<h1 align="center">
  <br>
  🔓 Camera Hack
  <br>
</h1>

<h4 align="center">
  Root shell + persistent hack on a cheap Chinese IP camera via UART serial
</h4>

<p align="center">
  <img src="https://img.shields.io/badge/SoC-Anyka_AK3918EV330-DC143C?style=for-the-badge" alt="SoC" />
  <img src="https://img.shields.io/badge/ARM926EJ--S-64MiB_RAM-FF6347?style=for-the-badge" alt="CPU" />
  <img src="https://img.shields.io/badge/Python-3.x-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Arduino-UNO-00979D?style=for-the-badge&logo=arduino&logoColor=white" alt="Arduino" />
  <a href="https://github.com/gabrielmaialva33/camera-hack/blob/master/LICENSE">
    <img src="https://img.shields.io/github/license/gabrielmaialva33/camera-hack?style=for-the-badge&color=5D6D7E&logo=opensourceinitiative&logoColor=white" alt="License" />
  </a>
</p>

<br>

<p align="center">
  <a href="#-hardware">Hardware</a>&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;
  <a href="#-what-was-done">What Was Done</a>&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;
  <a href="#-wiring">Wiring</a>&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;
  <a href="#-usage">Usage</a>&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;
  <a href="#-flash-layout">Flash Layout</a>&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;
  <a href="#-lessons-learned">Lessons Learned</a>&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;
  <a href="#-references">References</a>
</p>

<br>

---

## 🖥 Hardware

| Component | Detail |
|:----------|:-------|
| **SoC** | Anyka AK3918EV330, ARM926EJ-S, 64MiB RAM |
| **Flash** | 8MiB SPI NOR (kh25l64), 9 MTD partitions |
| **Sensor** | SC1345 (1280x720 native, upscaled to 1920x1080) |
| **WiFi** | RTL8188FU (USB 0bda:f179) |
| **Board** | JORTAN A03AK1H1N_JW GS23 V1.0 |
| **Kernel** | Linux 4.4.192V2.1 (Aug 23 2022) |
| **UART** | 115200 8N1, console ttySAK0 |
| **Credentials** | root with empty password |

---

## ⚡ What Was Done

1. Soldered UART pads on the camera board
2. Used Arduino Uno (CH340) as SoftwareSerial bridge (pins 2/3)
3. Logged in as root via UART (no password)
4. Installed persistent hack in `/rom/` (jffs2 RW partition)
5. Telnet enabled on ports 23 and 2323
6. Dumped all system files to SD card

### Persistent Hack

```sh
# /rom/hack.sh (survives reboots)
#!/bin/sh
(while true;do echo V>/dev/watchdog 2>/dev/null;sleep 1;done)&
telnetd -l /bin/sh 2>/dev/null &
telnetd -l /bin/sh -p 2323 2>/dev/null &
```

Injected into `/rom/time_zone.sh` which runs on every boot.

---

## 🔌 Wiring

```
Camera TX (3.3V) --> Arduino Pin 2 (SoftwareSerial RX)
Camera RX        <-- Arduino Pin 3 (SoftwareSerial TX)
Camera GND       --- Arduino GND

Voltage divider on Pin 3 -> Camera RX (5V to 3.3V):
  Pin 3 --[1K]--+--[2K]-- GND
                 |
                 +--> Camera RX
```

> [!WARNING]
> Camera operates at 3.3V, Arduino at 5V. Without the voltage divider it may work but can damage the camera long-term.

---

## 🚀 Usage

### Prerequisites

- Python 3.x + `pyserial` (`pip install pyserial`)
- Arduino CLI (`arduino-cli`)
- Arduino Uno with CH340

### Run

```bash
# 1. Upload serial bridge to Arduino
arduino-cli compile -b arduino:avr:uno arduino/serial_bridge/
arduino-cli upload -b arduino:avr:uno -p /dev/ttyUSB0 arduino/serial_bridge/

# 2. Run the hack (camera can already be powered on)
sudo python3 hack_final2.py
```

---

## 💾 Flash Layout

| Partition | Size | Mount | FS | RW |
|:----------|:-----|:------|:---|:--:|
| UBOOT (mtd0) | 200K | - | - | - |
| ENV (mtd1) | 4K | - | - | - |
| ENVBK (mtd2) | 4K | - | - | - |
| DTB (mtd3) | 48K | - | - | - |
| KERNEL (mtd4) | 1664K | - | - | - |
| ROOTFS (mtd5) | 1536K | `/` | squashfs | RO |
| **CONFIG (mtd6)** | **512K** | **`/rom`** | **jffs2** | **RW** |
| APP (mtd7) | 4224K | `/ipc`, `/usr` | squashfs | RO |

> `/rom` (CONFIG) is the only writable partition — this is where persistence lives.

---

## 🧠 Lessons Learned

| # | Lesson | Detail |
|:-:|:-------|:-------|
| 1 | **CH340 RESET+GND trick** | RX works but TX does NOT. Use SoftwareSerial bridge instead. |
| 2 | **Arduino resets on serial open** | CH340 sends DTR pulse. Fix: `DTR=False` + `stty -hupcl`. |
| 3 | **SoftwareSerial at 115200** | Drops bytes. Send char-by-char with 4ms delay. |
| 4 | **Don't need U-Boot** | Direct login works fine. Getty respawns on ttySAK0. |
| 5 | **Persist BEFORE killing IPC** | IPC holds watchdog, killing it may trigger reboot in ~10s. |
| 6 | **SD card path** | Mounts at `/mnt/disc1`, NOT `/mnt/tf/`. Only processes SD on boot if RESET button is held. |

---

## 📁 Project Structure

```
hack_final2.py              # Main hack script (the one that worked)
arduino/serial_bridge/      # SoftwareSerial bridge sketch
scripts/                    # Previous attempts and utilities
  ├── hack_v3.py            # V3 - kills IPC before persist (wrong order)
  ├── hack_slow.py          # One command at a time, long delays
  ├── uboot_hack.py         # U-Boot intercept + init=/bin/sh
  ├── reactive_hack.ino     # Arduino auto-detect "autoboot" + inject
  └── test_rxtx.py          # RX/TX diagnostic tool
dumps/                      # System file dumps from camera
```

---

## 📚 References

- [t-rekttt/yoosee-exploit](https://github.com/t-rekttt/yoosee-exploit) — Full Yoosee firmware
- [Lawliet95/ANYKA-Tuya-Hacking-Journey](https://github.com/Lawliet95/ANYKA-Tuya-Hacking-Journey) — Complete analysis
- [ricardojlrufino/anyka_v380ipcam_experiments](https://github.com/ricardojlrufino/anyka_v380ipcam_experiments) — GPIO, Python, NodeJS
- [blog.catsheavy.com](https://blog.catsheavy.com) — Jennov/Anyka hack walkthrough

---

## 📜 License

MIT — Gabriel Maia ([@gabrielmaialva33](https://github.com/gabrielmaialva33))

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=0:DC143C,100:00979D&height=80&section=footer" width="100%"/>
</p>
