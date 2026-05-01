#!/usr/bin/env python3
"""
Bitcoin Lottery Monitor
- Collects metrics from N miners (multi-manufacturer) every 60 s -> SQLite
- Fetches BTC price (CoinGecko) once per day -> SQLite
- Serves web dashboard on 0.0.0.0:8080
- Sends SMTP alerts: miner down/recovered, block found, weekly report
"""

import http.server
import json
import os
import smtplib
import sqlite3
import threading
import time
import urllib.request
from email.mime.text import MIMEText
from urllib.parse import urlparse, parse_qs

from adapters import load_miners_from_env, MinerAdapter

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH          = "/data/monitor.db"
COLLECT_INTERVAL = 60
PRICE_INTERVAL   = 86400
METRICS_RETENTION_DAYS = 30
PRICE_RETENTION_DAYS   = 365
BLOCK_REWARD_BTC = float(os.environ.get("BLOCK_REWARD_BTC", 3.125))

SMTP_HOST     = os.environ.get("SMTP_HOST", "")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER     = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM     = os.environ.get("SMTP_FROM", "") or SMTP_USER
SMTP_TO       = os.environ.get("SMTP_TO", "")
SMTP_STARTTLS = os.environ.get("SMTP_STARTTLS", "true").lower() != "false"
MONITOR_URL   = os.environ.get("MONITOR_URL", "http://localhost:8080")

# ---------------------------------------------------------------------------
# BTC price
# ---------------------------------------------------------------------------

def fetch_price() -> tuple[float, float] | None:
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=bitcoin&vs_currencies=eur,usd"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "bitcoin-lottery-monitor/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return float(data["bitcoin"]["eur"]), float(data["bitcoin"]["usd"])
    except Exception as e:
        print(f"[price] fetch error: {e}")
        return None


# ---------------------------------------------------------------------------
# SMTP
# ---------------------------------------------------------------------------

def smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_TO and SMTP_USER)


def send_mail(subject: str, body: str) -> bool:
    if not smtp_configured():
        return False
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"]    = SMTP_FROM
        msg["To"]      = SMTP_TO
        if SMTP_STARTTLS:
            s = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
            s.ehlo(); s.starttls(); s.ehlo()
        else:
            s = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15)
        if SMTP_USER:
            s.login(SMTP_USER, SMTP_PASSWORD)
        s.sendmail(SMTP_FROM, [SMTP_TO], msg.as_bytes())
        s.quit()
        print(f"[mail] Sent: {subject}")
        return True
    except Exception as e:
        print(f"[mail] Error sending '{subject}': {e}")
        return False


def _fmt_hash(mh: float) -> str:
    if mh >= 1e9:  return f"{mh / 1e9:.3f} PH/s"
    if mh >= 1e6:  return f"{mh / 1e6:.3f} TH/s"
    if mh >= 1e3:  return f"{mh / 1e3:.2f} GH/s"
    return f"{mh:.0f} MH/s"


def _fmt_eur(v: float | None) -> str:
    return f"{v:,.0f} EUR" if v else "n/a"


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------

