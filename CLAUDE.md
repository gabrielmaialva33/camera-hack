# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Contexto do Projeto

Hack de câmera IP barata (Yoosee/Jortan) via UART serial. O alvo é um SoC **Anyka AK3918EV330** (ARM926EJ-S, 64MiB RAM, 8MiB SPI NOR flash, Linux 4.4.192). A comunicação com a câmera é feita via Arduino Uno como bridge SoftwareSerial (115200 8N1), pois o CH340 com RESET+GND não consegue TX.

O hack foi concluído com sucesso: root shell, persistência via jffs2 (`/rom/`), telnet habilitado, dumps extraídos.

## Comandos

```bash
# Upload do bridge serial pro Arduino
arduino-cli compile -b arduino:avr:uno arduino/serial_bridge/
arduino-cli upload -b arduino:avr:uno -p /dev/ttyUSB0 arduino/serial_bridge/

# Executar o hack principal (requer sudo para acesso serial)
sudo python3 hack_final2.py
```

Dependência Python: `pyserial` (`pip install pyserial`).

## Arquitetura

### Script principal: `hack_final2.py`
O script que de fato funcionou. Opera em 3 fases sequenciais via serial:
1. **Login** — Aguarda prompt `login:`, envia `root` (sem senha), confirma shell com marcador echo
2. **Persistência** — Cria `/rom/hack.sh` (watchdog feeder + telnet) e injeta em `/rom/time_zone.sh` (executado todo boot). Feito **antes** de matar o IPC para garantir que o hack sobreviva a reboot acidental
3. **Dumps** — Salva ~22 arquivos de sistema no SD card (`/mnt/disc1`)
4. **Kill IPC** — Mata processos da câmera (anyka_ipc, shell_debug, daemon), ativa telnet, modo interativo

### Comunicação serial
- `slow_write()` — Envia char-a-char com 4ms delay (SoftwareSerial a 115200 perde bytes em rajada)
- `send()` — Envia comando com marcador único (`ZZxxxxxZZ`), filtra spam do firmware IPC (p2pu_, cloudlinks, dns_callback, etc.), retorna resposta limpa + flag de sucesso
- Arduino DTR/RTS desabilitados (`stty -hupcl` + `ser.dtr = False`) para evitar reset do CH340

### Arduino bridge: `arduino/serial_bridge/`
SoftwareSerial nos pinos 2 (RX da câmera) e 3 (TX para câmera). Hardware Serial (USB) fica livre para o PC. Loop simples bidirecional. Camera opera em 3.3V — idealmente usar divisor de tensão no pin 3.

### Scripts anteriores (`scripts/`)
Tentativas que levaram ao hack final — úteis como referência:
- `hack_v3.py` — Versão que mata IPC antes de persistir (ordem errada, risco de reboot)
- `hack_slow.py` — Envia um comando por vez com delays longos (8ms/char)
- `uboot_hack.py` — Intercepta U-Boot (janela de 1s) para bootar com `init=/bin/sh`
- `reactive_hack.ino` — Sketch Arduino que detecta "autoboot" e injeta comandos no U-Boot automaticamente
- `test_rxtx.py` — Diagnóstico de RX/TX separados

### Dumps (`dumps/`)
Arquivos extraídos do sistema da câmera (passwd, shadow, dmesg, mtd, busybox, init scripts, etc.). Referência para entender o firmware.

## Detalhes críticos do hardware

- **Flash RW**: Única partição gravável é `/rom` (mtd6, jffs2, 512K). `/etc/jffs2` é symlink para `/rom`. Rootfs é squashfs RO.
- **Persistência**: `/rom/time_zone.sh` executa todo boot — é o hook de injeção.
- **Watchdog**: O processo IPC alimenta o watchdog. Matar IPC sem iniciar feeder próprio causa reboot em ~10s.
- **SD card**: Monta em `/mnt/disc1` (não `/mnt/tf/`). Só processa SD no boot se botão RESET estiver pressionado.
- **UART**: Console em `ttySAK0`, getty respawna via inittab.
- **Credenciais**: root sem senha.
