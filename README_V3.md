# 🌿 SmartFarm V3.0 - Complete Web Edition

## ภาพรวม
SmartFarm V3.0 เป็นระบบเกษตรอัฉริยะแบบครบวงจรที่รวมทั้ง:
- 📷 **ระบบกล้อง AI** - ตรวจสุขภาพต้นกรีนโอ๊คด้วย Edge Impulse
- 🎛️ **ระบบควบคุมอัตโนมัติ** - ควบคุมพัดลม, สเปรย์, สแลนพรางแสง
- 📊 **เซ็นเซอร์แบบ Real-time** - แสดงค่าอุณหภูมิ, ความชื้น, แสง
- 🌐 **Web Dashboard** - ควบคุมและติดตามผ่านเว็บเบราว์เซอร์

**ไม่ต้องใช้ Blynk อีกต่อไป!** ทุกอย่างอยู่ในเว็บไซต์เดียว

---

## 🏗️ สถาปัตยกรรมระบบ

```
┌─────────────────┐
│   ESP32-CAM     │ ──┐
│  (กล้อง + AI)   │   │
└─────────────────┘   │
                      │
┌─────────────────┐   │    ┌──────────────────────┐
│   ESP32 Main    │───┼───▶│   Web Server         │
│ (เซ็นเซอร์ +    │   │    │  (Python Flask)      │
│  ควบคุม)        │   │    │  - ประมวลผลภาพ AI    │
└─────────────────┘   │    │  - จัดการเซ็นเซอร์   │
                      │    │  - API ควบคุม        │
                      │    └──────────────────────┘
                      │              │
                      └──────────────┘
                                     │
                              ┌──────▼───────┐
                              │ Web Browser  │
                              │  Dashboard   │
                              └──────────────┘
```

---

## 📋 ฟีเจอร์หลัก

### 1. ระบบกล้อง AI (ESP32-CAM)
- ✅ ถ่ายภาพทุก 10 วินาที (ปรับได้)
- ✅ ส่งภาพไปประมวลผลที่ Server
- ✅ AI ตรวจสุขภาพต้นกรีนโอ๊ค (Healthy/UnHealthy)
- ✅ แสดงผลพร้อมกรอบสีบนภาพ

### 2. ระบบควบคุมอัตโนมัติ (ESP32 Main)
- ✅ **โหมดอัตโนมัติ**: ควบคุมตาม threshold อุณหภูมิ/ความชื้น
- ✅ **โหมดแมนนวล**: ควบคุมผ่าน Web UI ได้โดยตรง
- ✅ **Debounce 1 นาที**: รอยืนยันค่าก่อนเปลี่ยนสถานะ
- ✅ **บันทึกสถานะ**: จำค่าล่าสุดแม้ไฟดับ

### 3. เซ็นเซอร์ที่รองรับ
| เซ็นเซอร์ | ชนิด | หน้าที่ |
|-----------|------|---------|
| DHT21 | อุณหภูมิ/ความชื้นอากาศ | ควบคุมพัดลม/สเปรย์ |
| MCP9700A | อุณหภูมิน้ำ | ตรวจสอบอุณหภูมิน้ำ |
| LDR | ค่าแสง | ควบคุมสแลนพรางแสง |

### 4. อุปกรณ์ควบคุม
- 🌀 **พัดลม** - เปิดเมื่ออุณหภูมิน้ำ > 30°C
- 💨 **สเปรย์/ควัน** - เปิดเมื่อความชื้น < 60%
- 🎚️ **สแลนพรางแสง** - ปิด(กาง)เมื่อแสงจัด > 3000

---

## 🚀 การติดตั้งและใช้งาน

### 1. เตรียม Web Server (Render/Cloud)

#### ติดตั้ง Dependencies
```bash
cd SmartFarm-main
pip install -r requirements.txt
```

