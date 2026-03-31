#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ── Pin Definitions (Page 27) ──────────────────────────────
#define LED_R 9
#define LED_G 10
#define LED_B 11
#define BUZZER 8

// ── LCD Setup: 16x2, I2C address 0x27 (Page 27) ───────────
LiquidCrystal_I2C lcd(0x27, 16, 2);

// ── State Variables ────────────────────────────────────────
String inputString = "";
bool stringComplete = false;

unsigned long previousMillis = 0;
bool ledState = false;
String currentMode = "IDLE";
int blinkInterval = 1000;

// ── Setup ──────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);
  inputString.reserve(50);

  pinMode(LED_R, OUTPUT);
  pinMode(LED_G, OUTPUT);
  pinMode(LED_B, OUTPUT);
  pinMode(BUZZER, OUTPUT);

  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("ARGUS READY     ");
  lcd.setCursor(0, 1);
  lcd.print("Waiting...      ");

  setLED(0, 0, 0);
}

// ── Main Loop ──────────────────────────────────────────────
void loop() {

  while (Serial.available()) {
    char inChar = (char)Serial.read();
    if (inChar == '\n') {
      stringComplete = true;
    } else {
      inputString += inChar;
    }
  }

  if (stringComplete) {
    processMessage(inputString);
    inputString = "";
    stringComplete = false;
  }

  handleBlink();
}

// ── Message Parser (Page 28) ───────────────────────────────
void processMessage(String msg) {
  msg.trim();

  // PING → PONG heartbeat
  if (msg == "PING") {
    Serial.println("PONG");
    return;
  }

  // EXAM:START → blue 3 sec → solid green
  if (msg == "EXAM:START") {
    setLED(0, 0, 255);
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("ARGUS ACTIVE    ");
    lcd.setCursor(0, 1);
    lcd.print("Initializing... ");
    delay(3000);
    currentMode = "GREEN";
    setLED(0, 255, 0);
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("EXAM ACTIVE     ");
    lcd.setCursor(0, 1);
    lcd.print("All Clear       ");
    return;
  }

  // EXAM:END → LED off, LCD done
  if (msg == "EXAM:END") {
    currentMode = "IDLE";
    setLED(0, 0, 0);
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("EXAM COMPLETED  ");
    lcd.setCursor(0, 1);
    lcd.print("Report Ready    ");
    return;
  }

  // STATUS:GREEN → solid green
  if (msg == "STATUS:GREEN") {
    currentMode = "GREEN";
    setLED(0, 255, 0);
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("EXAM ACTIVE     ");
    lcd.setCursor(0, 1);
    lcd.print("All Clear       ");
    return;
  }

  // STATUS:YELLOW:Bx:score → slow yellow blink
  if (msg.startsWith("STATUS:YELLOW:")) {
    currentMode = "YELLOW";
    blinkInterval = 1000;
    int firstColon = msg.indexOf(':', 14);
    String bench = msg.substring(14, firstColon);
    String score = msg.substring(firstColon + 1);
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("! WATCH: " + bench + "      ");
    lcd.setCursor(0, 1);
    lcd.print("Score: " + score + " | MED  ");
    return;
  }

  // ALERT:Bx:score:HIGH → fast red blink + 2 beeps
  if (msg.startsWith("ALERT:")) {
    currentMode = "RED";
    blinkInterval = 300;
    int c1 = msg.indexOf(':');
    int c2 = msg.indexOf(':', c1 + 1);
    int c3 = msg.indexOf(':', c2 + 1);
    String bench = msg.substring(c1 + 1, c2);
    String score = msg.substring(c2 + 1, c3);
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print(">>ALERT: " + bench + "     ");
    lcd.setCursor(0, 1);
    lcd.print("Score:" + score + " |HIGH  ");
    buzz(2);
    return;
  }
}

// ── Non-blocking Blink Handler ─────────────────────────────
void handleBlink() {
  if (currentMode == "GREEN") {
    setLED(0, 255, 0);
    return;
  }

  unsigned long currentMillis = millis();
  if (currentMillis - previousMillis >= blinkInterval) {
    previousMillis = currentMillis;
    ledState = !ledState;

    if (currentMode == "YELLOW") {
      if (ledState) setLED(255, 255, 0);
      else setLED(0, 0, 0);
    }

    if (currentMode == "RED") {
      if (ledState) setLED(255, 0, 0);
      else setLED(0, 0, 0);
    }
  }
}

// ── RGB LED Helper ─────────────────────────────────────────
void setLED(int r, int g, int b) {
  analogWrite(LED_R, r);
  analogWrite(LED_G, g);
  analogWrite(LED_B, b);
}

// ── Buzzer Helper ──────────────────────────────────────────
void buzz(int times) {
  for (int i = 0; i < times; i++) {
    digitalWrite(BUZZER, HIGH);
    delay(200);
    digitalWrite(BUZZER, LOW);
    delay(200);
  }
}