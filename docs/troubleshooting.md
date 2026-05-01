# Troubleshooting

## BFGMiner Sees No Devices

**Symptom:** Logs show `No ASIC devices detected` or `0 devices`.

**Check 1 — usbhid still bound:**
```bash
readlink /sys/bus/usb/devices/1-7:1.0/driver
# If this prints a path ending in usbhid, the driver is still attached.
```

Fix: Apply the udev rule (see [hardware.md](hardware.md)) and replug the NanoFury, or unbind manually:
```bash
echo -n "1-7:1.0" | sudo tee /sys/bus/usb/drivers/usbhid/unbind
```

**Check 2 — device not visible in container:**
```bash
docker exec -it nanofury_lottery lsusb
# Should list: Microchip Technology, Inc. NanoFury NF2
```

If not listed, the `/dev` bind mount may have stale entries. Restart Docker:
```bash
docker compose down && docker compose up -d
```

**Check 3 — device node permissions:**
```bash
ls -la /dev/bus/usb/001/
# The NanoFury node (e.g. 002) should have group=plugdev or mode=0666
```

If still `root:root 664`, the udev rule did not apply. Reload manually:
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --attr-match=idVendor=04d8
```

---

## Container Exits Immediately

```bash
docker compose logs
```

Common causes:

| Log message | Cause | Fix |
|-------------|-------|-----|
| `No devices found` | usbhid still bound or device node not accessible | See above |
| `Failed to connect to pool` | Network/pool unreachable | Check internet; verify `MINER_POOL_URL` in `.env` |
| `libusb: error -3` | Permission denied on `/dev/bus/usb/...` | Fix device node permissions (udev rule) |
| `configure: error: ...` | Build failure | Rebuild image: `docker compose build --no-cache` |

---

## Device Number Changes After Replug

The USB device number (e.g. `001/002`) changes every time the NanoFury is plugged in. The `/dev:/dev` bind mount in Docker is live, so the new device node appears automatically inside the container. The udev rule matches by USB ID, not by port, so it applies regardless of which number is assigned.

---

## BFGMiner Detects Device but Hashrate is 0

The Bitfury chip ramps up over ~30 seconds. Check with:
```bash
docker exec nanofury_lottery bfgminer-rpc devs
# Look for: Name=NFY, Status=Alive, MHS av > 0
```

If hashrate stays 0 or `Device Hardware%` stays above 20%, try a lower `osc6_bits`:
```yaml
# docker-compose.yml
command:
  - "--set"
  - "NFY:osc6_bits=50"   # was 54
```

Restart after changing: `docker compose up -d`

---

## Rebuilding the Image

BFGMiner is built from source during `docker build`. If the upstream repository has changed or the build is broken:

```bash
docker compose build --no-cache
docker compose up -d
```

The build takes ~5 minutes on first run.

---

## Monitoring via BFGMiner API

Port 4028 is exposed on `127.0.0.1` (not public) for monitoring:

```bash
# Hashrate summary
docker exec nanofury_lottery bfgminer-rpc summary

# Device details (hashrate, errors)
docker exec nanofury_lottery bfgminer-rpc devs

# Pool connection status
docker exec nanofury_lottery bfgminer-rpc pools

# Interactive TUI (press q to quit)
docker attach nanofury_lottery   # then Ctrl+P Ctrl+Q to detach without stopping
```

A healthy device shows:
```
Name=NFY, Status=Alive, MHS av=~2000-4000, Device Hardware%=<5
```

---

## Checking Host USB State

```bash
# Full NanoFury USB info
lsusb -v -d 04d8:00de 2>/dev/null

# Which driver is bound to the HID interface
for d in /sys/bus/usb/devices/1-*:1.0; do
  v=$(cat $d/../idVendor 2>/dev/null)
  [ "$v" = "04d8" ] && echo "$d: $(readlink $d/driver | xargs basename)"
done
```
