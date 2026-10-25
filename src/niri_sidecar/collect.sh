LC_ALL=C
export LC_ALL
read_value() {
    if test -r "$2"; then
        printf '%s ' "$1"
        tr '\n' ' ' < "$2"
        printf '\n'
    fi
}
cpu_sample() {
    head -n 1 /proc/stat
    read_value uptime /proc/uptime
    read_value usage_ns /sys/fs/cgroup/cpuacct/cpuacct.usage
    read_value usage_ns /sys/fs/cgroup/cpu,cpuacct/cpuacct.usage
    read_value cpu_stat /sys/fs/cgroup/cpu.stat
}
printf '@@MODEL\n'
hostname
awk -F: '/model name|Hardware/ {sub(/^[ \t]+/, "", $2); print $2; found=1; exit} END {if (!found) print "CPU"}' /proc/cpuinfo
getconf _NPROCESSORS_ONLN
printf '@@GPU\n'
if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits 2>/dev/null
fi
printf '@@MEMORY\n'
grep -E '^(MemTotal|MemAvailable):' /proc/meminfo
read_value limit /sys/fs/cgroup/memory/memory.limit_in_bytes
read_value current /sys/fs/cgroup/memory/memory.usage_in_bytes
read_value stat /sys/fs/cgroup/memory/memory.stat
read_value limit /sys/fs/cgroup/memory.max
read_value current /sys/fs/cgroup/memory.current
read_value stat /sys/fs/cgroup/memory.stat
printf '@@LIMITS\n'
read_value quota /sys/fs/cgroup/cpu/cpu.cfs_quota_us
read_value period /sys/fs/cgroup/cpu/cpu.cfs_period_us
read_value cpumax /sys/fs/cgroup/cpu.max
printf '@@DISKS\n'
if test "$#" -eq 0; then
    set -- / "$HOME" "$HOME/autodl-tmp" "$HOME/autodl-fs" /autodl-fs
fi
for path do
    case "$path" in
        "~") path="$HOME" ;;
        "~/"*) path="$HOME/${path#~/}" ;;
    esac
    df -Pk "$path" 2>/dev/null
done
printf '@@CPU_START\n'
cpu_sample
sleep .25
printf '@@CPU_END\n'
cpu_sample
printf '@@END\n'
