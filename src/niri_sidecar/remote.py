#!/usr/bin/python3
import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import shlex

from niri_sidecar.common import config, theme

HOME = Path.home()
RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "niri-sidecar" / "ssh"
COLLECTOR = Path(__file__).with_name("collect.sh")


def fields(lines):
    return {
        key: value.strip()
        for key, value in (line.split(None, 1) for line in lines if len(line.split(None, 1)) == 2)
    }


def parse_sample(text):
    sections = {}
    section = None
    for line in text.splitlines():
        if line.startswith("@@"):
            section = sections.setdefault(line[2:], [])
        elif section is not None:
            section.append(line)
    result = {"gpus": [], "disks": []}
    model = sections.get("MODEL", [])
    result["hostname"] = model[0] if model else ""
    cpu_model = model[1] if len(model) > 1 else "CPU"
    cores = int(model[2]) if len(model) > 2 else 1
    for row in csv.reader(sections.get("GPU", []), skipinitialspace=True):
        if len(row) == 5:
            idx, name, used, total, utilization = [s.strip() for s in row]
            result["gpus"].append(
                {
                    "index": idx,
                    "name": name,
                    "used": float(used),
                    "total": float(total),
                    "utilization": float(utilization) if utilization.isnumeric() else None,
                }
            )
    memory = fields(sections.get("MEMORY", []))
    if "MemTotal:" in memory and "MemAvailable:" in memory:
        total = int(memory["MemTotal:"].split()[0]) * 1024
        used = total - int(memory["MemAvailable:"].split()[0]) * 1024
        scope = "host"
        if memory.get("limit", "").isdigit() and 0 < int(memory["limit"]) < total:
            total = int(memory["limit"])
            stat_values = memory.get("stat", "").split()
            stats = dict(zip(stat_values[::2], stat_values[1::2]))
            reclaimable = int(stats.get("total_inactive_file", stats.get("inactive_file", 0)))
            used = max(0, int(memory["current"]) - reclaimable)
            scope = "container quota"
        result["memory"] = {
            "used": used,
            "total": total,
            "percent": min(100, used / total * 100),
            "scope": scope,
        }
    limits = fields(sections.get("LIMITS", []))
    quota = float(limits.get("quota", "-1"))
    period = float(limits.get("period", "100000"))
    if "cpumax" in limits:
        q, p = limits["cpumax"].split()
        quota, period = (float(q) if q != "max" else -1), float(p)
    allocated = min(cores, quota / period) if quota > 0 else cores
    start = fields(sections.get("CPU_START", []))
    end = fields(sections.get("CPU_END", []))
    if "cpu" in start and "cpu" in end:
        before = [int(v) for v in start["cpu"].split()[:8]]
        after = [int(v) for v in end["cpu"].split()[:8]]
        elapsed_ticks = sum(after) - sum(before)
        idle_ticks = after[3] + after[4] - before[3] - before[4]
        percent = (1 - idle_ticks / elapsed_ticks) * 100 if elapsed_ticks else 0
        scope = "host"
        if "uptime" in start and "uptime" in end:
            seconds = float(end["uptime"].split()[0]) - float(start["uptime"].split()[0])
            usage_start, usage_end = None, None
            if "usage_ns" in start and "usage_ns" in end:
                usage_start, usage_end = int(start["usage_ns"]), int(end["usage_ns"])
            elif "cpu_stat" in start and "cpu_stat" in end:
                first, last = start["cpu_stat"].split(), end["cpu_stat"].split()
                first, last = dict(zip(first[::2], first[1::2])), dict(zip(last[::2], last[1::2]))
                if "usage_usec" in first and "usage_usec" in last:
                    usage_start, usage_end = int(first["usage_usec"]) * 1000, int(last["usage_usec"]) * 1000
            if seconds > 0 and usage_start is not None:
                percent = (usage_end - usage_start) / 1e9 / seconds / allocated * 100
                scope = "container quota"
        result["cpu"] = {
            "model": cpu_model,
            "cores": allocated,
            "percent": max(0, min(100, percent)),
            "scope": scope,
        }
    seen = set()
    for line in sections.get("DISKS", [])[1:]:
        row = line.split()
        if len(row) < 6 or not row[1].isdigit() or row[-1] in seen:
            continue
        seen.add(row[-1])
        total, used, available = (int(v) * 1024 for v in row[1:4])
        result["disks"].append(
            {
                "mount": row[-1],
                "total": total,
                "used": used,
                "available": available,
                "percent": float(row[4].rstrip("%")),
            }
        )
    return result


