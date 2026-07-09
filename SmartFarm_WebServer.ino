// SmartFarm V3.0 - Web Server Edition (ไม่ใช้ Blynk)
// เชื่อมต่อกับ Web Server แทน Blynk โดยตรง
// ส่งข้อมูลเซ็นเซอร์และรับคำสั่งควบคุมผ่าน HTTP REST API

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <Preferences.h>

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
String motorState="out";

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
const unsigned long MOTOR_OUT_MS = 1900;
const unsigned long MOTOR_IN_MS  = 1300;

// Update interval
unsigned long lastUpdateMs = 0;
const unsigned long UPDATE_INTERVAL = 2000; // ส่งข้อมูลทุก 2 วินาที

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
// HTTP Communication with Web Server
// ========================================
void sendSensorDataAndGetControls(){
  if(WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = String(SERVER_URL) + "/api/sensor/update";

  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  // สร้าง JSON payload
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
    String response = http.getString();

    // Parse response เพื่อรับคำสั่งควบคุมจาก Web UI
    StaticJsonDocument<256> resDoc;
    DeserializationError error = deserializeJson(resDoc, response);

    if(!error && resDoc["ok"]){
      JsonObject controls = resDoc["controls"];

      // Auto mode สามารถสลับได้เสมอ
      if(controls.containsKey("auto_mode")){
        bool webAutoMode = controls["auto_mode"].as<bool>();
        if(webAutoMode != autoMode){
          autoMode = webAutoMode;
          fanPending = false;
          sprayPending = false;
          shadePending = false;
          saveState();
          Serial.printf("🤖 โหมด: %s (จากเว็บ)\n", autoMode?"AUTO":"MANUAL");
        }
      }

      // อัพเดทการควบคุมจาก Web UI (เฉพาะตอนไม่ได้อยู่ใน auto mode)
      if(!autoMode){
        if(controls.containsKey("spray")){
          bool webSpray = controls["spray"].as<bool>();
          if(webSpray != spray){
            spray = webSpray;
            digitalWrite(RELAY_SMOKE, !spray);
            saveState();
            Serial.printf("💨 สเปรย์: %s (จากเว็บ)\n", spray?"เปิด":"ปิด");
          }
        }

        if(controls.containsKey("fan")){
          bool webFan = controls["fan"].as<bool>();
          if(webFan != fan){
            fan = webFan;
            digitalWrite(RELAY_FAN, !fan);
            saveState();
            Serial.printf("🌀 พัดลม: %s (จากเว็บ)\n", fan?"เปิด":"ปิด");
          }
        }

        // Motor toggle
        if(controls.containsKey("motor_toggle")){
          bool motorToggle = controls["motor_toggle"].as<bool>();
          if(motorToggle && !motorWorking){
            startMotor(motorState == "out" ? false : true);
          }
        }
      }
    }

    Serial.println("✅ อัพเดทข้อมูลสำเร็จ");
  }else{
    Serial.printf("❌ HTTP Error: %d\n", httpCode);
  }

  http.end();
}

// ========================================
// Serial Output
// ========================================
void printSerial(){
 Serial.println("==== SmartFarm (Web Server) ====");
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

 Serial.println("\n🌿 SmartFarm V3.0 - Web Server Edition");
 Serial.println("========================================");
 Serial.printf("โหมดเริ่มต้น: %s\n", autoMode?"AUTO":"MANUAL");
}

// ========================================
// Loop
// ========================================
void loop(){
 handleMotor();

 unsigned long now = millis();

 // รันระบบควบคุมทุก 1 วินาที
 static unsigned long lastTaskMs = 0;
 if(now - lastTaskMs >= 1000){
   task();
   lastTaskMs = now;
 }

 // ส่งข้อมูลไปที่ Web Server ทุก 2 วินาที
 if(now - lastUpdateMs >= UPDATE_INTERVAL){
   connectWiFi(); // ตรวจสอบ WiFi connection
   sendSensorDataAndGetControls();
   lastUpdateMs = now;
 }

 delay(100);
}