def db_connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def db_init(con: sqlite3.Connection) -> None:
    # Drop any orphaned index that references miner_id before that column exists.
    # This can happen when a previous startup crashed mid-migration.
    existing_cols = {row[1] for row in con.execute("PRAGMA table_info(metrics)")}
    if "miner_id" not in existing_cols:
        con.execute("DROP INDEX IF EXISTS idx_metrics_mid")
        con.commit()

    # Create tables using v1-compatible schema.
    # _migrate() adds the multi-miner columns to both new and existing databases.
    con.executescript("""
        CREATE TABLE IF NOT EXISTS metrics (
            ts           INTEGER PRIMARY KEY,
            mhs_avg      REAL,
            mhs_20s      REAL,
            hw_pct       REAL,
            hw_errors    INTEGER,
            diff1_work   INTEGER,
            found_blocks INTEGER,
            best_share   REAL,
            elapsed      INTEGER,
            accepted     INTEGER,
            rejected     INTEGER,
            pool_alive   INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(ts);

        CREATE TABLE IF NOT EXISTS prices (
            ts        INTEGER PRIMARY KEY,
            price_eur REAL,
            price_usd REAL
        );
        CREATE INDEX IF NOT EXISTS idx_prices_ts ON prices(ts);

        CREATE TABLE IF NOT EXISTS block_events (
            ts        INTEGER PRIMARY KEY,
            block_num INTEGER,
            price_eur REAL,
            price_usd REAL
        );

        CREATE TABLE IF NOT EXISTS email_state (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    _migrate(con)
    con.commit()
    con.execute("CREATE INDEX IF NOT EXISTS idx_metrics_mid ON metrics(miner_id, ts)")
    con.commit()


def _migrate(con: sqlite3.Connection) -> None:
    """Add columns introduced after v1 to existing databases."""
    for col, ddl in [
        ("miner_id", "TEXT DEFAULT 'miner_1'"),
        ("temp_c",   "REAL"),
    ]:
        try:
            con.execute(f"ALTER TABLE metrics ADD COLUMN {col} {ddl}")
        except Exception:
            pass  # column already exists

    for col, ddl in [("miner_id", "TEXT DEFAULT 'miner_1'")]:
        try:
            con.execute(f"ALTER TABLE block_events ADD COLUMN {col} {ddl}")
        except Exception:
            pass


def db_get_state(con, key: str, default: str = "") -> str:
    row = con.execute("SELECT value FROM email_state WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def db_set_state(con, key: str, value) -> None:
    con.execute("INSERT OR REPLACE INTO email_state (key, value) VALUES (?,?)",
                (key, str(value)))
    con.commit()


def db_insert_metrics(con: sqlite3.Connection, m: dict) -> None:
    con.execute("""
        INSERT OR REPLACE INTO metrics
        (ts, miner_id, mhs_avg, mhs_20s, hw_pct, hw_errors, diff1_work,
         found_blocks, best_share, elapsed, accepted, rejected, pool_alive, temp_c)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        m["ts"], m["miner_id"],
        m["hashrate_avg"], m["hashrate_short"],
        m["hw_error_pct"], m["hw_errors"], m["work_done"],
        m["found_blocks"], m["best_share"], m["uptime_sec"],
        m["accepted"], m["rejected"], m["pool_alive"], m["temp_c"],
    ))
    con.commit()


def db_insert_price(con, eur: float, usd: float) -> None:
    con.execute("INSERT OR REPLACE INTO prices (ts, price_eur, price_usd) VALUES (?,?,?)",
                (int(time.time()), eur, usd))
    con.commit()


def db_insert_block_event(con, ts: int, miner_id: str, block_num: int) -> None:
    row = con.execute("SELECT price_eur, price_usd FROM prices ORDER BY ts DESC LIMIT 1").fetchone()
    eur = row["price_eur"] if row else None
    usd = row["price_usd"] if row else None
    con.execute(
        "INSERT OR IGNORE INTO block_events (ts, miner_id, block_num, price_eur, price_usd)"
        " VALUES (?,?,?,?,?)",
        (ts, miner_id, block_num, eur, usd),
    )
    con.commit()
    val = f"{BLOCK_REWARD_BTC * eur:,.0f} EUR" if eur else "unknown"
    print(f"[blocks] *** BLOCK #{block_num} found by {miner_id}! Value: {val} ***")


def db_purge(con: sqlite3.Connection) -> None:
    now = int(time.time())
    con.execute("DELETE FROM metrics WHERE ts < ?", (now - METRICS_RETENTION_DAYS * 86400,))
    con.execute("DELETE FROM prices  WHERE ts < ?", (now - PRICE_RETENTION_DAYS  * 86400,))
    con.commit()


def db_latest(con: sqlite3.Connection, miner_id: str | None = None) -> dict | None:
    if miner_id and miner_id != "all":
        row = con.execute(
            "SELECT * FROM metrics WHERE miner_id=? ORDER BY ts DESC LIMIT 1",
            (miner_id,),
        ).fetchone()
        return dict(row) if row else None
    # Aggregate across all miners (most recent sample per miner, then sum/max)
    row = con.execute("""
        SELECT
            MAX(ts)                 AS ts,
            'all'                   AS miner_id,
            SUM(mhs_avg)            AS mhs_avg,
            SUM(mhs_20s)            AS mhs_20s,
            AVG(hw_pct)             AS hw_pct,
            SUM(hw_errors)          AS hw_errors,
            SUM(diff1_work)         AS diff1_work,
            SUM(found_blocks)       AS found_blocks,
            MAX(best_share)         AS best_share,
            MAX(elapsed)            AS elapsed,
            SUM(accepted)           AS accepted,
            SUM(rejected)           AS rejected,
            MIN(pool_alive)         AS pool_alive,
            MAX(temp_c)             AS temp_c
        FROM (
            SELECT * FROM metrics
            WHERE ts >= (SELECT MAX(ts) - 120 FROM metrics)
        )
    """).fetchone()
    return dict(row) if row else None


