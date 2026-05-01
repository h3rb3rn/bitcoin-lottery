# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projektübersicht

Dieses Deployment betreibt einen **Bitcoin-Solo-Miner** auf einem NanoFury-USB-ASIC-Gerät. Es nutzt BFGMiner (gebaut aus dem Quellcode von luke-jr/bfgminer) in einem Docker-Container, der direkten USB-Zugriff benötigt.

- **Mining-Pool:** solo.ckpool.org (Solo-Mining)
- **Hardware:** NanoFury / Bitfury-USB-ASIC
- **Takt-Einstellung:** `osc6_bits=54` (Hardware-Clock via BFGMiner-Parameter)

## Commands

### Container

```bash
docker compose up -d          # start miner
docker compose logs -f        # live log output
docker compose down           # stop
docker compose build --no-cache && docker compose up -d  # rebuild image
```

### USB / Debugging

```bash
lsusb | grep -i "04d8"                         # verify NanoFury is on host
readlink /sys/bus/usb/devices/1-7:1.0/driver   # should be empty (no driver bound)
docker exec -it nanofury_lottery lsusb          # verify visible inside container
```

### One-Time Host Setup (required after fresh install or kernel update)

```bash
sudo cp udev/50-nanofury.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usb --action=add
```

## Architecture

```
.env                       → Pool credentials and wallet address (never commit)
.env.example               → Template without real values
docker-compose.yml         → Service definition; passes .env vars as CLI args to BFGMiner
Dockerfile                 → Builds BFGMiner from source (luke-jr/bfgminer) with --enable-bitfury
udev/50-nanofury.rules     → Host udev rule: sets USB permissions + unbinds usbhid driver
docs/                      → Human-readable documentation
```

**Data flow:** `.env` → `docker-compose.yml` environment → BFGMiner CLI arguments → Stratum connection to ckpool → Bitcoin network.

## Critical Details

- **usbhid driver conflict** — The kernel auto-binds `usbhid` to the NanoFury (HID device class 03). BFGMiner needs the interface free. The udev rule unbinds it on plug. See `docs/hardware.md`.
- **`privileged: true`** — Required for libusb inside the container to open the USB device node and call `libusb_detach_kernel_driver()`.
- **`osc6_bits=54`** — Controls Bitfury oscillator frequency. Range ~48–56; higher = more hashrate + heat.
- **Dockerfile builds from source** — Build takes ~5 minutes. If upstream `luke-jr/bfgminer` breaks, check their commit history.
- **`.env` is gitignored** — Contains wallet address and pool credentials.
