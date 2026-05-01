#!/usr/bin/env bash
# Usage: watch -n 30 ./scripts/status.sh
export LC_NUMERIC=C

RPC="docker exec nanofury_lottery bfgminer-rpc"

get_field() {
    echo "$1" | grep -o "${2}=[^,|]*" | head -1 | cut -d= -f2-
}

summary=$($RPC summary 2>/dev/null | grep -o "SUMMARY,.*")
devs=$($RPC devs    2>/dev/null | grep -o "PGA=.*")
pools=$($RPC pools  2>/dev/null | grep -o "POOL=.*")

if [ -z "$summary" ]; then
    echo "ERROR: Container not running or API unreachable"
    echo "  docker compose up -d"
    exit 1
fi

mhs_av=$(get_field "$summary" "MHS av")
mhs_20s=$(get_field "$summary" "MHS 20s")
hw_errs=$(get_field "$devs"    "Hardware Errors")
hw_pct=$(get_field "$devs"    "Device Hardware%")
elapsed=$(get_field "$summary" "Elapsed")
best_share=$(get_field "$summary" "Best Share")
found=$(get_field "$summary" "Found Blocks")
diff1=$(get_field "$summary" "Diff1 Work")
dev_status=$(get_field "$devs" "Status")
pool_status=$(get_field "$pools" "Status")
pool_url=$(get_field "$pools" "Stratum URL")
accepted=$(get_field "$pools" "Accepted")
rejected=$(get_field "$pools" "Rejected")
network_blocks=$(get_field "$summary" "Network Blocks")

uptime_h=$((elapsed / 3600))
uptime_m=$(((elapsed % 3600) / 60))
uptime_s=$((elapsed % 60))

if [ -t 1 ]; then
    GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
    CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
else
    GREEN=''; RED=''; YELLOW=''; CYAN=''; BOLD=''; RESET=''
fi

[ "$dev_status"  = "Alive" ] && DEV_COLOR=$GREEN  || DEV_COLOR=$RED
[ "$pool_status" = "Alive" ] && POOL_COLOR=$GREEN  || POOL_COLOR=$RED

mhs_av_r=$(awk "BEGIN{printf \"%d\", $mhs_av}")
mhs_20s_r=$(awk "BEGIN{printf \"%d\", $mhs_20s}")
hw_pct_r=$(awk "BEGIN{printf \"%.4f\", $hw_pct}")

printf "${BOLD}Bitcoin Lottery — NanoFury NF2${RESET}   $(date '+%Y-%m-%d %H:%M:%S')\n"
printf '%0.s─' {1..50}; echo

printf "\n${CYAN}DEVICE${RESET}\n"
printf "  Status      : ${DEV_COLOR}%s${RESET}\n" "$dev_status"
printf "  Uptime      : %dh %dm %ds\n" "$uptime_h" "$uptime_m" "$uptime_s"
printf "  Hashrate    : ${BOLD}%s MH/s${RESET} avg  |  %s MH/s (20s)\n" "$mhs_av_r" "$mhs_20s_r"
printf "  HW Errors   : %s  (%s%%)\n" "$hw_errs" "$hw_pct_r"

printf "\n${CYAN}POOL${RESET}\n"
printf "  Status      : ${POOL_COLOR}%s${RESET}  —  %s\n" "$pool_status" "$pool_url"
printf "  Accepted    : %s  /  Rejected: %s\n" "$accepted" "$rejected"
printf "  Network blk : %s seen\n" "$network_blocks"

printf "\n${CYAN}LOTTERY${RESET}\n"
printf "  Blocks found: ${BOLD}%s${RESET}\n" "$found"
printf "  Best share  : %s\n" "$best_share"
printf "  Diff1 work  : %s\n" "$diff1"

echo