def db_latest_price(con: sqlite3.Connection) -> dict | None:
    row = con.execute("SELECT * FROM prices ORDER BY ts DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def db_history(con: sqlite3.Connection, start: int, end: int,
               miner_id: str | None = None) -> list[dict]:
    if miner_id and miner_id != "all":
        rows = con.execute(
            "SELECT * FROM metrics WHERE miner_id=? AND ts>=? AND ts<=? ORDER BY ts ASC",
            (miner_id, start, end),
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT * FROM metrics WHERE ts>=? AND ts<=? ORDER BY ts ASC",
            (start, end),
        ).fetchall()
    return [dict(r) for r in rows]


def db_price_history(con: sqlite3.Connection, start: int, end: int) -> list[dict]:
    rows = con.execute(
        "SELECT * FROM prices WHERE ts>=? AND ts<=? ORDER BY ts ASC",
        (start, end),
    ).fetchall()
    return [dict(r) for r in rows]


def db_block_events(con: sqlite3.Connection) -> list[dict]:
    rows = con.execute("SELECT * FROM block_events ORDER BY ts ASC").fetchall()
    result = []
    for r in rows:
        d = dict(r)
        if d.get("price_eur"):
            d["value_eur"] = round(BLOCK_REWARD_BTC * d["price_eur"], 2)
            d["value_usd"] = round(BLOCK_REWARD_BTC * d["price_usd"], 2)
        result.append(d)
    return result


def db_stats(con: sqlite3.Connection, miner_id: str | None = None) -> dict:
    if miner_id and miner_id != "all":
        where = "WHERE miner_id=?"
        params: tuple = (miner_id,)
    else:
        where, params = "", ()
    row = con.execute(f"""
        SELECT
            COUNT(*)                                            AS total_samples,
            ROUND(AVG(mhs_avg), 0)                             AS avg_hashrate,
            ROUND(MAX(best_share), 2)                          AS peak_best_share,
            MAX(found_blocks)                                  AS total_found,
            ROUND(100.0 * SUM(pool_alive) / MAX(COUNT(*),1),1) AS uptime_pct,
            MIN(ts)                                            AS first_seen,
            ROUND(SUM(mhs_avg * 60.0), 0)                     AS cumulative_mh
        FROM metrics {where}
    """, params).fetchone()
    return dict(row) if row else {}


# ---------------------------------------------------------------------------
# Email report bodies
# ---------------------------------------------------------------------------

def _weekly_report_body(con: sqlite3.Connection, adapters: list[MinerAdapter]) -> str:
    price = db_latest_price(con)
    price_eur = price["price_eur"] if price else None
    agg = db_stats(con)
    blocks = db_block_events(con)

    lines = [
        "Bitcoin Lottery - Weekly Report",
        "=" * 40,
        f"Monitoring since: {time.strftime('%Y-%m-%d', time.localtime(agg.get('first_seen', time.time())))}\n",
        "AGGREGATE",
        "-" * 16,
        f"Avg hashrate:    {_fmt_hash(agg.get('avg_hashrate') or 0)}",
        f"Cumulative work: {_fmt_hash(agg.get('cumulative_mh') or 0).replace('/s','')}",
        f"Pool uptime:     {agg.get('uptime_pct', 0)}%",
        f"Blocks found:    {agg.get('total_found', 0)}",
        "",
    ]
    for a in adapters:
        s = db_stats(con, a.miner_id)
        lines += [
            f"MINER: {a.name}",
            f"  Avg hashrate:  {_fmt_hash(s.get('avg_hashrate') or 0)}",
            f"  Pool uptime:   {s.get('uptime_pct', 0)}%",
            f"  Best share:    {s.get('peak_best_share', 0)}",
            f"  Blocks found:  {s.get('total_found', 0)}",
            "",
        ]
    lines += [
        "BTC PRICE",
        "-" * 16,
        f"Current:       {_fmt_eur(price_eur)}",
        f"Block reward:  {_fmt_eur(BLOCK_REWARD_BTC * price_eur) if price_eur else 'n/a'}",
        "",
    ]
    if blocks:
        lines += ["BLOCKS FOUND", "-" * 16]
        for b in blocks:
            ts_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(b["ts"]))
            val = _fmt_eur(b.get("value_eur"))
            lines.append(f"  Block #{b['block_num']} by {b['miner_id']} at {ts_str}  ->  {val}")
        lines.append("")
    else:
        lines.append("Blocks found: 0  (still in the game)\n")

    lines.append(f"Dashboard: {MONITOR_URL}")
    return "\n".join(lines)