def connection(args):
    options = []
    host = None
    index = 1
    takes_value = set("BbcDEeFIiJLlmOopQRSWw")
    while index < len(args):
        arg = args[index]
        if arg == "--":
            index += 1
            host = args[index] if index < len(args) else None
            break
        if not arg.startswith("-") or arg == "-":
            host = arg
            break
        flag = arg[1:2]
        if flag in takes_value:
            value = arg[2:]
            if not value:
                index += 1
                if index >= len(args):
                    return None
                value = args[index]
            if flag in "pJilF":
                options += ["-" + flag, value]
            elif flag == "o":
                name = value.split("=", 1)[0].split()[0].lower()
                if name in {
                    "hostname",
                    "user",
                    "port",
                    "identityfile",
                    "identityagent",
                    "identitiesonly",
                    "proxyjump",
                    "proxycommand",
                    "controlpath",
                    "hostkeyalias",
                    "certificatefile",
                }:
                    options += ["-o", value]
        index += 1
    if not host or host.startswith("-"):
        return None
    port = next((options[i + 1] for i, v in enumerate(options[:-1]) if v == "-p"), "")
    label = host + (":" + port if port else "")
    key = hashlib.sha256(json.dumps([options, host]).encode()).hexdigest()[:16]
    return {"key": key, "host": host, "label": label, "options": options}


def sessions():
    found = {}
    for proc in Path("/proc").iterdir():
        if not proc.name.isdecimal():
            continue
        try:
            if proc.stat().st_uid != os.getuid() or (proc / "comm").read_text().strip() != "ssh":
                continue
            if not str((proc / "fd/0").resolve()).startswith("/dev/pts/"):
                continue
            args = [a.decode() for a in (proc / "cmdline").read_bytes().split(b"\0") if a]
            target = connection(args)
            if target:
                found.setdefault(target["key"], target)["pids"] = found.get(target["key"], {}).get(
                    "pids", []
                ) + [int(proc.name)]
        except (OSError, UnicodeError):
            continue
    return found


def query(target):
    command = [
        "ssh",
        *target["options"],
        "-T",
        "-x",
        "-a",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=4",
        "-o",
        "ConnectionAttempts=1",
        "-o",
        "ClearAllForwardings=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "PermitLocalCommand=no",
        "-o",
        "ControlMaster=auto",
        "-o",
        "ControlPersist=15",
        "-o",
        f"ControlPath={RUNTIME / target['key']}",
        target["host"],
        "sh -s -- " + " ".join(shlex.quote(p) for p in config()["remote"]["disk_paths"]),
    ]
    result = {"key": target["key"], "host": target["label"], "gpus": []}
    try:
        run = subprocess.run(command, capture_output=True, text=True, timeout=7, input=COLLECTOR.read_text())
        if run.returncode:
            message = run.stderr.strip()
            if "Permission denied" in message:
                result["error"] = "SSH authentication unavailable; configure a key or reusable connection"
            else:
                result["error"] = (
                    "SSH query failed; check authentication, network and the configured SSH host."
                )
            return result
        result.update(parse_sample(run.stdout))
        if not result.get("cpu") and not result.get("memory"):
            result["error"] = "Remote system metrics unavailable"
        result["updated"] = time.time()
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        result["error"] = (
            "SSH query timed out"
            if isinstance(error, subprocess.TimeoutExpired)
            else "Unable to read remote metrics"
        )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args(argv)
    RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
    RUNTIME.chmod(0o700)
    cached = {}
    previous = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        while True:
            targets = sessions()
            due = [
                t
                for key, t in targets.items()
                if key not in cached
                or time.monotonic() - cached[key][0] >= max(1, float(config()["remote"]["interval"]))
            ]
            for target, value in zip(due, pool.map(query, due)):
                cached[target["key"]] = (time.monotonic(), value)
            cached = {key: value for key, value in cached.items() if key in targets}
            hosts = [dict(cached[key][1]) for key in targets]
            if config()["privacy"]["redact_hosts"]:
                for index, host in enumerate(hosts, 1):
                    host["host"] = f"Remote {index}"
                    host["hostname"] = ""
            state = {**theme(), "hosts": hosts}
            output = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
            if output != previous:
                print(output, flush=True)
                previous = output
            if not args.watch:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()
