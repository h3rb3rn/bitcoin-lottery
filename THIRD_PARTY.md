# Third-Party Notices

This project builds on, bundles, or connects to the following third-party software and services. Each entry lists the component, its origin, license, and how it is used in this stack.

---

## Mining Engine

### BFGMiner
| | |
|--|--|
| **Repository** | https://github.com/luke-jr/bfgminer |
| **Fork author** | Luke Dashjr |
| **Original** | CGMiner by Con Kolivas (https://github.com/ckolivas/cgminer) |
| **License** | GNU General Public License v3.0 (GPL-3.0) |
| **Used as** | Mining engine; compiled from source in `Dockerfile` with `--enable-nanofury` |

BFGMiner is a fork of CGMiner with extended FPGA and ASIC driver support. This project uses the `nanofury` driver (device name `NFY`), which sends SPI commands as HID feature reports over libusb to the Bitfury chip via an MCP2210 USB-to-SPI bridge. The binary is not distributed — it is built from source at Docker image build time.

> Because BFGMiner is licensed under GPL-3.0, any modifications to BFGMiner source code distributed as part of a Docker image must also be made available under GPL-3.0. This project applies no patches to BFGMiner source; the upstream repository is cloned and compiled unmodified.

---

## Dashboard Frontend

### Chart.js
| | |
|--|--|
| **Repository** | https://github.com/chartjs/Chart.js |
| **Authors** | Chart.js contributors |
| **License** | MIT License |
| **Version** | 4.x (loaded via jsDelivr CDN) |
| **Used as** | Hashrate, BTC price, and hardware error rate charts in `monitor/index.html` |

Loaded at runtime from `https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js`. No local copy is bundled.

---

## Runtime & Standard Library

### Python 3.11 — Standard Library
| | |
|--|--|
| **Homepage** | https://www.python.org/ |
| **Authors** | Python Software Foundation and contributors |
| **License** | Python Software Foundation License (PSF) — compatible with Apache 2.0 |
| **Used as** | Monitor application runtime (`monitor/app.py`, `monitor/adapters.py`) |

Only standard library modules are used: `http.server`, `sqlite3`, `smtplib`, `threading`, `urllib.request`, `json`, `socket`. No third-party Python packages are installed.

### SQLite
| | |
|--|--|
| **Homepage** | https://www.sqlite.org/ |
| **Authors** | D. Richard Hipp and contributors |
| **License** | Public Domain |
| **Used as** | Embedded time-series database for metrics and BTC price history (`data/monitor.db`) |

Accessed via Python's built-in `sqlite3` module. No separate installation required.

---

## Container Base Image

### Debian bookworm-slim
| | |
|--|--|
| **Homepage** | https://www.debian.org/ |
| **Authors** | Debian Project |
| **License** | Each package carries its own license (all DFSG-free) |
| **Used as** | Base image for the BFGMiner container (`FROM debian:bookworm-slim`) |

---

## BFGMiner Build-Time Dependencies

These libraries are installed inside the Docker build stage via `apt-get` to compile BFGMiner from source. They are present in the final image only as shared libraries linked by the BFGMiner binary.

| Library | Authors | License | Role in BFGMiner |
|---------|---------|---------|------------------|
| **libcurl** | Daniel Stenberg and contributors | MIT/curl License | Pool connectivity (HTTP/Stratum) |
| **libjansson** | Petri Lehtinen | MIT License | JSON protocol parsing |
| **libusb-1.0** | Johannes Erdfelt, Nathan Hjelm, and contributors | LGPL-2.1+ | USB device access for the nanofury driver |
| **libhidapi** | Alan Ott / Signal 11 Software | GPL-3.0 / BSD / HIDAPI (triple-licensed) | HID feature reports for MCP2210 SPI bridge |
| **libevent** | Niels Provos, Nick Mathewson, and contributors | BSD-3-Clause | Event loop |
| **uthash** | Troy D. Hanson | BSD Revised (1-Clause) | Hash table macros |
| **libncurses5** | Thomas Dickey and contributors | MIT (X11) | Terminal UI |
| **libudev** (systemd) | systemd contributors | LGPL-2.1+ | USB device enumeration |

---

## External Services

### solo.ckpool.org — Solo Mining Pool
| | |
|--|--|
| **Homepage** | https://solo.ckpool.org |
| **Operator** | Con Kolivas |
| **Protocol** | Stratum v1 over TCP |
| **Fee** | 0% (solo payouts go directly to `MINER_WALLET`) |
| **Used as** | Mining pool; configured via `MINER_POOL_URL` in `.env` |

ckpool is open-source server software (https://bitbucket.org/ckolivas/ckpool), also by Con Kolivas, licensed under GPL-3.0. Connection to solo.ckpool.org is a runtime configuration choice — any Stratum-compatible solo pool can be substituted.

### CoinGecko API
| | |
|--|--|
| **Homepage** | https://www.coingecko.com/en/api |
| **Operator** | CoinGecko |
| **Authentication** | None (public endpoint) |
| **Used as** | BTC/EUR and BTC/USD price feed, fetched once every 24 hours by the monitor |

Endpoint used: `https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=eur,usd`

No API key is required for this endpoint at the current rate limit. CoinGecko's public API terms of service apply.

---

## License Compatibility Note

This project is released under the **Apache License 2.0**. The Apache 2.0 license applies only to the original code in this repository (`monitor/`, `scripts/`, `udev/`, `docker-compose.yml`, `Dockerfile`). It does not relicense any of the third-party components listed above, which retain their respective licenses.

BFGMiner (GPL-3.0) is compiled and run as a separate process inside its own container. It is not linked against or incorporated into the monitor application code. This separation preserves the GPL boundary.