def _block_alert_body(miner_name: str, block_num: int,
                      price_eur: float | None, price_usd: float | None) -> str:
    value_eur = _fmt_eur(BLOCK_REWARD_BTC * price_eur) if price_eur else "n/a"
    value_usd = f"{BLOCK_REWARD_BTC * price_usd:,.0f} USD" if price_usd else "n/a"
    return (
        f"BLOCK FOUND!\n\n"
        f"Miner:        {miner_name}\n"
        f"Block number: #{block_num}\n"
        f"Reward:       {BLOCK_REWARD_BTC} BTC\n"
        f"BTC price:    {_fmt_eur(price_eur)} / {f'{price_usd:,.0f} USD' if price_usd else 'n/a'}\n"
        f"Value:        {value_eur} / {value_usd}\n\n"
        f"Next steps:\n"
        f"1. Verify on-chain: {MONITOR_URL}/api/blocks\n"
        f"2. Open wallet and wait for 100 confirmations (~16h)\n"
        f"3. See docs/winning.md for full instructions\n\n"
        f"Dashboard: {MONITOR_URL}\n"
    )


# ---------------------------------------------------------------------------
# Collector thread — one per adapter
# ---------------------------------------------------------------------------

def collector_loop(adapter: MinerAdapter, con: sqlite3.Connection) -> None:
    last_purge   = 0
    prev_blocks  = None
    fail_count   = 0
    down_alerted = False
    FAIL_THRESHOLD = 3

    while True:
        m = adapter.fetch()

        if m:
            db_insert_metrics(con, m)

            if down_alerted:
                send_mail(
                    f"✅ Miner back online - {adapter.name}",
                    f"'{adapter.name}' is reachable again.\n\n"
                    f"Hashrate: {_fmt_hash(m['hashrate_avg'])}\n\n{MONITOR_URL}",
                )
                down_alerted = False
            fail_count = 0

            if prev_blocks is not None and m["found_blocks"] > prev_blocks:
                db_insert_block_event(con, m["ts"], adapter.miner_id, m["found_blocks"])
                price = db_latest_price(con)
                send_mail(
                    f"🎉 BLOCK FOUND #{m['found_blocks']} - {adapter.name}",
                    _block_alert_body(
                        adapter.name, m["found_blocks"],
                        price["price_eur"] if price else None,
                        price["price_usd"] if price else None,
                    ),
                )
            prev_blocks = m["found_blocks"]

            print(f"[{adapter.miner_id}] {time.strftime('%H:%M:%S')}  "
                  f"{_fmt_hash(m['hashrate_avg'])}  "
                  f"pool={'up' if m['pool_alive'] else 'DOWN'}  "
                  f"blocks={m['found_blocks']}")

        else:
            fail_count += 1
            print(f"[{adapter.miner_id}] {time.strftime('%H:%M:%S')}  "
                  f"unreachable (#{fail_count})")

            if fail_count >= FAIL_THRESHOLD and not down_alerted:
                elapsed_min = fail_count * COLLECT_INTERVAL // 60
                send_mail(
                    f"🚨 Miner unreachable - {adapter.name}",
                    f"'{adapter.name}' has not responded for ~{elapsed_min} minutes.\n\n"
                    f"Host: {adapter.host}:{adapter.port}\n\n"
                    f"Dashboard: {MONITOR_URL}",
                )
                down_alerted = True

        now = time.time()
        if now - last_purge > 86400:
            db_purge(con)
            last_purge = now

        time.sleep(COLLECT_INTERVAL)


# ---------------------------------------------------------------------------
# Price thread
# ---------------------------------------------------------------------------

def price_loop(con: sqlite3.Connection) -> None:
    while True:
        result = fetch_price()
        if result:
            eur, usd = result
            db_insert_price(con, eur, usd)
            print(f"[price] BTC {eur:,.0f} EUR / {usd:,.0f} USD")
        time.sleep(PRICE_INTERVAL)