#### ไฟล์ที่สำคัญ
```
SmartFarm-main/
├── app.py                    # Main Flask app
├── sensor_controller.py      # [ใหม่] จัดการเซ็นเซอร์
├── config.py                 # การตั้งค่าทั้งหมด
├── image_processor.py        # ประมวลผลภาพ
├── templates/
│   └── index.html           # [อัพเดท] Dashboard ใหม่
└── requirements.txt         # Python dependencies
```

#### Deploy บน Render
1. Push โค้ดไปที่ GitHub: `https://github.com/FameKungGGEZ/SmartFarm`
2. ไปที่ Render.com → New Web Service
3. เชื่อมต่อกับ GitHub repo
4. ตั้งค่า:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
5. คลิก "Create Web Service"

#### ได้ URL แบบ
```
https://smartfarm-9epw.onrender.com
```

---

### 2. อัพโหลดโค้ดไปยัง ESP32

#### A) ESP32-CAM (ระบบกล้อง)
**ไฟล์**: ใช้โค้ดเดิมที่ `esp32_cam_plant_monitor.ino`

**แก้ไขบรรทัดนี้**:
```cpp
const char* SERVER_BASE = "https://smartfarm-9epw.onrender.com";
```
เปลี่ยนเป็น URL ของคุณ

**Arduino IDE Settings**:
- Board: `AI Thinker ESP32-CAM`
- Partition Scheme: `Huge APP (3MB No OTA/1MB SPIFFS)`
- PSRAM: `Enabled`

#### B) ESP32 Main (ระบบควบคุม)
**ไฟล์**: `SmartFarm_WebServer.ino` (ไฟล์ใหม่!)

**แก้ไขบรรทัดนี้**:
```cpp
const char* ssid="YOUR_WIFI_SSID";
const char* password="YOUR_WIFI_PASSWORD";
const char* SERVER_URL = "https://smartfarm-9epw.onrender.com";
```

**ต้องติดตั้งไลบรารี**:
- DHT sensor library
- ArduinoJson
- Preferences (มีใน ESP32 core อยู่แล้ว)

**Arduino IDE Settings**:
- Board: `ESP32 Dev Module`
- Upload Speed: `115200`

---

### 3. การต่อสายอุปกรณ์

#### ESP32 Main - Pin Connections

| อุปกรณ์ | ESP32 Pin |
|---------|-----------|
| DHT21 (Data) | GPIO 23 |
| MCP9700A (Analog) | GPIO 35 |
| LDR (Analog) | GPIO 34 |
| Relay พัดลม | GPIO 27 |
| Relay สเปรย์ | GPIO 14 |
| Relay Motor 1 | GPIO 26 |
| Relay Motor 2 | GPIO 25 |

#### ESP32-CAM - ใช้ Pin Configuration มาตรฐาน AI-Thinker

---

## 🎮 การใช้งาน Web Dashboard

### เปิด Dashboard
```
https://your-app-name.onrender.com
```

### ส่วนต่างๆ ของหน้าจอ

#### 1. สถิติการตรวจสุขภาพ (บนสุด)
- 🟢 **Healthy**: จำนวนต้นแข็งแรง
- 🔴 **UnHealthy**: จำนวนต้นผิดปกติ
- 📊 **Total**: จำนวนต้นทั้งหมด
- 📡 **Status**: สถานะปัจจุบัน

#### 2. ระบบควบคุมและเซ็นเซอร์ (ใหม่! 🎉)
```
┌─────────────────────────────────────┐
│ ⚙️ ระบบควบคุมและเซ็นเซอร์           │
├─────────────────────────────────────┤
│ 🌡️ อุณหภูมิอากาศ  │ 💧 ความชื้น    │
│     28.5 °C        │    65.2 %      │
│ 💦 อุณหภูมิน้ำ     │ ☀️ ค่าแสง       │
│     25.3 °C        │    2500        │
├─────────────────────────────────────┤
│ 🤖 โหมดอัตโนมัติ    [ON/OFF]        │
│ 💨 สเปรย์/ควัน      [ON/OFF]        │
│ 🌀 พัดลม            [ON/OFF]        │
│ 🎚️ สลับสแลน (กาง)   [ปุ่ม]         │
└─────────────────────────────────────┘
```

