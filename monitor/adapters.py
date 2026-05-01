"""
Miner adapters — normalize heterogeneous miner APIs into one data shape.

Each adapter implements fetch() -> dict | None.
The returned dict always has the same keys regardless of manufacturer.

Supported types (MINER_N_TYPE env var):
  bfgminer   — BFGMiner TCP socket, pipe-delimited text (NanoFury, GekkoScience, ...)
  cgminer    — CGMiner TCP socket, JSON protocol (Antminer U3, many USB ASICs)
  antminer   — Antminer HTTP CGI API + Basic Auth (S/T/L/E series)
  whatsminer — Whatsminer TCP socket, JSON protocol (M series)
  bitaxe     — Bitaxe REST API, no auth (ESP32-based open-source miners)
"""

import base64
import json
import os
import socket
import time
import urllib.request
from abc import ABC, abstractmethod


# ---------------------------------------------------------------------------
# Normalized metric keys (returned by every adapter)
# ---------------------------------------------------------------------------
# {
#   "ts":             int        Unix timestamp
#   "miner_id":       str        e.g. "miner_1"
#   "name":           str        human-readable label
#   "hashrate_avg":   float      MH/s — long-window average
#   "hashrate_short": float      MH/s — short-window (20s / 5s)
#   "hw_error_pct":   float      hardware error percentage
#   "hw_errors":      int        cumulative hardware error count
#   "work_done":      int        diff1 work / accepted shares
#   "found_blocks":   int        blocks found by this miner
#   "best_share":     float      best share difficulty ever found
#   "uptime_sec":     int        seconds since miner last (re)started
#   "pool_alive":     int        1 = pool connection up, 0 = down
#   "accepted":       int        accepted shares
#   "rejected":       int        rejected shares
#   "temp_c":         float|None chip temperature in Celsius, or None
# }


class MinerAdapter(ABC):
    def __init__(self, miner_id: str, name: str, host: str, port: int,
                 user: str = "", password: str = "", **_):
        self.miner_id = miner_id
        self.name     = name
        self.host     = host
        self.port     = port
        self.user     = user
        self.password = password

    @abstractmethod
    def fetch(self) -> dict | None:
        ...

    def _base(self) -> dict:
        return {
            "ts": int(time.time()), "miner_id": self.miner_id, "name": self.name,
            "hashrate_avg": 0.0, "hashrate_short": 0.0,
            "hw_error_pct": 0.0, "hw_errors": 0, "work_done": 0,
            "found_blocks": 0, "best_share": 0.0, "uptime_sec": 0,
            "pool_alive": 0, "accepted": 0, "rejected": 0, "temp_c": None,
        }

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name!r} @ {self.host}:{self.port})"


# ---------------------------------------------------------------------------
# BFGMiner — TCP socket, pipe-delimited text protocol
# ---------------------------------------------------------------------------

class BFGMinerAdapter(MinerAdapter):
    """BFGMiner socket RPC. Works for NanoFury, GekkoScience, Compac, etc."""

    def _rpc(self, command: str) -> str:
        with socket.create_connection((self.host, self.port), timeout=10) as s:
            s.sendall(command.encode())
            chunks = []
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
                if b"\x00" in chunk:
                    break
            return b"".join(chunks).rstrip(b"\x00").decode(errors="replace")

    @staticmethod
    def _parse(response: str) -> dict:
        result = {}
        for segment in response.split("|"):
            for pair in segment.split(","):
                if "=" in pair:
                    k, _, v = pair.partition("=")
                    result[k.strip()] = v.strip()
        return result

    def fetch(self) -> dict | None:
        try:
            devs    = self._parse(self._rpc("devs"))
            summary = self._parse(self._rpc("summary"))
            pools   = self._parse(self._rpc("pools"))
            m = self._base()
            m.update({
                "hashrate_avg":   float(devs.get("MHS av", 0)),
                "hashrate_short": float(devs.get("MHS 20s", 0)),
                "hw_error_pct":   float(devs.get("Device Hardware%", 0)),
                "hw_errors":      int(devs.get("Hardware Errors", 0)),
                "work_done":      int(devs.get("Diff1 Work", 0)),
                "found_blocks":   int(summary.get("Found Blocks", 0)),
                "best_share":     float(summary.get("Best Share", 0)),
                "uptime_sec":     int(summary.get("Elapsed", 0)),
                "pool_alive":     1 if pools.get("Status") == "Alive" else 0,
                "accepted":       int(pools.get("Accepted", 0)),
                "rejected":       int(pools.get("Rejected", 0)),
            })
            return m
        except Exception:
            return None


# ---------------------------------------------------------------------------
# CGMiner — TCP socket, JSON protocol
# ---------------------------------------------------------------------------

