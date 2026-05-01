#!/usr/bin/env bash
# Send test emails for all alert types via the running monitor container.
# Reads SMTP credentials from the container's environment (set via .env).
#
# Usage:
#   ./scripts/test-mail.sh             # all three types
#   ./scripts/test-mail.sh down        # miner-offline alert only
#   ./scripts/test-mail.sh block       # block-found alert only
#   ./scripts/test-mail.sh report      # weekly report only

set -euo pipefail
cd "$(dirname "$0")/.."

TYPE="${1:-all}"

if ! docker inspect bitcoin_monitor >/dev/null 2>&1; then
    echo "ERROR: Container bitcoin_monitor is not running."
    echo "       Start it with: docker compose up -d monitor"
    exit 1
fi

run_py() {
    docker exec bitcoin_monitor python3 -c "$1"
}

send() {
    local kind="$1"
    echo "-> Sending test mail: ${kind} ..."
    run_py "
import sys
sys.path.insert(0, '/app')
import app, time

ok = False

if '${kind}' == 'down':
    ok = app.send_mail(
        '[TEST] 🚨 Bitcoin Miner - unreachable',
        '''This is a test email for alert type: MINER OFFLINE.

In a real incident this means the miner has not responded for ~3 minutes.

Possible causes:
  - Container crashed        (docker compose ps)
  - USB device disconnected  (lsusb | grep 04d8)
  - BFGMiner hung            (docker compose restart nanofury_lottery)

Dashboard: ''' + app.MONITOR_URL
    )

elif '${kind}' == 'block':
    ok = app.send_mail(
        '[TEST] 🎉 BLOCK FOUND #1 - Bitcoin Lottery',
        app._block_alert_body(1, 65000.0, 72000.0)
    )

elif '${kind}' == 'report':
    con = app.db_connect()
    body = app._weekly_report_body(con)
    ok = app.send_mail('[TEST] 📊 Bitcoin Lottery - Weekly Report', body)

if ok:
    print('OK - email sent successfully.')
else:
    print('ERROR - check SMTP settings in .env')
    print('  SMTP_HOST:', app.SMTP_HOST or '(not set)')
    print('  SMTP_USER:', app.SMTP_USER or '(not set)')
    print('  SMTP_TO:  ', app.SMTP_TO   or '(not set)')
    sys.exit(1)
"
}

case "$TYPE" in
    down)   send down   ;;
    block)  send block  ;;
    report) send report ;;
    all)
        send down
        echo
        send block
        echo
        send report
        ;;
    *)
        echo "Unknown type: $TYPE"
        echo "Allowed: all | down | block | report"
        exit 1
        ;;
esac

echo
echo "Done. Check the inbox of: $(docker exec bitcoin_monitor python3 -c 'import app; print(app.SMTP_TO or "(not configured)")')"