**การทำงาน**:
- ✅ **Auto Mode ON**: ระบบควบคุมอัตโนมัติ (ปุ่มอื่นปิดใช้งาน)
- ✅ **Auto Mode OFF**: ควบคุมด้วยตนเอง ผ่าน toggle switches
- ✅ **Real-time Update**: ข้อมูลอัพเดททันทีผ่าน SSE (Server-Sent Events)
- ✅ **Pending Status**: แสดงสถานะ "รอยืนยันค่า" เมื่ออยู่ในช่วง debounce

#### 3. ภาพจากกล้อง
- **Latest Photo**: ภาพล่าสุดจาก ESP32-CAM พร้อมโซนตรวจจับ
- **Result Photo**: ภาพผลการวิเคราะห์ พร้อมกรอบสี (เขียว=ดี, แดง=ไม่ดี)

---

## 🔧 การปรับแต่ง Threshold

### แก้ไขใน ESP32 Code (`SmartFarm_WebServer.ino`)

```cpp
// ค่า Threshold ของพัดลม (อิงอุณหภูมิน้ำ)
const float TEMP_FAN_ON  = 30.0;  // เปิดเมื่อ > 30°C
const float TEMP_FAN_OFF = 28.0;  // ปิดเมื่อ < 28°C

// ค่า Threshold ของสเปรย์ (อิงความชื้น)
const float HUM_MIST_ON  = 60.0;  // เปิดเมื่อ < 60%
const float HUM_MIST_OFF = 70.0;  // ปิดเมื่อ > 70%

// ค่า Threshold ของสแลน (อิงค่าแสง)
const int LIGHT_CLOSE_TH = 3000;  // ปิด(กาง)เมื่อ >= 3000
const int LIGHT_OPEN_TH  = 2200;  // เปิด(ม้วน)เมื่อ <= 2200

// เวลารอยืนยันค่า (Debounce)
const unsigned long CONFIRM_MS = 60000UL; // 1 นาที (60000 ms)
```

### แก้ไขความถี่การส่งข้อมูล
```cpp
// ส่งข้อมูลไปที่ Server (บรรทัด 46)
const unsigned long UPDATE_INTERVAL = 2000; // 2 วินาที (ms)
```

### แก้ไขความถี่การถ่ายภาพ (ESP32-CAM)
```cpp
// ใน esp32_cam_plant_monitor.ino บรรทัด 47
const unsigned long CAPTURE_INTERVAL_MS = 10UL * 1000UL;  // 10 วินาที
```

---

## 📡 API Documentation

### สำหรับ ESP32 ส่งข้อมูล

#### POST `/api/sensor/update`
ส่งข้อมูลเซ็นเซอร์และรับคำสั่งควบคุมกลับ

**Request Body (JSON)**:
```json
{
  "water_temp": 25.5,
  "air_temp": 28.3,
  "humidity": 65.2,
  "light_value": 2500,
  "auto_mode": false,
  "spray": true,
  "fan": true,
  "shade_closed": false,
  "motor_state": "out",
  "motor_working": false,
  "fan_pending": false,
  "spray_pending": false,
  "shade_pending": false
}
```

**Response (JSON)**:
```json
{
  "ok": true,
  "controls": {
    "auto_mode": false,
    "spray": true,
    "fan": true,
    "motor_toggle": false
  }
}
```

### สำหรับ Web UI

#### GET `/api/sensor/data`
ดึงข้อมูลเซ็นเซอร์ล่าสุด

#### POST `/api/control/<type>`
ควบคุมอุปกรณ์ (type: `spray`, `fan`, `auto_mode`, `motor_toggle`)

