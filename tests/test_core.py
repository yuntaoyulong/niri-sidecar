import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from niri_sidecar import common, remote, windows


class Samples(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / "tests/fixtures/container.sample").read_text()

    def test_cgroup_v1_limits_and_cache(self):
        result = remote.parse_sample(self.text)
        self.assertEqual(result["memory"]["total"], 8 * 1024**3)
        self.assertEqual(result["memory"]["used"], 2 * 1024**3)
        self.assertEqual(result["memory"]["percent"], 25)
        self.assertEqual(result["cpu"]["cores"], 2)
        self.assertAlmostEqual(result["cpu"]["percent"], 50)
        self.assertEqual(len(result["disks"]), 1)
        self.assertEqual(result["gpus"][0]["utilization"], 78)

    def test_cgroup_v2_cpu(self):
        text = self.text.replace("quota 200000 \nperiod 100000 ", "cpumax 200000 100000")
        text = text.replace("usage_ns 1000000000 ", "cpu_stat usage_usec 1000000 user_usec 500000")
        text = text.replace("usage_ns 1250000000 ", "cpu_stat usage_usec 1250000 user_usec 600000")
        result = remote.parse_sample(text)
        self.assertAlmostEqual(result["cpu"]["percent"], 50)

    def test_no_gpu_still_reports_cpu_memory_and_disk(self):
        result = remote.parse_sample(self.text.replace("0, NVIDIA A100 80GB PCIe, 40960, 81920, 78", ""))
        self.assertEqual(result["gpus"], [])
        self.assertIn("cpu", result)
        self.assertIn("memory", result)
        self.assertEqual(len(result["disks"]), 1)

    def test_host_fallback_and_guest_ticks(self):
        text = "\n".join(
            l
            for l in self.text.splitlines()
            if not l.startswith(("limit ", "current ", "stat ", "quota ", "period ", "usage_ns "))
        )
        result = remote.parse_sample(text)
        self.assertEqual(result["cpu"]["scope"], "host")
        self.assertAlmostEqual(result["cpu"]["percent"], 20)
        self.assertEqual(result["memory"]["total"], 32 * 1024**3)


class Connections(unittest.TestCase):
    def test_connection_options_only(self):
        result = remote.connection(
            [
                "ssh",
                "-p2222",
                "-L",
                "8000:localhost:80",
                "-J",
                "jump.example",
                "-i",
                "/example/key",
                "-o",
                "PermitLocalCommand=yes",
                "user@gpu.example",
                "do-not-run-this",
            ]
        )
        self.assertEqual(result["options"], ["-p", "2222", "-J", "jump.example", "-i", "/example/key"])
        self.assertNotIn("do-not-run-this", json.dumps(result))
        self.assertNotIn("8000", json.dumps(result))

    def test_batch_query_does_not_forward_agent_or_ports(self):
        target = remote.connection(["ssh", "-p", "2222", "user@gpu.example"])
        sample = (ROOT / "tests/fixtures/container.sample").read_text()
        with patch.object(
            remote.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, sample, "")
        ) as run:
            remote.query(target)
        args = run.call_args.args[0]
        self.assertIn("-a", args)
        self.assertIn("ClearAllForwardings=yes", args)
        self.assertIn("StrictHostKeyChecking=yes", args)
        self.assertIn("PermitLocalCommand=no", args)
        self.assertEqual(args[-1], "sh -s -- ")

    def test_cannot_focus_an_unrelated_window(self):
        with (
            patch.object(windows, "tasks", return_value={"tasks": [{"id": 10}]}),
            patch.object(windows.subprocess, "run") as run,
        ):
            with self.assertRaises(ValueError):
                windows.focus(20, "example.browser")
            run.assert_not_called()


class Privacy(unittest.TestCase):
    def test_private_defaults(self):
        self.assertTrue(common.DEFAULTS["privacy"]["redact_hosts"])
        self.assertFalse(common.DEFAULTS["modules"]["clipboard_pins"])
        self.assertFalse(common.DEFAULTS["modules"]["previews"])
        self.assertFalse(common.DEFAULTS["modules"]["folder_tabs"])

    def test_demo_only_uses_fictional_data(self):
        result = subprocess.check_output(
            [sys.executable, str(ROOT / "src/niri_sidecar/cli.py"), "demo", "--json"], text=True
        )
        scene = json.loads(result)
        self.assertTrue(scene["remote"]["demo"])
        self.assertEqual(scene["remote"]["hosts"][0]["host"], "Remote 1")
        self.assertEqual(scene["pins"][0]["paths"], ["/example/example.txt"])

    def test_install_is_relocatable_and_preserves_existing_config(self):
        with tempfile.TemporaryDirectory() as folder:
            prefix, cfg = Path(folder) / "prefix", Path(folder) / "config"
            config_file = cfg / "niri-sidecar/config.json"
            config_file.parent.mkdir(parents=True)
            config_file.write_text('{"display":"EXAMPLE-1"}')
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "install.py"),
                    "--prefix",
                    str(prefix),
                    "--config-home",
                    str(cfg),
                ],
                check=True,
                capture_output=True,
            )
            result = subprocess.check_output([str(prefix / "bin/niri-sidecar"), "demo", "--json"], text=True)
            self.assertTrue(json.loads(result)["remote"]["demo"])
            self.assertEqual(json.loads(config_file.read_text())["display"], "EXAMPLE-1")


if __name__ == "__main__":
    unittest.main()
