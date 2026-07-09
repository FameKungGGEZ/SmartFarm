// SmartFarm V3.1 - Blynk Control + Web Monitor
// ควบคุมผ่าน Blynk App
// แสดงสถานะผ่าน Web Server

#define BLYNK_TEMPLATE_ID "TMPL6NUBqUsHj"
#define BLYNK_TEMPLATE_NAME "SmartFarm"
#define BLYNK_AUTH_TOKEN "aE8bHdNu6YcwX7TIVTyy33FKaOgWrGXu"

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <Preferences.h>
#include <BlynkSimpleEsp32.h>

#define MCP_PIN 35
#define RELAY_SMOKE 14
#define RELAY_FAN 27
#define LIGHT_PIN 34
#define DHTPIN 23
#define RELAY_MOTOR1 26
#define RELAY_MOTOR2 25

#define DHTTYPE DHT21
DHT dht(DHTPIN,DHTTYPE);

// ========================================
// ตั้งค่า WiFi และ Server
// ========================================
const char* ssid="TP-wifi";
const char* password="";

// URL ของ Web Server
const char* SERVER_URL = "https://smartfarm-9epw.onrender.com";


// ========================================
// ตัวแปรระบบ
// ========================================
bool autoMode=true;  // เปิด Auto Mode เป็นค่าเริ่มต้น
bool spray=true, fan=true;
bool motorWorking=false;
String motorState="in";  // เริ่มต้นเป็น "in" (ปิด)

int lightValue;
float waterTemp,airTemp,hum;

// Threshold values
const int LIGHT_CLOSE_TH = 3000;
const int LIGHT_OPEN_TH  = 2200;
const unsigned long CONFIRM_MS = 60000UL; // 1 นาที

bool shadeClosed = false;

// Debounce timers
bool fanPending=false, fanPendingTarget=false;
unsigned long fanPendingStartMs=0;

bool sprayPending=false, sprayPendingTarget=false;
unsigned long sprayPendingStartMs=0;

bool shadePending=false, shadePendingTarget=false;
unsigned long shadePendingStartMs=0;

// Temperature/Humidity thresholds
const float TEMP_FAN_ON  = 30.0;
const float TEMP_FAN_OFF = 28.0;
const float HUM_MIST_ON  = 60.0;
const float HUM_MIST_OFF = 70.0;

// Preferences for Flash storage
Preferences prefs;
const char* PREFS_NS = "smartfarm";

// Motor control
enum MotorAction { MOTOR_IDLE, MOTOR_RUN_IN, MOTOR_RUN_OUT };
MotorAction motorAction = MOTOR_IDLE;
unsigned long motorStartMs = 0;
const unsigned long MOTOR_OUT_MS = 1300;  // เปิดสแลน (กางออก) = 1.3 วินาที
const unsigned long MOTOR_IN_MS  = 1900;  // ปิดสแลน (ม้วนเข้า) = 1.9 วินาที

// Update interval
unsigned long lastUpdateMs = 0;
const unsigned long UPDATE_INTERVAL = 2000; // ส่งข้อมูลทุก 2 วินาที

// ========================================
// Blynk Virtual Pins
// ========================================
// V10 - Auto Mode Switch
BLYNK_WRITE(V10) {
  autoMode = param.asInt();
  fanPending = false;
  sprayPending = false;
  shadePending = false;
  saveState();
  Serial.printf("🤖 [Blynk] โหมด: %s\n", autoMode?"AUTO":"MANUAL");
}

// V0 - Spray Switch
BLYNK_WRITE(V0) {
  if(!autoMode) {
    spray = param.asInt();
    digitalWrite(RELAY_SMOKE, !spray);
    saveState();
    Serial.printf("💨 [Blynk] สเปรย์: %s\n", spray?"เปิด":"ปิด");
  }
}

// V7 - Fan Switch
BLYNK_WRITE(V7) {
  if(!autoMode) {
    fan = param.asInt();
    digitalWrite(RELAY_FAN, !fan);
    saveState();
    Serial.printf("🌀 [Blynk] พัดลม: %s\n", fan?"เปิด":"ปิด");
  }
}

