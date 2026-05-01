# Dashboard

The web dashboard runs as a Docker service alongside the miner and is accessible at `http://<server-ip>:8080`.

![Dashboard Screenshot](img/dashboard.png)

## Metrics

### Header bar

| Element | Meaning |
|---------|---------|
| Pool: Live / OFFLINE | Green dot = Stratum connection active |
| Stand: HH:MM:SS | Last data refresh |

### Metric cards

| Card | Source | Notes |
|------|--------|-------|
| **Hashrate** | BFGMiner `devs` | Average since start + 20-second rolling |
| **BTC Kurs** | CoinGecko (täglich) | EUR and USD |
| **Blockwert** | Kurs × 3.125 BTC | What the current reward is worth right now |
| **Blöcke gefunden** | BFGMiner `summary` | Gold = 0 (no win yet), green = win |
| **Bester Share** | BFGMiner `summary` | Closest the chip has come to a valid block hash |
| **HW-Fehlerrate** | BFGMiner `devs` | Green <1%, orange 1–2%, red >2% |
| **Laufzeit** | BFGMiner `summary` | Time since last BFGMiner restart |

### Charts

| Chart | Data | Update |
|-------|------|--------|
| Hashrate (MH/s) | Ø and 20s rolling | Every 60 s |
| BTC Kurs (EUR) | Daily close price | Once per day |
| Hardware-Fehlerrate | % defective hashes | Every 60 s |

## Time Window

The toolbar at the top controls all charts simultaneously:

- **Quick ranges:** 1h, 6h, 24h, 7 Tage, 30 Tage, 90 Tage, 1 Jahr
- **Custom range:** Von / Bis date pickers → Anwenden

## Block Events Table

Hidden until `Found Blocks > 0`. When a block is found, the table records:
- Exact timestamp
- Cumulative block number
- BTC price in EUR and USD **at the moment of the find**
- EUR and USD value of the 3.125 BTC reward

This data is stored permanently in `data/monitor.db` and serves as documentation for tax purposes.

## Data Retention

| Data | Resolution | Retention |
|------|-----------|-----------|
| Miner metrics | 1 row / minute | 30 days |
| BTC price | 1 row / day | 365 days |
| Block events | 1 row / block found | Forever |

## Storage

SQLite database at `./data/monitor.db`. At 1 row/minute:
- ~1.4 MB/day of miner data → purged after 30 days → steady state ~42 MB
- Price data: 365 rows/year → negligible

## API Endpoints

All endpoints return JSON. Accessible at `http://<server-ip>:8080`.

| Endpoint | Description |
|----------|-------------|
| `GET /api/now` | Current metrics + BTC price + block value |
| `GET /api/history?range=24h` | Miner metrics for time window |
| `GET /api/history?start=<ts>&end=<ts>` | Miner metrics for Unix timestamp range |
| `GET /api/prices?range=30d` | BTC price history |
| `GET /api/blocks` | All found block events |
| `GET /api/stats` | All-time aggregated statistics |
