# SmartFarm AI Server V2 — สรุปไฟล์และการแก้ไขทั้งหมด

> อัพเดตล่าสุด: 2026-07-07

---

## 📁 ไฟล์ที่สร้างใหม่ทั้งหมด

### Python Server (`smartfarm_v2/`)

| ไฟล์ | หน้าที่ |
|------|---------|
| `config.py` | ตั้งค่าทั้งหมด — Blynk token, pins, HSV range, thresholds |
| `blynk.py` | ส่งข้อมูลขึ้น Blynk (sync + async, ทีละพิน + batch) |
| `image_processor.py` | ค้นหาต้นไม้ด้วย OpenCV + วาดกรอบ + สร้าง result.jpg |
| `session.py` | Session Manager Thread-Safe + Auto Cleanup |
| `dashboard.py` | Blueprint: `/`, `/stats`, `/latest.jpg`, `/result.jpg` |
| `app.py` | Entry point: Flask + 4 ESP32 API routes |
| `templates/index.html` | Dashboard UI — auto refresh ทุก 5 วิ |
| `requirements.txt` | Flask, OpenCV, NumPy, Requests, Gunicorn |
| `Procfile` | gunicorn สำหรับ Render / Koyeb / Railway |
| `runtime.txt` | Python 3.11.9 |
| `.gitignore` | ไม่ commit ภาพและ venv |
| `README.md` | คู่มือติดตั้ง + API Reference |
| `Dockerfile` | สำหรับ Deploy บน Render ด้วย Docker |
| `CHANGELOG.md` | ไฟล์นี้ |

---

## 🔧 การแก้ไขที่ทำไป

### ครั้งที่ 1 — เพิ่ม Dockerfile

**ปัญหา:** Render หา `Dockerfile` ไม่เจอ เพราะไฟล์อยู่ใน subfolder  
**แก้ไข:** ย้าย `Dockerfile` ไปไว้ที่ root ของ repo

```
/ (root)
└── Dockerfile   ← เพิ่มที่นี่
└── smartfarm_v2/
    └── Dockerfile  ← ของเดิม
```

---

### ครั้งที่ 2 — เปลี่ยน Edge Impulse Library

**ปัญหา:** ใช้ library เดิม `Plant_inferencing` ไม่ตรงกับโมเดลใหม่  
**ไฟล์ที่แก้:** `esp32_cam_plant_monitor.ino`

```cpp
// เดิม
#include <Plant_inferencing.h>

// ใหม่
#include <GreenOak_inferencing.h>
```

**ข้อมูลโมเดลใหม่ (จาก ei-greenoak-arduino-1.0.4-impulse-#1.zip):**
- Input size: 96×96 px (ไม่เปลี่ยน)
- Labels: `Healthy`, `UnHealthy` (ไม่เปลี่ยน)
- Python server: ไม่ต้องแก้ไขใดๆ ✅

---

### ครั้งที่ 3 — แก้ปัญหา False Detection

**ปัญหา:** OpenCV ตรวจจับวัตถุสีเขียวที่ไม่ใช่ต้นไม้ (หญ้า, เงา, วัสดุ)

#### `config.py`

```python
# เดิม — HSV กว้างเกิน จับทุกอย่างสีเขียว
GREEN_HSV_LOWER = (25, 40, 40)
GREEN_HSV_UPPER = (95, 255, 255)
MIN_PLANT_AREA  = 1500

# ใหม่ — จับเฉพาะสีใบกรีนโอ๊ค
GREEN_HSV_LOWER = (35, 50, 40)
GREEN_HSV_UPPER = (85, 255, 255)
MIN_PLANT_AREA  = 4000
```

#### `image_processor.py`

เพิ่ม Shape Filter กรอง contour ที่ไม่ใช่ต้นไม้ออก:
- Aspect ratio > 3.5 → ยาวเรียวเกินไป ❌
- Density < 20% → บางเกินไป ไม่ใช่ก้อนใบ ❌

#### `esp32_cam_plant_monitor.ino`

เพิ่ม Confidence Threshold:
```cpp
const float MIN_CONF = 0.70f;
// ถ้า confidence < 70% = ข้าม ไม่นับเป็นต้นไม้
```

---

## 📡 API ที่ใช้งาน (ไม่มีการเปลี่ยนแปลง)

| Endpoint | Method | ผู้เรียก | หน้าที่ |
|----------|--------|---------|---------|
| `/upload` | POST | ESP32 | รับภาพ JPEG |
| `/crop` | GET | ESP32 | ส่ง crop 96×96 RGB |
| `/result` | POST | ESP32 | รับผล Healthy/UnHealthy |
| `/finalize` | POST | ESP32 | สรุปผล + อัพเดต Blynk |
| `/stats` | GET | Dashboard | JSON สถิติล่าสุด |
| `/latest.jpg` | GET | ทุกคน | ภาพล่าสุด |
| `/result.jpg` | GET | ทุกคน | ภาพผลลัพธ์พร้อมกรอบ |
| `/` | GET | ทุกคน | Dashboard HTML |

---

## 📌 Blynk Virtual Pins

| Pin | ประเภท | ความหมาย |
|-----|--------|----------|
| V13 | Integer | จำนวนต้นแข็งแรง (Healthy) |
| V16 | Integer | จำนวนต้นผิดปกติ (UnHealthy) |
| V17 | String | URL ภาพผลลัพธ์ |
| V18 | String | ข้อความสถานะปัจจุบัน |

---

## 🔗 Links

- **GitHub:** https://github.com/FameKungGGEZ/SmartFarm
- **Server (Render):** https://smartfarm-9epw.onrender.com
- **Dashboard:** https://smartfarm-9epw.onrender.com/
- **Result Image:** https://smartfarm-9epw.onrender.com/result.jpg
- **Stats API:** https://smartfarm-9epw.onrender.com/stats