// V8 - Motor Button (Push)
BLYNK_WRITE(V8) {
  int btnValue = param.asInt();
  Serial.printf("🎚️ [Blynk] V8 button pressed: %d\n", btnValue);

  // ปุ่ม Push อาจส่ง 255 หรือ 1 (ขึ้นอยู่กับ Blynk version)
  if(!motorWorking && btnValue > 0) {
    startMotor(motorState == "out" ? false : true);
    Serial.printf("🎚️ [Blynk] สลับสแลนจาก %s\n", motorState.c_str());
  } else if(btnValue > 0) {
    Serial.printf("⚠️ มอเตอร์กำลังทำงานอยู่\n");
  }
}

// ========================================
// Flash State Management
// ========================================
void saveState(){
  prefs.begin(PREFS_NS,false);
  prefs.putBool("autoMode",autoMode);
  prefs.putBool("spray",spray);
  prefs.putBool("fan",fan);
  prefs.putBool("shadeClosed",shadeClosed);
  prefs.putString("motorState",motorState);
  prefs.end();
}

void loadState(){
  prefs.begin(PREFS_NS,true);
  autoMode    = prefs.getBool("autoMode",true);  // Default = true
  spray       = prefs.getBool("spray",true);
  fan         = prefs.getBool("fan",true);
  shadeClosed = prefs.getBool("shadeClosed",false);
  motorState  = prefs.getString("motorState","out");
  prefs.end();
}

// ========================================
// Motor Control
// ========================================
void startMotor(bool goOut){
  if(motorWorking) return;
  motorWorking = true;
  motorAction = goOut ? MOTOR_RUN_OUT : MOTOR_RUN_IN;
  motorStartMs = millis();
  if(goOut){
    digitalWrite(RELAY_MOTOR1,LOW);
    digitalWrite(RELAY_MOTOR2,HIGH);
  }else{
    digitalWrite(RELAY_MOTOR1,HIGH);
    digitalWrite(RELAY_MOTOR2,LOW);
  }
  Serial.println("🎚️ มอเตอร์เริ่มทำงาน...");
}

void handleMotor(){
  if(motorAction==MOTOR_IDLE) return;
  unsigned long dur = (motorAction==MOTOR_RUN_OUT)? MOTOR_OUT_MS : MOTOR_IN_MS;
  if(millis()-motorStartMs >= dur){
    digitalWrite(RELAY_MOTOR1,HIGH);
    digitalWrite(RELAY_MOTOR2,HIGH);
    motorState = (motorAction==MOTOR_RUN_OUT)? "out":"in";
    motorAction = MOTOR_IDLE;
    motorWorking = false;
    saveState();
    Serial.printf("✅ มอเตอร์หยุด: %s\n", motorState.c_str());
  }
}

// ========================================
// Sensor Reading
// ========================================
void readSensors(){
 lightValue=analogRead(LIGHT_PIN);
 int raw=analogRead(MCP_PIN);
 float v=raw*3.3/4095.0;
 waterTemp=(v-0.4)/0.0195;

 hum=dht.readHumidity();
 airTemp=dht.readTemperature();

 // ป้องกัน nan (ถ้า DHT ไม่ทำงาน)
 if(isnan(hum)) {
   hum = 0.0;
   Serial.println("⚠️ DHT Humidity error - using 0.0");
 }
 if(isnan(airTemp)) {
   airTemp = 0.0;
   Serial.println("⚠️ DHT Temperature error - using 0.0");
 }
 if(isnan(waterTemp)) {
   waterTemp = 0.0;
 }
}

