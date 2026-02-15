/*
 * Serial Bridge - USB <-> Camera UART
 *
 * Usa SoftwareSerial nos pinos 2/3 pra comunicar com a camera.
 * Hardware Serial (USB) fica livre pro PC.
 *
 * === FIACAO ===
 *
 *   Arduino Pin 2  <-- Camera TX (fio amarelo/verde que sai dados)
 *   Arduino Pin 3  --> Camera RX (fio que recebe comandos)
 *   Arduino GND    --- Camera GND
 *
 *   TIRAR o jumper RESET-GND! O ATmega precisa rodar.
 *
 * === IMPORTANTE ===
 * Camera opera em 3.3V, Arduino em 5V.
 * - Camera TX -> Pin 2: OK direto (3.3V eh lido como HIGH pelo Arduino)
 * - Pin 3 -> Camera RX: IDEALMENTE usar divisor de tensao:
 *     Pin 3 --[1K]--+--[2K]-- GND
 *                    |
 *                    +------> Camera RX
 *   Isso converte 5V -> 3.3V. SEM DIVISOR pode funcionar
 *   mas pode danificar a camera a longo prazo.
 *
 * === BAUD ===
 * 115200 no SoftwareSerial pode perder bytes.
 * Se tiver problemas, tente 57600 ou use AltSoftSerial.
 */

#include <SoftwareSerial.h>

#define CAM_RX_PIN 2   // Arduino recebe da camera (Camera TX -> aqui)
#define CAM_TX_PIN 3   // Arduino envia pra camera (aqui -> Camera RX)
#define BAUD 115200

SoftwareSerial camSerial(CAM_RX_PIN, CAM_TX_PIN);

void setup() {
  Serial.begin(BAUD);       // USB <-> PC
  camSerial.begin(BAUD);    // Pinos 2/3 <-> Camera

  Serial.println("=================================");
  Serial.println("  SERIAL BRIDGE ATIVO");
  Serial.println("  USB <-> Camera UART");
  Serial.println("  Baud: 115200");
  Serial.println("  Cam RX pin: 2, Cam TX pin: 3");
  Serial.println("=================================");
}

void loop() {
  // Camera -> PC (prioridade: nao perder dados da camera)
  while (camSerial.available()) {
    Serial.write(camSerial.read());
  }

  // PC -> Camera
  while (Serial.available()) {
    byte b = Serial.read();
    camSerial.write(b);
  }
}
