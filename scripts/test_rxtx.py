#!/usr/bin/env python3
"""
Teste de RX e TX separados para comunicação serial com a câmera.
Fase 1: RX puro (só escuta por 15s)
Fase 2: TX+RX (envia dados e verifica eco/resposta)
"""
import serial
import time
import sys

PORT = '/dev/ttyUSB0'
BAUD = 115200
TIMEOUT = 0.5

def test_rx(duration=15):
    """Fase 1: Só escuta - verifica se recebe dados da câmera"""
    print("=" * 60)
    print("FASE 1: TESTE RX (recebendo dados da câmera)")
    print(f"Escutando {PORT} @ {BAUD} por {duration}s...")
    print("=" * 60)

    ser = serial.Serial(PORT, BAUD, timeout=TIMEOUT)
    ser.reset_input_buffer()

    total_bytes = 0
    start = time.time()

    while time.time() - start < duration:
        data = ser.read(4096)
        if data:
            total_bytes += len(data)
            # Mostra texto legível
            try:
                text = data.decode('utf-8', errors='replace')
                sys.stdout.write(text)
                sys.stdout.flush()
            except:
                print(f"[{len(data)} bytes binários]", end='')

        elapsed = time.time() - start
        remaining = duration - elapsed
        if remaining > 0 and remaining % 5 < 0.6 and not data:
            print(f"\r[RX] {elapsed:.0f}s - {total_bytes} bytes recebidos", end='', flush=True)

    ser.close()

    print(f"\n{'=' * 60}")
    print(f"RX RESULTADO: {total_bytes} bytes recebidos em {duration}s")
    if total_bytes > 0:
        print("✓ RX FUNCIONANDO - câmera está enviando dados")
    else:
        print("✗ RX FALHOU - nenhum dado recebido da câmera")
    print(f"{'=' * 60}\n")
    return total_bytes > 0


def test_tx():
    """Fase 2: Envia dados e verifica resposta"""
    print("=" * 60)
    print("FASE 2: TESTE TX (enviando dados para câmera)")
    print(f"Porta: {PORT} @ {BAUD}")
    print("=" * 60)

    ser = serial.Serial(PORT, BAUD, timeout=1)
    ser.reset_input_buffer()

    # Teste 2a: Enviar Enter simples e ver se gera resposta
    print("\n[TX Test A] Enviando 3x Enter...")
    for i in range(3):
        ser.write(b'\r\n')
        time.sleep(0.3)

    time.sleep(1)
    response_a = ser.read(4096)
    print(f"  Enviado: 3x \\r\\n")
    print(f"  Recebido: {len(response_a)} bytes")
    if response_a:
        text = response_a.decode('utf-8', errors='replace')
        print(f"  Conteúdo: {repr(text[:200])}")

    # Teste 2b: Enviar "root\r\n" (login)
    print("\n[TX Test B] Enviando 'root' + Enter...")
    ser.reset_input_buffer()
    ser.write(b'root\r\n')
    time.sleep(2)

    response_b = ser.read(4096)
    print(f"  Enviado: root\\r\\n")
    print(f"  Recebido: {len(response_b)} bytes")
    if response_b:
        text = response_b.decode('utf-8', errors='replace')
        print(f"  Conteúdo: {repr(text[:300])}")

    # Teste 2c: Enviar comando simples
    print("\n[TX Test C] Enviando 'id' + Enter...")
    ser.reset_input_buffer()
    ser.write(b'id\r\n')
    time.sleep(2)

    response_c = ser.read(4096)
    print(f"  Enviado: id\\r\\n")
    print(f"  Recebido: {len(response_c)} bytes")
    if response_c:
        text = response_c.decode('utf-8', errors='replace')
        print(f"  Conteúdo: {repr(text[:300])}")

    # Teste 2d: Loopback byte-a-byte
    print("\n[TX Test D] Teste de integridade TX (envia 'ABCDEF' e verifica eco)...")
    ser.reset_input_buffer()
    test_str = b'ABCDEF'
    ser.write(test_str)
    time.sleep(1)

    response_d = ser.read(4096)
    print(f"  Enviado: {test_str}")
    print(f"  Recebido: {len(response_d)} bytes")
    if response_d:
        text = response_d.decode('utf-8', errors='replace')
        print(f"  Conteúdo: {repr(text[:200])}")
        # Verifica se o eco está correto
        if test_str in response_d:
            print("  ✓ Eco perfeito!")
        else:
            print("  ⚠ Eco com corrupção ou sem eco (normal se câmera não ecoa)")

    ser.close()

    total_rx = len(response_a) + len(response_b) + len(response_c) + len(response_d)
    print(f"\n{'=' * 60}")
    print(f"TX RESULTADO: {total_rx} bytes recebidos em resposta aos envios")
    if total_rx > 10:
        print("✓ TX FUNCIONANDO - câmera responde aos comandos")
    elif total_rx > 0:
        print("⚠ TX PARCIAL - alguma resposta mas pode ter corrupção")
    else:
        print("✗ TX FALHOU - nenhuma resposta da câmera aos comandos")
    print(f"{'=' * 60}\n")
    return total_rx > 0


if __name__ == '__main__':
    print("\n🔍 TESTE COMPLETO RX/TX - Câmera Anyka via CH340\n")

    rx_ok = test_rx(15)

    if rx_ok:
        print("RX OK! Testando TX agora...\n")
        tx_ok = test_tx()
    else:
        print("RX falhou. Verifique:")
        print("  1. Câmera está ligada?")
        print("  2. Arduino RESET está no GND?")
        print("  3. Camera TX → Arduino pin 1 (RXD)?")
        print("\nTentando TX mesmo assim...\n")
        tx_ok = test_tx()

    print("\n" + "=" * 60)
    print("RESUMO FINAL:")
    print(f"  RX (câmera → PC): {'✓ OK' if rx_ok else '✗ FALHOU'}")
    print(f"  TX (PC → câmera): {'✓ OK' if tx_ok else '✗ FALHOU'}")
    print("=" * 60)