// ========================================
// Auto Control Functions
// ========================================
void autoControlFan(){
 if(!autoMode) return;
 unsigned long now = millis();
 bool desired = fan;
 if(!fan && waterTemp>TEMP_FAN_ON)      desired = true;
 else if(fan && waterTemp<TEMP_FAN_OFF) desired = false;

 if(desired != fan){
   if(!fanPending || fanPendingTarget!=desired){
     fanPending=true; fanPendingTarget=desired; fanPendingStartMs=now;
   }else if(now-fanPendingStartMs >= CONFIRM_MS){
     fan=desired;
     digitalWrite(RELAY_FAN,!fan);
     fanPending=false;
     saveState();
     Blynk.virtualWrite(V7, fan ? 1 : 0);
     Serial.printf("🌀 พัดลม: %s (Auto)\n", fan?"เปิด":"ปิด");
   }
 }else{
   fanPending=false;
 }
}

void autoControlSpray(){
 if(!autoMode) return;
 unsigned long now = millis();
 bool desired = spray;
 if(!spray && hum<HUM_MIST_ON)        desired = true;
 else if(spray && hum>HUM_MIST_OFF)   desired = false;

 if(desired != spray){
   if(!sprayPending || sprayPendingTarget!=desired){
     sprayPending=true; sprayPendingTarget=desired; sprayPendingStartMs=now;
   }else if(now-sprayPendingStartMs >= CONFIRM_MS){
     spray=desired;
     digitalWrite(RELAY_SMOKE,!spray);
     sprayPending=false;
     saveState();
     Blynk.virtualWrite(V0, spray ? 1 : 0);
     Serial.printf("💨 สเปรย์: %s (Auto)\n", spray?"เปิด":"ปิด");
   }
 }else{
   sprayPending=false;
 }
}

void autoShadeControl(){
 if(!autoMode) return;
 if(motorWorking) return;
 unsigned long now = millis();
 bool desired = shadeClosed;
 if(!shadeClosed && lightValue>=LIGHT_CLOSE_TH)     desired = true;
 else if(shadeClosed && lightValue<=LIGHT_OPEN_TH)  desired = false;

 if(desired != shadeClosed){
   if(!shadePending || shadePendingTarget!=desired){
     shadePending=true; shadePendingTarget=desired; shadePendingStartMs=now;
   }else if(now-shadePendingStartMs >= CONFIRM_MS){
     startMotor(desired);
     shadeClosed=desired;
     shadePending=false;
     saveState();
     Serial.printf("☀️ สแลน: %s (Auto)\n", desired?"ปิด":"เปิด");
   }
 }else{
   shadePending=false;
 }
}

