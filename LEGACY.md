# Legacy Hardware Integration

Practical guide for connecting end-of-life ASIC miners and older server hardware to this stack in a Proxmox/LXC environment. The monitor's adapter layer normalizes heterogeneous APIs, so hardware from different eras and manufacturers can feed into the same dashboard and alerting pipeline.

---

## Proxmox / LXC Considerations

### USB Passthrough to an LXC Container

Proxmox LXC containers share the host kernel. USB devices passed through are accessed via device nodes — no PCIe passthrough required.

**Step 1 — Identify the device on the host:**

```bash
lsusb
# e.g.: Bus 001 Device 003: ID 04d8:00de Microchip Technology, Inc.
```

Note the bus and device numbers (e.g., `001/003`).

**Step 2 — Find the major:minor numbers:**

```bash
ls -la /dev/bus/usb/001/003
# crw-rw-r-- 1 root plugdev 189, 3 ...
# major=189, minor=3
```

**Step 3 — Add to the LXC config** (`/etc/pve/lxc/<CTID>.conf`):

```conf
lxc.cgroup2.devices.allow: c 189:* rwm
lxc.mount.entry: /dev/bus/usb/001/003 dev/bus/usb/001/003 none bind,optional,create=file
```

Repeat for each USB device. After editing, restart the container.

**Step 4 — Install udev rules on the Proxmox host** (not inside the container):

```bash
sudo cp udev/50-nanofury.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usb --action=add
```

The LXC container sees device node changes in real time because it shares the host kernel.

### Privileged vs. Unprivileged Containers

- **Privileged** (`unprivileged: 0`): simplest path for USB + libusb. `privileged: true` in `docker-compose.yml` maps cleanly.
- **Unprivileged** (`unprivileged: 1`): requires explicit cgroup device allowances (Step 3 above) and the `CAP_NET_ADMIN` / `CAP_SYS_ADMIN` capabilities. USB access is possible but more fragile across kernel updates.

For mining hardware, privileged containers are the pragmatic default.

---

## Network-Attached Legacy ASICs

Miners like the Antminer S9 have a built-in web interface and expose a CGI/JSON API over the local network. No USB passthrough is needed — add them as network miners in `.env`:

```bash
MINER_2_NAME=Antminer S9
MINER_2_TYPE=antminer
MINER_2_HOST=192.168.1.50     # static IP or DHCP reservation
MINER_2_PORT=80
MINER_2_USER=root
MINER_2_PASSWORD=root
```

The `AntminerAdapter` polls `/cgi-bin/minerStatus.cgi` with Basic Auth and normalizes GH/s to MH/s for the shared dashboard.

### Assigning Static IPs

Assign static IPs via DHCP reservation (preferred) or set a static IP in the miner's web UI. Miners that reboot frequently benefit from reservations so the `MINER_N_HOST` value stays valid.

---

## Supported Legacy Hardware

| Manufacturer | Type | Adapter | Notes |
|-------------|------|---------|-------|
| NanoFury NF2 | USB ASIC | `bfgminer` | Requires udev rule + USB passthrough |
| GekkoScience Compac | USB ASIC | `bfgminer` | Same udev approach as NanoFury |
| Antminer U3 | USB ASIC | `cgminer` | CGMiner JSON protocol on port 4028 |
| Antminer S9 / S17 / T9 | Network ASIC | `antminer` | HTTP Basic Auth on port 80 |
| Antminer L3+ / E3 | Network ASIC | `antminer` | Same as S9 |
| Whatsminer M20 / M30 | Network ASIC | `whatsminer` | JSON-RPC on port 4028 |
| Bitaxe Ultra / Max | Network ASIC | `bitaxe` | REST API on port 80, no auth |

For any CGMiner-compatible device not listed above, try `MINER_N_TYPE=cgminer` first.

---

## USB Hub Stability

Legacy USB ASICs are sensitive to power delivery. Observed failure modes:

- **Periodic disconnects** — use a powered USB hub rated ≥ 2 A per port. Passive hubs on server motherboards often drop voltage under load.
- **usbhid rebind after replug** — the udev rule re-fires on each plug event, so reconnects are handled automatically without restarting the container.
- **Multiple devices on one host** — each device needs its own udev unbind rule if the interface path (`1-7:1.0`) differs. Check `lsusb -t` and adjust the `KERNELS` match in the udev rule accordingly.

---

## Stabilizing BFGMiner on Older Hardware

### Container Restart Policy

```yaml
restart: unless-stopped
```

BFGMiner exits if it loses the USB device. `unless-stopped` brings it back automatically. Pair with Docker healthcheck monitoring or the built-in SMTP alerting.

### Clock Tuning for Stability

Lower `osc6_bits` reduces hashrate but also reduces heat and hardware errors. For hardware running in ambient temperatures above 30 °C:

```bash
OSC6_BITS=50   # cooler, more stable
```

Monitor `hw_pct` in the dashboard — sustained values above 2% indicate thermal stress or a marginal power supply.

### Build Reproducibility

The Dockerfile clones `luke-jr/bfgminer` at build time (no pinned commit). If upstream breaks, pin to a known-good commit:

```dockerfile
RUN git clone https://github.com/luke-jr/bfgminer.git /opt/bfgminer-src && \
    git -C /opt/bfgminer-src checkout <COMMIT_SHA>
```

Run `docker compose build --no-cache` after changing the Dockerfile.

---

## Proxmox Host Maintenance

### Kernel Updates

The udev rule and USB device path are kernel-version-independent. After a kernel update:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usb --action=add
```

If the USB bus/device topology changes (path like `1-7:1.0` shifts), update the `KERNELS` value in `udev/50-nanofury.rules` to match.

### LXC Snapshot Before Updates

```bash
pct snapshot <CTID> pre-kernel-update --description "before kernel upgrade"
```

Roll back with `pct rollback <CTID> pre-kernel-update` if USB passthrough breaks after the update.

---

## Adding a Second Miner (Example Walkthrough)

Goal: add an Antminer S9 at `192.168.1.55` alongside the existing NanoFury.

**1. Verify reachability:**

```bash
curl -u root:root http://192.168.1.55/cgi-bin/minerStatus.cgi | python3 -m json.tool
```

A JSON response confirms the API is up.

**2. Add to `.env`:**

```bash
MINER_2_NAME=Antminer S9
MINER_2_TYPE=antminer
MINER_2_HOST=192.168.1.55
MINER_2_PORT=80
MINER_2_USER=root
MINER_2_PASSWORD=root
```

**3. Restart the monitor container:**

```bash
docker compose restart monitor
```

The dashboard will show a second miner panel and an updated aggregate row within 60 seconds.
