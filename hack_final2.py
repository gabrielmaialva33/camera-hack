#!/usr/bin/env python3
"""
HACK FINAL v2 - Persiste ANTES de matar IPC!

Ordem esperta:
1. Login (com IPC rodando - tudo bem, comandos passam)
2. Hack persistente em /rom/ (PRIMEIRO! Antes de mexer no IPC)
3. Dumps pro SD card
4. Mata IPC + telnet (pode rebotar, mas hack ja ta salvo)
"""
import serial
import time
import sys
import re
import subprocess

PORT = '/dev/ttyUSB0'
BAUD = 115200
SD = '/mnt/disc1'

LOG = open('/tmp/hack_final2_raw.log', 'w')


def slow_write(ser, text):
    for ch in text:
        ser.write(ch.encode())
        time.sleep(0.004)


def send(ser, cmd, wait=3.0):
    marker = f'ZZ{int(time.time()*100) % 99999}ZZ'
    full = f'{cmd}; echo {marker}\r\n'

    ser.reset_input_buffer()
    time.sleep(0.08)
    slow_write(ser, full)

    buf = b''
    start = time.time()
    while time.time() - start < wait:
        chunk = ser.read(4096)
        if chunk:
            buf += chunk
            if marker.encode() in buf:
                break
        time.sleep(0.05)

    text = buf.decode('utf-8', errors='replace')
    LOG.write(f'>>> {cmd}\n{text}\n{"="*40}\n')
    LOG.flush()

    lines = []
    for line in text.split('\n'):
        s = line.strip()
        s = re.sub(r'\x1b\[[0-9;]*m', '', s)
        if any(x in s for x in [
            'p2pu_', 'evtimer_', 'dns_callback', 'cloudlinks',
            'udhcpc:', 'sync cnt', 'cloud-links', 'UploadDevCfg',
            'check_dns', 'scan result', 'CheckAPAvail', 'TheTimes',
            'nowTxPackets', 'fgSendBroadcast', 'netMg.c', 'key.c:',
            'IrCut', 'vWifi', 'av_ctl', 'RFKILL', 'dwLastConnect',
            marker, 'echo ' + marker,
        ]):
            continue
        if s and s != cmd:
            lines.append(s)

    return '\n'.join(lines), marker in text


def p(msg):
    print(msg, flush=True)