// ========================================
// HTTP Communication with Web Server (ส่งสถานะเท่านั้น)
// ========================================
void sendStatusToWebServer(){
  if(WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = String(SERVER_URL) + "/api/sensor/update";

  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  // สร้าง JSON payload (ส่งสถานะเท่านั้น ไม่รับคำสั่งกลับมา)
  StaticJsonDocument<512> doc;
  doc["water_temp"] = waterTemp;
  doc["air_temp"] = airTemp;
  doc["humidity"] = hum;
  doc["light_value"] = lightValue;
  doc["auto_mode"] = autoMode;
  doc["spray"] = spray;
  doc["fan"] = fan;
  doc["shade_closed"] = shadeClosed;
  doc["motor_state"] = motorState;
  doc["motor_working"] = motorWorking;
  doc["fan_pending"] = fanPending;
  doc["spray_pending"] = sprayPending;
  doc["shade_pending"] = shadePending;

  String payload;
  serializeJson(doc, payload);

  int httpCode = http.POST(payload);

  if(httpCode == 200){
    Serial.println("✅ ส่งสถานะไปยังเว็บสำเร็จ");
  }else{
    Serial.printf("❌ HTTP Error: %d\n", httpCode);
  }

  http.end();
}

// ========================================
// Sync Blynk Virtual Pins
// ========================================
void syncBlynkPins(){
  Blynk.virtualWrite(V10, autoMode ? 1 : 0);
  Blynk.virtualWrite(V0, spray ? 1 : 0);
  Blynk.virtualWrite(V7, fan ? 1 : 0);
}

// ========================================
// Serial Output
// ========================================
void printSerial(){
 Serial.println("==== SmartFarm (Blynk Control) ====");
 Serial.printf("Mode: %s\n",autoMode?"AUTO":"MANUAL");
 Serial.printf("Air %.1fC Hum %.1f%% Water %.1fC Light %d\n",airTemp,hum,waterTemp,lightValue);
 Serial.printf("Spray: %s Fan: %s\n", spray?"ON":"OFF", fan?"ON":"OFF");
 Serial.printf("Shade: %s (motorState=%s)\n", shadeClosed?"CLOSED":"OPEN", motorState.c_str());

 if(fanPending)   Serial.printf("  [รอยืนยัน] Fan -> %s\n", fanPendingTarget?"ON":"OFF");
 if(sprayPending) Serial.printf("  [รอยืนยัน] Spray -> %s\n", sprayPendingTarget?"ON":"OFF");
 if(shadePending) Serial.printf("  [รอยืนยัน] Shade -> %s\n", shadePendingTarget?"CLOSED":"OPEN");
}

// ========================================
// Main Task Loop
// ========================================
void task(){
 readSensors();
 autoControlFan();
 autoControlSpray();
 autoShadeControl();
 printSerial();
}

// ========================================
// WiFi Connection
// ========================================
void connectWiFi(){
  if(WiFi.status() == WL_CONNECTED) return;

  Serial.print("กำลังเชื่อมต่อ WiFi");
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  int retry = 0;
  while(WiFi.status() != WL_CONNECTED && retry < 40){
    delay(500);
    Serial.print(".");
    retry++;
  }

  Serial.println();
  if(WiFi.status() == WL_CONNECTED){
    Serial.print("✅ เชื่อมต่อ WiFi สำเร็จ IP: ");
    Serial.println(WiFi.localIP());
  }else{
    Serial.println("❌ เชื่อมต่อ WiFi ไม่สำเร็จ จะลองใหม่รอบถัดไป");
  }
}

// ========================================
// Setup
// ========================================
void setup(){
 Serial.begin(115200);
 analogReadResolution(12);

 pinMode(RELAY_SMOKE,OUTPUT);
 pinMode(RELAY_FAN,OUTPUT);
 pinMode(RELAY_MOTOR1,OUTPUT);
 pinMode(RELAY_MOTOR2,OUTPUT);

 loadState();

 digitalWrite(RELAY_SMOKE,!spray);
 digitalWrite(RELAY_FAN,!fan);
 digitalWrite(RELAY_MOTOR1,HIGH);
 digitalWrite(RELAY_MOTOR2,HIGH);

 dht.begin();
 connectWiFi();

 // เชื่อมต่อ Blynk
 Blynk.begin(BLYNK_AUTH_TOKEN, ssid, password);

 Serial.println("\n🌿 SmartFarm V3.1 - Blynk Control + Web Monitor");
 Serial.println("========================================");
 Serial.printf("โหมดเริ่มต้น: %s\n", autoMode?"AUTO":"MANUAL");
 Serial.printf("สถานะสแลนปัจจุบัน: %s\n", motorState=="out"?"เปิด":"ปิด");
 Serial.println("ควบคุมผ่าน: Blynk App");
 Serial.println("แสดงสถานะ: Web Server");
}

// ========================================
// Loop
// ========================================
void loop(){
 Blynk.run();  // รัน Blynk
 handleMotor();

 unsigned long now = millis();

 // รันระบบควบคุมทุก 1 วินาที
 static unsigned long lastTaskMs = 0;
 if(now - lastTaskMs >= 1000){
   task();
   lastTaskMs = now;
 }

 // ส่งสถานะไปที่ Web Server ทุก 2 วินาที
 if(now - lastUpdateMs >= UPDATE_INTERVAL){
   connectWiFi(); // ตรวจสอบ WiFi connection
   sendStatusToWebServer();
   lastUpdateMs = now;
 }

 // Sync Blynk pins ทุก 5 วินาที
 static unsigned long lastSyncMs = 0;
 if(now - lastSyncMs >= 5000){
   if(Blynk.connected()){
     syncBlynkPins();
   }
   lastSyncMs = now;
 }

 delay(100);
}