**Request Body**:
```json
{
  "value": true
}
```

#### GET `/api/events`
Server-Sent Events สำหรับ real-time updates

---

## 🐛 แก้ปัญหา

### 1. ESP32 เชื่อมต่อ WiFi ไม่ได้
- ✅ ตรวจสอบ SSID/Password
- ✅ ตรวจสอบสัญญาณ WiFi
- ✅ ดู Serial Monitor (115200 baud)

### 2. ข้อมูลเซ็นเซอร์ไม่อัพเดท
- ✅ ตรวจสอบ Server URL ใน ESP32 code
- ✅ ดูว่า ESP32 ส่งข้อมูลสำเร็จหรือไม่ (Serial Monitor)
- ✅ ตรวจสอบ Server logs บน Render

### 3. ควบคุมจาก Web ไม่ทำงาน
- ✅ ตรวจสอบว่าไม่ได้อยู่ใน Auto Mode (ปุ่มจะถูกปิด)
- ✅ รอ 2-3 วินาที (ESP32 ส่งข้อมูลทุก 2 วินาที)
- ✅ เปิด Browser Console ดู errors

### 4. กล้องไม่ส่งภาพ
- ✅ ตรวจสอบว่า ESP32-CAM เชื่อมต่อ WiFi
- ✅ ตรวจสอบ SERVER_BASE URL
- ✅ ดู Serial Monitor ของ ESP32-CAM

---

## 📊 การติดตาม Logs

### Server Logs (Render)
```bash
# ไปที่ Render Dashboard → Logs
# จะเห็นข้อมูลแบบนี้:
📊 Sensor Update: Temp=28.3°C Hum=65.2% Light=2500
🎛  Control: spray = true
📷 รับภาพจาก ESP32
🌿 กำลัง crop ต้นกรีนโอ๊ค (Fixed Zone)...
```

### ESP32 Serial Monitor
```bash
==== SmartFarm (Web Server) ====
Mode: AUTO
Air 28.3C Hum 65.2% Water 25.5C Light 2500
Spray: ON Fan: ON
Shade: OPEN (motorState=out)
✅ อัพเดทข้อมูลสำเร็จ
```

---

## 🎯 ข้อดีของ Web Edition vs Blynk

| ฟีเจอร์ | Web Edition | Blynk |
|---------|-------------|-------|
| ไม่มีค่าใช้จ่าย | ✅ ฟรี | ❌ มี Limit |
| ควบคุมได้ไม่จำกัด | ✅ | ❌ จำกัดตาม Plan |
| รวมกล้อง + ควบคุม | ✅ | ❌ แยกกัน |
| Responsive Design | ✅ | ✅ |
| Real-time Update | ✅ (SSE) | ✅ |
| ปรับแต่ง UI ได้ | ✅ เต็มที่ | ❌ จำกัด |

---

## 🔄 อัพเดทในอนาคต
- [ ] เพิ่ม Authentication (Login)
- [ ] บันทึกประวัติข้อมูลเซ็นเซอร์
- [ ] แสดงกราฟแบบ real-time
- [ ] แจ้งเตือนผ่าน Line Notify
- [ ] รองรับหลาย Zone/ฟาร์ม
- [ ] Mobile App (React Native/Flutter)

---

## 📝 License
MIT License - ใช้ได้อย่างอิสระ

## 👨‍💻 Credits
- **Developer**: FameKungGGEZ
- **GitHub**: https://github.com/FameKungGGEZ/SmartFarm
- **Version**: 3.0 (Web Complete Edition)

---

## 🙏 ขอบคุณ
- Edge Impulse - สำหรับ AI Model
- OpenCV - สำหรับ Image Processing
- Flask - สำหรับ Web Framework
- Render - สำหรับ Free Cloud Hosting

---

**หมายเหตุ**: ถ้ามีปัญหาหรือข้อสงสัย สามารถเปิด Issue ได้ที่ GitHub Repository
