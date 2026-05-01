# Hardware — NanoFury NF2

## Device

The NanoFury NF2 (sold by bitshopper.de) is a USB Bitcoin ASIC miner based on the Bitfury chip.

| Property | Value |
|----------|-------|
| USB ID | `04d8:00de` (Microchip HID controller) |
| Hashrate | ~2 GH/s |
| Power | 100 mA @ 5V USB (0.5 W) |
| Interface | USB HID (appears as a HID gamepad/input device to the OS) |
| Protocol | Custom Bitfury SPI over HID feature reports via MCP2210 bridge |
| BFGMiner driver | `nanofury` (device name `NFY`) — not the generic `bitfury` driver |
| Clock setting | `NFY:osc6_bits=54` (controls oscillator frequency; higher = more heat + hashrate) |

The chip is a first-generation Bitfury ASIC connected via an MCP2210 USB-to-SPI bridge. BFGMiner's `nanofury` driver sends SPI commands as HID feature reports over libusb, bypassing the OS HID stack entirely. This requires `libhidapi` at build time.

## The Driver Problem

The Linux kernel sees the USB HID descriptor and automatically binds the `usbhid` driver to interface `1-7:1.0`. This blocks BFGMiner from claiming the interface via libusb, causing the miner to see no devices.

### Symptoms

```
# usbhid is bound — BFGMiner cannot access the device
$ readlink /sys/bus/usb/devices/1-7:1.0/driver
../../../../../../../bus/usb/drivers/usbhid

# No Bitfury devices detected in BFGMiner logs
[2024-01-01 00:00:00] No ASIC devices detected
```

### Fix — udev Rule

The file `udev/50-nanofury.rules` (in this repository) must be installed to `/etc/udev/rules.d/`:

```bash
sudo cp udev/50-nanofury.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usb --action=add
```

The rule does two things:

1. **Sets permissions** — `MODE="0666", GROUP="plugdev"` so libusb can open the device node at `/dev/bus/usb/001/NNN`.
2. **Unbinds usbhid** — runs `echo -n 1-7:1.0 > /sys/bus/usb/drivers/usbhid/unbind` when the device is plugged in, freeing the interface for BFGMiner.

The unbind happens automatically every time the NanoFury is reconnected.

### Verify the Fix

```bash
# Should print nothing (no symlink = no driver bound)
readlink /sys/bus/usb/devices/1-7:1.0/driver

# Should show group=plugdev
ls -la /dev/bus/usb/001/
# crw-rw-r-- 1 root plugdev 189, 1 ... 002
```

## Why `privileged: true` in Docker

Docker needs `privileged: true` for two reasons:

1. `/dev:/dev` is bind-mounted so the container sees the live USB device node even after replug.
2. `libusb_detach_kernel_driver()` — even with usbhid already unbound via udev, BFGMiner calls this as a safety measure. It requires elevated capabilities which `privileged` provides.

## Clock Tuning

The `osc6_bits=54` parameter passed via `--set bitfury:osc6_bits=54` controls the oscillator frequency. The valid range is roughly 48–56:

| Value | Hashrate | Temperature |
|-------|----------|-------------|
| 48 | lower | cooler |
| 54 | ~2 GH/s | moderate |
| 56 | higher | hot, may error |

Adjust in `docker-compose.yml` under `command:` — the parameter name is `NFY:osc6_bits=N`.

## Build Dependencies

The Dockerfile requires these packages beyond standard BFGMiner dependencies:

| Package | Reason |
|---------|--------|
| `libhidapi-dev` | Required by the `nanofury` driver |
| `uthash-dev` | Required by BFGMiner configure |
| `libevent-dev` | Required by BFGMiner configure |

`git://` submodule URLs must be rewritten to `https://` before the build (`git config --global url."https://".insteadOf git://`) because GitHub disabled the git protocol in 2022.
