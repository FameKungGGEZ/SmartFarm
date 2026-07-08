# 🌿 SmartFarm AI Server V2

ระบบ Backend สำหรับตรวจสุขภาพต้นกรีนโอ๊คอัตโนมัติ  
ทำงานร่วมกับ **ESP32-CAM + Edge Impulse + OpenCV + Blynk**

---

## 🏗️ โครงสร้างไฟล์

```
smartfarm_v2/
├── app.py               ← Entry point (Flask + ESP32 API Routes)
├── config.py            ← ตั้งค่าทั้งหมด (Blynk token, paths, thresholds)
├── blynk.py             ← จัดการการส่งข้อมูลขึ้น Blynk
├── image_processor.py   ← ค้นหาต้นไม้ + สร้าง result.jpg
├── session.py           ← Session Manager (Thread-Safe + Auto Cleanup)
├── dashboard.py         ← Blueprint สำหรับ Dashboard + /stats
├── templates/
│   └── index.html       ← Dashboard UI (Auto Refresh ทุก 5 วิ)
├── photos/              ← เก็บ latest.jpg และ result.jpg (auto-created)
├── requirements.txt
├── Procfile             ← สำหรับ Render / Koyeb / Railway
├── runtime.txt
└── .gitignore
```

---

## 🔄 Flow การทำงาน

```
ESP32-CAM
  │
  ├─ POST /upload      ← ส่งภาพ JPEG ดิบ
  │     └─ Server: ค้นหาต้น → Crop 96x96 → สร้าง Session
  │
  ├─ GET  /crop        ← ขอ crop ทีละต้น (RGB888 raw)
  │     └─ Server: ส่ง bytes ให้ Edge Impulse วิเคราะห์
  │
  ├─ POST /result      ← ส่งผล Healthy/UnHealthy + confidence
  │     └─ Server: บันทึกผลลงใน Session
  │
  └─ POST /finalize    ← แจ้งตรวจครบแล้ว
        └─ Server: สร้าง result.jpg + อัพเดต Blynk + ลบ Session
```

---

## ⚡ การติดตั้งและรัน

### รันในเครื่อง (Local)

```bash
# 1. Clone หรือวางไฟล์ลงในโฟลเดอร์
cd smartfarm_v2

# 2. สร้าง Virtual Environment
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 3. ติดตั้ง dependencies
pip install -r requirements.txt

# 4. ตั้งค่า Blynk Token (เลือกอย่างใดอย่างหนึ่ง)
# วิธีที่ 1: แก้ config.py โดยตรง
# วิธีที่ 2: ใช้ environment variable
export BLYNK_TOKEN="your_token_here"   # Linux/Mac
set BLYNK_TOKEN=your_token_here        # Windows

# 5. รัน Server
python app.py
```

เปิด `http://localhost:5000` เพื่อดู Dashboard

---

### Deploy บน Render

1. Push โค้ดขึ้น GitHub
2. สร้าง New Web Service บน [render.com](https://render.com)
3. เชื่อมกับ Repository
4. ตั้งค่า:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT`
5. เพิ่ม Environment Variable: `BLYNK_TOKEN=your_token`

---

### Deploy บน Koyeb

```bash
# ใช้ Koyeb CLI
koyeb app init smartfarm
koyeb service create smartfarm \
  --app smartfarm \
  --git github.com/youruser/smartfarm_v2 \
  --git-branch main \
  --env BLYNK_TOKEN=your_token \
  --ports 8000:http
```

---

### Deploy ด้วย Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p photos
EXPOSE 5000
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4"]
```

```bash
docker build -t smartfarm-v2 .
docker run -p 5000:5000 -e BLYNK_TOKEN=your_token smartfarm-v2
```

---

## 📡 API Reference

### `POST /upload`
รับภาพ JPEG จาก ESP32-CAM

```
Body: raw JPEG bytes (Content-Type: application/octet-stream)
Response: {"session": "1720354614000", "crops": 12}
```

### `GET /crop?session={id}&index={n}`
ส่ง crop RGB888 ขนาด 96x96 ให้ Edge Impulse

```
Response: application/octet-stream (27648 bytes)
```

### `POST /result?session={id}&index={n}&label={label}&conf={conf}`
รับผลการวิเคราะห์

```
label: "Healthy" หรือ "UnHealthy"
conf:  ค่า confidence เช่น "98.52"
Response: {"ok": true}
```

### `POST /finalize?session={id}`
สรุปผลและอัพเดต Blynk

```
Response: {"ok": true, "healthy": 10, "unhealthy": 2, "total": 12}
```

### `GET /stats`
ดึงสถิติล่าสุด

```json
{
  "healthy": 10,
  "unhealthy": 2,
  "total": 12,
  "last_scan": "2026-07-07 15:30:00",
  "status": "✅ ตรวจสอบเสร็จแล้ว"
}
```

---

## 📌 Blynk Virtual Pins

| Pin  | ประเภท  | ความหมาย              |
|------|---------|----------------------|
| V13  | Integer | จำนวนต้นแข็งแรง (Healthy)   |
| V16  | Integer | จำนวนต้นผิดปกติ (UnHealthy) |
| V17  | String  | URL ภาพผลลัพธ์              |
| V18  | String  | ข้อความสถานะปัจจุบัน        |

---

## ⚙️ การปรับแต่ง

แก้ไข `config.py`:

```python
# เพิ่มจำนวนต้นสูงสุดต่อภาพ
MAX_CROPS_PER_PHOTO = 30

# ปรับขนาด crop (ต้องตรงกับโมเดล)
CROP_SIZE = 96

# ปรับช่วงสีเขียว HSV
GREEN_HSV_LOWER = (25, 40, 40)
GREEN_HSV_UPPER = (95, 255, 255)

# ปรับ timeout session
SESSION_TIMEOUT = 600  # วินาที
```

---

## 🛠️ Tech Stack

- **Flask 3.0** — Web Framework
- **OpenCV 4.10** — Image Processing
- **NumPy** — Array operations
- **Requests** — Blynk HTTP API
- **Gunicorn** — Production WSGI Server
- **Threading** — Concurrent session management