# ---------------------------------------------------------------------------
# Weekly report thread
# ---------------------------------------------------------------------------

def weekly_report_loop(con: sqlite3.Connection, adapters: list[MinerAdapter]) -> None:
    while True:
        last_ts = float(db_get_state(con, "last_weekly_ts", "0"))
        if time.time() - last_ts >= 7 * 86400:
            body = _weekly_report_body(con, adapters)
            sent = send_mail("📊 Bitcoin Lottery - Weekly Report", body)
            if sent or not smtp_configured():
                db_set_state(con, "last_weekly_ts", time.time())
        time.sleep(3600)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "index.html")

RANGE_SECONDS = {
    "1h": 3600, "6h": 21600, "24h": 86400,
    "7d": 604800, "30d": 2592000, "90d": 7776000, "365d": 31536000,
}


class Handler(http.server.BaseHTTPRequestHandler):
    db:       sqlite3.Connection
    adapters: list[MinerAdapter]

    def log_message(self, fmt, *args):
        pass

    def send_json(self, data, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _window(self, qs: dict) -> tuple[int, int]:
        now = int(time.time())
        if "start" in qs and "end" in qs:
            return int(qs["start"][0]), int(qs["end"][0])
        r = qs.get("range", ["24h"])[0]
        return now - RANGE_SECONDS.get(r, 86400), now

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        qs     = parse_qs(parsed.query)
        miner  = qs.get("miner", [None])[0]  # None = all

        if path == "/":
            try:
                with open(DASHBOARD_PATH, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except FileNotFoundError:
                self.send_error(404, "index.html not found")

        elif path == "/api/miners":
            self.send_json([
                {"miner_id": a.miner_id, "name": a.name,
                 "type": a.__class__.__name__.replace("Adapter", "").lower(),
                 "host": a.host, "port": a.port}
                for a in self.adapters
            ])

        elif path == "/api/now":
            price = db_latest_price(self.db)
            agg   = db_latest(self.db, None)   # aggregate

            per_miner = {}
            for a in self.adapters:
                row = db_latest(self.db, a.miner_id)
                if row:
                    per_miner[a.miner_id] = dict(row, name=a.name)

            response: dict = {
                "aggregate": agg or {},
                "miners": per_miner,
                "price_eur": price["price_eur"] if price else None,
                "price_usd": price["price_usd"] if price else None,
            }
            if price:
                response["block_value_eur"] = round(BLOCK_REWARD_BTC * price["price_eur"], 2)
                response["block_value_usd"] = round(BLOCK_REWARD_BTC * price["price_usd"], 2)
            self.send_json(response)

        elif path == "/api/history":
            start, end = self._window(qs)
            self.send_json(db_history(self.db, start, end, miner))

        elif path == "/api/prices":
            start, end = self._window(qs)
            self.send_json(db_price_history(self.db, start, end))

        elif path == "/api/blocks":
            self.send_json(db_block_events(self.db))

        elif path == "/api/stats":
            self.send_json(db_stats(self.db, miner))

        else:
            self.send_error(404)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    adapters = load_miners_from_env()
    con = db_connect()
    db_init(con)

    if smtp_configured():
        print(f"[mail] SMTP configured -> {SMTP_TO}")
    else:
        print("[mail] SMTP not configured - email alerts disabled")

    result = fetch_price()
    if result:
        eur, usd = result
        db_insert_price(con, eur, usd)
        print(f"[price] initial: BTC {eur:,.0f} EUR / {usd:,.0f} USD")
    else:
        print("[price] initial fetch failed, will retry in 24h")

    # Initial metrics per adapter
    for adapter in adapters:
        for attempt in range(10):
            m = adapter.fetch()
            if m:
                db_insert_metrics(con, m)
                break
            print(f"[startup] {adapter.name} not ready, retry {attempt + 1}/10 in 6s ...")
            time.sleep(6)

    for adapter in adapters:
        threading.Thread(
            target=collector_loop, args=(adapter, con), daemon=True, name=adapter.miner_id,
        ).start()

    threading.Thread(target=price_loop, args=(con,), daemon=True).start()
    threading.Thread(target=weekly_report_loop, args=(con, adapters), daemon=True).start()

    Handler.db       = con
    Handler.adapters = adapters
    server = http.server.ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    print(f"[server] Dashboard running on http://0.0.0.0:8080  ({len(adapters)} miner(s))")
    server.serve_forever()


if __name__ == "__main__":
    main()