class CGMinerAdapter(MinerAdapter):
    """CGMiner JSON-RPC. Same port as BFGMiner but JSON framing."""

    def _rpc(self, command: str) -> dict:
        with socket.create_connection((self.host, self.port), timeout=10) as s:
            s.sendall(json.dumps({"command": command}).encode())
            data = b""
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
                if b"\x00" in chunk:
                    break
            return json.loads(data.rstrip(b"\x00").decode(errors="replace"))

    def fetch(self) -> dict | None:
        try:
            devs    = self._rpc("devs")
            summary = self._rpc("summary")
            pools   = self._rpc("pools")

            dev  = (devs.get("DEVS")    or [{}])[0]
            smry = (summary.get("SUMMARY") or [{}])[0]
            pool = (pools.get("POOLS")  or [{}])[0]

            # CGMiner may report in KH/s or MH/s depending on firmware
            mhs_av = float(dev.get("MHS av", 0))
            if mhs_av == 0:
                mhs_av = float(dev.get("KHS av", 0)) / 1000

            mhs_5s = float(dev.get("MHS 5s", 0))
            if mhs_5s == 0:
                mhs_5s = float(dev.get("KHS 5s", 0)) / 1000

            temp = dev.get("Temperature")
            m = self._base()
            m.update({
                "hashrate_avg":   mhs_av,
                "hashrate_short": mhs_5s,
                "hw_error_pct":   float(dev.get("Device Hardware%", 0)),
                "hw_errors":      int(dev.get("Hardware Errors", 0)),
                "work_done":      int(smry.get("Diff1 Work", 0)),
                "found_blocks":   int(smry.get("Found Blocks", 0)),
                "best_share":     float(smry.get("Best Share", 0)),
                "uptime_sec":     int(smry.get("Elapsed", 0)),
                "pool_alive":     1 if pool.get("Status") == "Alive" else 0,
                "accepted":       int(pool.get("Accepted", 0)),
                "rejected":       int(pool.get("Rejected", 0)),
                "temp_c":         float(temp) if temp else None,
            })
            return m
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Antminer — HTTP CGI API with Basic Auth (S/T/L/E series)
# ---------------------------------------------------------------------------

class AntminerAdapter(MinerAdapter):
    """Antminer S/T/L/E — HTTP GET /cgi-bin/minerStatus.cgi with Basic Auth."""

    def _get(self, path: str) -> dict:
        url = f"http://{self.host}:{self.port}{path}"
        creds = base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
        req = urllib.request.Request(url, headers={
            "Authorization": f"Basic {creds}",
            "User-Agent": "bitcoin-lottery-monitor/1.0",
        })
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())

    def fetch(self) -> dict | None:
        try:
            data = self._get("/cgi-bin/minerStatus.cgi")

            # Antminer reports GH/s; convert to MH/s
            ghs_av = float(data.get("GHS av", 0))
            ghs_5s = float(data.get("GHS 5s", 0))

            pools = data.get("pools") or [{}]
            pool  = pools[0]

            temps = [float(t) for t in data.get("temp", []) if t]
            temp  = max(temps) if temps else None

            m = self._base()
            m.update({
                "hashrate_avg":   ghs_av * 1000,
                "hashrate_short": ghs_5s * 1000,
                "hw_error_pct":   float(data.get("Device Hardware%", 0)),
                "hw_errors":      int(data.get("Hardware Errors", 0)),
                "work_done":      int(data.get("Diff1 Work", 0)),
                "found_blocks":   int(data.get("Found Blocks", 0)),
                "best_share":     float(data.get("Best Share", 0)),
                "uptime_sec":     int(data.get("Elapsed", 0)),
                "pool_alive":     1 if pool.get("Status") == "Alive" else 0,
                "accepted":       int(pool.get("Accepted", 0)),
                "rejected":       int(pool.get("Rejected", 0)),
                "temp_c":         temp,
            })
            return m
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Whatsminer — TCP socket, JSON protocol (M series)
# ---------------------------------------------------------------------------

class WhatsMinAdapter(MinerAdapter):
    """Whatsminer M series — JSON-RPC on port 4028, different from CGMiner."""

    def _rpc(self, command: str) -> dict:
        with socket.create_connection((self.host, self.port), timeout=10) as s:
            s.sendall(json.dumps({"cmd": command}).encode())
            data = b""
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
            return json.loads(data.decode(errors="replace"))

    def fetch(self) -> dict | None:
        try:
            devs    = self._rpc("devs")
            summary = self._rpc("summary")
            pools   = self._rpc("pools")

            dev  = (devs.get("Msg",    {}).get("DEVS",    [{}]))[0]
            smry = (summary.get("Msg", {}).get("SUMMARY", [{}]))[0]
            pool = (pools.get("Msg",   {}).get("POOLS",   [{}]))[0]

            # Whatsminer may use TH/s — try multiple keys
            mhs_av = float(smry.get("MHS av", 0))
            if mhs_av == 0:
                ths_av = float(smry.get("HS av", smry.get("THS av", 0)))
                mhs_av = ths_av * 1e6  # TH/s -> MH/s

            temp = dev.get("Temperature")
            m = self._base()
            m.update({
                "hashrate_avg":   mhs_av,
                "hashrate_short": float(smry.get("MHS 5s", 0)),
                "hw_error_pct":   float(dev.get("Device Hardware%", 0)),
                "hw_errors":      int(dev.get("Hardware Errors", 0)),
                "work_done":      int(smry.get("Diff1 Work", 0)),
                "found_blocks":   int(smry.get("Found Blocks", 0)),
                "best_share":     float(smry.get("Best Share", 0)),
                "uptime_sec":     int(smry.get("Elapsed", 0)),
                "pool_alive":     1 if pool.get("Status") == "Alive" else 0,
                "accepted":       int(pool.get("Accepted", 0)),
                "rejected":       int(pool.get("Rejected", 0)),
                "temp_c":         float(temp) if temp else None,
            })
            return m
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Bitaxe — REST API, no auth (ESP32-based open-source miners)
# ---------------------------------------------------------------------------