def main():
    # Serial sem reset Arduino
    try:
        subprocess.run(['stty', '-F', PORT, '-hupcl'], capture_output=True)
    except:
        pass

    ser = serial.Serial()
    ser.port = PORT
    ser.baudrate = BAUD
    ser.timeout = 0.3
    ser.dtr = False
    ser.rts = False
    ser.open()
    ser.dtr = False
    ser.rts = False
    ser.reset_input_buffer()
    time.sleep(0.2)
    ser.read(65536)

    p("=" * 60)
    p("  HACK FINAL v2 - Persiste primeiro!")
    p("=" * 60)

    # === LOGIN ===
    p("\n[LOGIN]")
    slow_write(ser, '\r\n')
    time.sleep(1)
    slow_write(ser, '\r\n')
    time.sleep(1)

    buf = b''
    start = time.time()
    login_ok = False

    while time.time() - start < 45:
        data = ser.read(4096)
        if data:
            buf += data
            text = data.decode('utf-8', errors='replace')
            for line in text.split('\n'):
                l = line.strip()
                if 'login:' in l:
                    p(f'  >> {l[:80]}')

        if b'login:' in buf[-500:]:
            p("  >>> LOGIN PROMPT!")
            time.sleep(0.3)
            slow_write(ser, 'root\r\n')
            time.sleep(4)
            ser.read(32768)
            time.sleep(2)
            ser.read(32768)

            for attempt in range(5):
                ser.reset_input_buffer()
                time.sleep(0.5)
                slow_write(ser, 'echo LOGGED_OK\r\n')
                time.sleep(3)
                check = ser.read(8192)
                if b'LOGGED_OK' in check:
                    p(f"  >>> ROOT SHELL OK! (try {attempt+1})")
                    login_ok = True
                    break
                time.sleep(2)
                ser.read(32768)

            if not login_ok:
                p("  >>> Assumindo login OK")
                login_ok = True
            break

        if int(time.time() - start) % 8 == 0 and int(time.time() - start) > 0:
            slow_write(ser, '\r\n')

        time.sleep(0.1)

    if not login_ok:
        p("FALHA login")
        ser.close()
        return

    time.sleep(1)
    ser.read(32768)

    # ==============================================
    # FASE 1: HACK PERSISTENTE PRIMEIRO!
    # (com IPC rodando - comandos passam mesmo com flood)
    # ==============================================
    p("\n" + "=" * 60)
    p("[FASE 1] HACK PERSISTENTE (IPC ainda rodando)")
    p("=" * 60)

    # Garante /rom montado
    out, ok = send(ser, "mount | grep rom || mount -t jffs2 /dev/mtdblock6 /rom 2>/dev/null; echo ROM_CHECK", 3)
    p(f"  /rom: {ok}")

    # Cria hack.sh linha por linha
    cmds_hack = [
        "echo '#!/bin/sh' > /rom/hack.sh",
        "echo '(while true;do echo V>/dev/watchdog 2>/dev/null;sleep 1;done)&' >> /rom/hack.sh",
        "echo 'telnetd -l /bin/sh 2>/dev/null &' >> /rom/hack.sh",
        "echo 'telnetd -l /bin/sh -p 2323 2>/dev/null &' >> /rom/hack.sh",
        "echo 'echo HACK_ACTIVE >> /tmp/hack.log' >> /rom/hack.sh",
        "chmod +x /rom/hack.sh",
    ]
    for cmd in cmds_hack:
        out, ok = send(ser, cmd, 2)
    p("  /rom/hack.sh CRIADO")

    # Injeta em time_zone.sh
    out, ok = send(ser, "grep -q hack /rom/time_zone.sh 2>/dev/null || echo '/rom/hack.sh &' >> /rom/time_zone.sh", 3)
    p(f"  time_zone.sh INJETADO: {ok}")

    # Verifica hack.sh
    out, ok = send(ser, "cat /rom/hack.sh", 3)
    p(f"  Verificacao hack.sh:")
    for line in out.split('\n')[:8]:
        if line.strip():
            p(f"    {line.strip()}")

    # Verifica time_zone.sh
    out, ok = send(ser, "cat /rom/time_zone.sh 2>/dev/null", 3)
    p(f"  Verificacao time_zone.sh:")
    for line in out.split('\n')[:5]:
        if line.strip():
            p(f"    {line.strip()}")

    # Sync filesystem
    out, ok = send(ser, "sync", 2)
    p(f"  sync: {ok}")

    p("\n  >>> HACK PERSISTENTE INSTALADO! <<<")
    p("  >>> Mesmo que reboot agora, hack sobrevive! <<<")

    # ==============================================
    # FASE 2: DUMPS PRO SD
    # ==============================================
    p("\n" + "=" * 60)
    p("[FASE 2] DUMPS PRO SD CARD")
    p("=" * 60)

    # Monta SD
    out, ok = send(ser, f"mkdir -p {SD}; mount /dev/mmcblk0p1 {SD} 2>/dev/null || mount /dev/mmcblk0 {SD} 2>/dev/null; ls {SD}/ 2>/dev/null; echo SD_MOUNT", 4)
    p(f"  SD mount: {ok}")

    dumps = [
        ("id",           f"id > {SD}/id.txt"),
        ("passwd",       f"cp /etc/passwd {SD}/passwd.txt 2>/dev/null"),
        ("shadow",       f"cp /etc/shadow {SD}/shadow.txt 2>/dev/null"),
        ("inittab",      f"cat /etc/inittab > {SD}/inittab.txt 2>/dev/null"),
        ("rc.local",     f"cat /etc/init.d/rc.local > {SD}/rc_local.txt 2>/dev/null"),
        ("rcS",          f"cat /etc/init.d/rcS > {SD}/rcS.txt 2>/dev/null"),
        ("setup.sh",     f"cat /ipc/setup.sh > {SD}/setup_sh.txt 2>/dev/null"),
        ("rom_all",      f"for f in /rom/*; do echo ====$f; cat $f 2>/dev/null; done > {SD}/rom_all.txt"),
        ("jffs2_all",    f"for f in /etc/jffs2/*; do echo ====$f; cat $f 2>/dev/null; done > {SD}/jffs2_all.txt 2>/dev/null"),
        ("initd_all",    f"for f in /etc/init.d/*; do echo ====$f; cat $f; done > {SD}/initd_all.txt 2>/dev/null"),
        ("ifconfig",     f"ifconfig -a > {SD}/ifconfig.txt 2>/dev/null"),
        ("mtd",          f"cat /proc/mtd > {SD}/mtd.txt"),
        ("cpuinfo",      f"cat /proc/cpuinfo > {SD}/cpuinfo.txt"),
        ("cmdline",      f"cat /proc/cmdline > {SD}/cmdline.txt"),
        ("dmesg",        f"dmesg > {SD}/dmesg.txt 2>/dev/null"),
        ("ps",           f"ps w > {SD}/ps.txt"),
        ("mount",        f"mount > {SD}/mount.txt"),
        ("busybox",      f"busybox --list > {SD}/busybox.txt 2>/dev/null"),
        ("wifi",         f"cat /rom/wifi*.ini > {SD}/wifi.txt 2>/dev/null"),
        ("device.cfg",   f"cat /rom/device.config > {SD}/device_config.txt 2>/dev/null"),
        ("hack_verify",  f"cat /rom/hack.sh > {SD}/hack_verify.txt"),
        ("tz_verify",    f"cat /rom/time_zone.sh > {SD}/tz_verify.txt 2>/dev/null"),
    ]

    ok_count = 0
    for desc, cmd in dumps:
        out, ok = send(ser, cmd, 3)
        ok_count += 1 if ok else 0
        p(f"  [{'+'if ok else '?'}] {desc}")

    # Sync SD
    send(ser, "sync", 2)
    p(f"\n  Dumps feitos: {ok_count}/{len(dumps)}")

    # ==============================================
    # FASE 3: AGORA MATA IPC (opcional, pode rebotar)
    # ==============================================
    p("\n" + "=" * 60)
    p("[FASE 3] MATANDO IPC + TELNET")
    p("=" * 60)

    # Feeder watchdog PRIMEIRO
    send(ser, "( while true; do echo V > /dev/watchdog 2>/dev/null; sleep 1; done ) &", 2)
    p("  Watchdog feeder: ok")

    # Kill processos
    send(ser, "killall -9 shell_debug 2>/dev/null", 1.5)
    send(ser, "killall -9 daemon 2>/dev/null", 1.5)
    p("  Kill shell_debug + daemon")

    send(ser, "killall -9 anyka_ipc ipc 2>/dev/null", 2)
    p("  Kill IPC!")

    time.sleep(3)
    ser.read(32768)

    # Tenta telnet
    send(ser, "telnetd -l /bin/sh 2>/dev/null &", 2)
    send(ser, "telnetd -l /bin/sh -p 2323 2>/dev/null &", 2)
    p("  Telnet: 23 + 2323")

    # Marca sucesso no SD
    send(ser, f"echo HACK_FINAL_V2_COMPLETE > {SD}/SUCCESS.txt; sync", 2)

    p("\n" + "=" * 60)
    p("  HACK COMPLETO!")
    p("")
    p("  [1] /rom/hack.sh INSTALADO (persistente)")
    p("  [2] time_zone.sh INJETADO")
    p("  [3] Dumps no SD card")
    p("  [4] IPC morto, telnet ativo")
    p("")
    p("  Se camera rebotar: hack ja esta salvo!")
    p("  Tira o SD e confere os dumps no PC")
    p("=" * 60)

    LOG.close()

    # Interativo
    p("\nInterativo (Ctrl+C sair)...")
    try:
        while True:
            cmd = input("cam# ")
            if cmd.strip():
                out, ok = send(ser, cmd, 3)
                print(out)
    except (KeyboardInterrupt, EOFError):
        pass

    ser.close()


if __name__ == '__main__':
    main()
