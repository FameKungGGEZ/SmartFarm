# 🚀 SmartFarm V3.0 - Quick Start Guide

## สิ่งที่เปลี่ยนแปลง
✅ **ไม่ต้องใช้ Blynk อีกต่อไป!**
✅ ระบบกล้อง + ควบคุม รวมอยู่ในเว็บเดียว
✅ Real-time update ทุกอย่าง
✅ ควบคุมได้ไม่จำกัด ไม่มี limit

## ไฟล์ที่สำคัญ
```
SmartFarm-main/
├── SmartFarm_WebServer.ino    [ใหม่] โค้ด ESP32 ควบคุมหลัก (แทน Blynk)
├── sensor_controller.py       [ใหม่] จัดการเซ็นเซอร์ server-side
├── app.py                     [แก้ไข] เพิ่ม API สำหรับควบคุม
├── templates/index.html       [แก้ไข] เพิ่ม UI ควบคุมและเซ็นเซอร์
└── README_V3.md              [ใหม่] คู่มือฉบับเต็ม
```

## การติดตั้งด่วน

### 1. Deploy Web Server (5 นาที)
1. Push โค้ดไปที่ GitHub: https://github.com/FameKungGGEZ/SmartFarm
2. ไปที่ Render.com → New Web Service
3. เลือก GitHub repo
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `gunicorn app:app`
6. คลิก Deploy

### 2. อัพโหลด ESP32 (10 นาที)

#### A) ESP32-CAM (กล้อง)
- ใช้โค้ดเดิม: `esp32_cam_plant_monitor.ino`
- แก้แค่ URL ของ server

#### B) ESP32 Main (ควบคุม) 
- ใช้โค้ดใหม่: `SmartFarm_WebServer.ino`
- แก้ WiFi และ Server URL
- อัพโหลด!

### 3. เปิดเว็บ
```
https://your-app.onrender.com
```

## สิ่งที่จะเห็นในเว็บ

### ส่วน 1: สถิติกล้อง (เหมือนเดิม)
- 🟢 ต้นแข็งแรง
- 🔴 ต้นผิดปกติ
- 📊 จำนวนรวม

### ส่วน 2: ควบคุมและเซ็นเซอร์ (ใหม่!)
```
┌─────────────────────────────────┐
│ ⚙️ ระบบควบคุมและเซ็นเซอร์       │
│                                 │
│ 🌡️ อุณหภูมิอากาศ  28.5 °C      │
│ 💧 ความชื้น       65.2 %        │
│ 💦 อุณหภูมิน้ำ     25.3 °C      │
│ ☀️ ค่าแสง         2500          │
│                                 │
│ 🤖 โหมดอัตโนมัติ  [ON/OFF]     │
│ 💨 สเปรย์/ควัน    [ON/OFF]     │
│ 🌀 พัดลม          [ON/OFF]     │
│ 🎚️ สลับสแลน       [ปุ่ม]       │
└─────────────────────────────────┘
```

### ส่วน 3: ภาพกล้อง (เหมือนเดิม)
- Latest Photo
- Result Photo

## การทำงาน

### โหมดอัตโนมัติ (Auto Mode)
- เปิด: ระบบควบคุมตาม threshold
- ปิดอุปกรณ์อื่นไม่ให้กดได้
- ESP32 ตัดสินใจเอง

### โหมดแมนนวล (Manual Mode)
- ปิด Auto: ควบคุมจากเว็บได้เลย
- กดปุ่มบนเว็บ → ESP32 รับคำสั่งภายใน 2 วินาที
- Real-time ทันที!

## ตรวจสอบว่าทำงานหรือไม่

### 1. ESP32 Serial Monitor ควรเห็น:
```
✅ เชื่อมต่อ WiFi สำเร็จ IP: 192.168.1.xxx
==== SmartFarm (Web Server) ====
Mode: AUTO
Air 28.3C Hum 65.2% Water 25.5C Light 2500
✅ อัพเดทข้อมูลสำเร็จ
```

### 2. เว็บไซต์ควรเห็น:
- ค่าเซ็นเซอร์อัพเดททุก 2 วินาที
- สถานะอุปกรณ์แสดงถูกต้อง
- กดปุ่มแล้วเปลี่ยนสถานะได้

### 3. Render Logs ควรเห็น:
```
📊 Sensor Update: Temp=28.3°C Hum=65.2% Light=2500
```

## แก้ปัญหาเร็ว

❌ **ESP32 ไม่เชื่อม WiFi**
→ ตรวจสอบ SSID/Password

❌ **ข้อมูลไม่อัพเดท**
→ ตรวจสอบ Server URL ในโค้ด ESP32

❌ **กดปุ่มไม่ได้**
→ ตรวจสอบว่าไม่ได้เปิด Auto Mode

❌ **กล้องไม่ส่งภาพ**
→ ตรวจสอบ ESP32-CAM ว่าเชื่อม WiFi แล้ว

## ข้อดีเทียบกับ Blynk

| ฟีเจอร์ | Web V3 | Blynk |
|---------|--------|-------|
| ไม่มีค่าใช้จ่าย | ✅ | ❌ |
| ไม่มี Limit | ✅ | ❌ |
| รวมกล้อง+ควบคุม | ✅ | ❌ |
| ปรับแต่ง UI ได้ | ✅ | ❌ |
| Real-time | ✅ | ✅ |

## ต่อไป?
อ่านคู่มือฉบับเต็ม: `README_V3.md`

---
**Version**: 3.0 - Complete Web Edition  
**GitHub**: https://github.com/FameKungGGEZ/SmartFarm  
**สร้างโดย**: Claude Code + FameKungGGEZ