class BitaxeAdapter(MinerAdapter):
    """Bitaxe — HTTP GET /api/system/info, no authentication required."""

    def _get(self, path: str) -> dict:
        url = f"http://{self.host}:{self.port}{path}"
        req = urllib.request.Request(url, headers={"User-Agent": "bitcoin-lottery-monitor/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())

    def fetch(self) -> dict | None:
        try:
            info = self._get("/api/system/info")

            # Bitaxe reports hashrate in GH/s
            ghs = float(info.get("hashRate", 0))
            temp = info.get("temp")

            m = self._base()
            m.update({
                "hashrate_avg":   ghs * 1000,
                "hashrate_short": ghs * 1000,  # no short-window metric available
                "hw_error_pct":   0.0,
                "hw_errors":      int(info.get("invalidShares", 0)),
                "work_done":      int(info.get("sharesAccepted", 0)),
                "found_blocks":   0,   # Bitaxe API does not expose this
                "best_share":     float(info.get("bestDiff", 0)),
                "uptime_sec":     int(info.get("uptimeSeconds", 0)),
                "pool_alive":     1 if info.get("isOnline", False) else 0,
                "accepted":       int(info.get("sharesAccepted", 0)),
                "rejected":       int(info.get("sharesRejected", 0)),
                "temp_c":         float(temp) if temp else None,
            })
            return m
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Registry + config loader
# ---------------------------------------------------------------------------

ADAPTER_TYPES: dict[str, type[MinerAdapter]] = {
    "bfgminer":   BFGMinerAdapter,
    "cgminer":    CGMinerAdapter,
    "antminer":   AntminerAdapter,
    "whatsminer": WhatsMinAdapter,
    "bitaxe":     BitaxeAdapter,
}


def load_miners_from_env() -> list[MinerAdapter]:
    """
    Build adapter list from MINER_N_* environment variables.

    Example .env:
        MINER_1_NAME=NanoFury NF2
        MINER_1_TYPE=bfgminer
        MINER_1_HOST=nanofury_lottery
        MINER_1_PORT=4028

        MINER_2_NAME=Antminer S9
        MINER_2_TYPE=antminer
        MINER_2_HOST=192.168.1.50
        MINER_2_PORT=80
        MINER_2_USER=root
        MINER_2_PASSWORD=root

    Falls back to legacy BFGMINER_HOST/PORT if no MINER_N_* vars are set.
    """
    miners: list[MinerAdapter] = []

    for i in range(1, 11):
        name = os.environ.get(f"MINER_{i}_NAME")
        if not name:
            break
        mtype    = os.environ.get(f"MINER_{i}_TYPE", "bfgminer").lower()
        host     = os.environ.get(f"MINER_{i}_HOST", "localhost")
        port     = int(os.environ.get(f"MINER_{i}_PORT", 4028))
        user     = os.environ.get(f"MINER_{i}_USER", "root")
        password = os.environ.get(f"MINER_{i}_PASSWORD", "root")

        cls = ADAPTER_TYPES.get(mtype)
        if cls is None:
            print(f"[config] Unknown miner type '{mtype}' for '{name}', skipping."
                  f" Valid: {', '.join(ADAPTER_TYPES)}")
            continue

        miners.append(cls(
            miner_id=f"miner_{i}", name=name,
            host=host, port=port, user=user, password=password,
        ))
        print(f"[config] Registered: {name} ({mtype} @ {host}:{port})")

    # Legacy single-miner fallback
    if not miners:
        host = os.environ.get("BFGMINER_HOST", "nanofury_lottery")
        port = int(os.environ.get("BFGMINER_PORT", 4028))
        miners.append(BFGMinerAdapter(
            miner_id="miner_1", name="NanoFury NF2", host=host, port=port,
        ))
        print(f"[config] Legacy fallback: BFGMiner @ {host}:{port}")

    return miners
