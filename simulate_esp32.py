# =====================================================================
# simulate_esp32.py — จำลองการทำงานของ ESP32-CAM บน PC
# =====================================================================
# ใช้สำหรับทดสอบระบบโดยไม่ต้องมีบอร์ดจริง
# ขั้นตอนเดียวกับ ESP32:
#   1. POST รูปไป /upload
#   2. GET /crop ทีละต้น
#   3. POST /result (จำลองผล AI)
#   4. POST /finalize
# =====================================================================

import sys
import requests
import random

SERVER = "http://127.0.0.1:5000"

def simulate(image_path: str):
    print(f"\n{'='*50}")
    print(f"📷  ส่งภาพ: {image_path}")

    # ---- 1. Upload ----
    with open(image_path, "rb") as f:
        img_bytes = f.read()

    print(f"   ขนาดภาพ: {len(img_bytes):,} bytes")
    r = requests.post(
        f"{SERVER}/upload",
        data=img_bytes,
        headers={"Content-Type": "image/jpeg"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    session   = data["session"]
    crop_count = data["crops"]
    print(f"✅  Session: {session}")
    print(f"🌿  พบโซน/ต้น: {crop_count} ต้น")

    if crop_count == 0:
        print("⚠️  ไม่พบต้นไม้ในภาพ (ตรวจสอบ zones.json)")
        return

    # ---- 2–3. ขอ crop → จำลอง AI → ส่งผลกลับ ----
    # จำลอง AI: สุ่ม Healthy/UnHealthy โดย Healthy มีโอกาส 70%
    print(f"\n{'─'*40}")
    print("🤖  จำลองผล Edge Impulse AI:")
    for i in range(crop_count):
        # GET crop (แค่เช็คว่า server ส่งได้ถูกต้อง)
        rc = requests.get(
            f"{SERVER}/crop",
            params={"session": session, "index": i},
            timeout=15,
        )
        if rc.status_code != 200:
            print(f"  ⚠️  ต้น #{i+1}: ขอ crop ไม่ได้ ({rc.status_code})")
            continue
        if len(rc.content) != 96 * 96 * 3:
            print(f"  ⚠️  ต้น #{i+1}: ขนาด crop ผิด ({len(rc.content)} bytes)")
            continue

        # จำลองผล AI
        label = "Healthy" if random.random() < 0.70 else "UnHealthy"
        conf  = round(random.uniform(80.0, 99.0), 2)
        emoji = "✅" if label == "Healthy" else "❌"
        print(f"  {emoji}  ต้นที่ {i+1}: {label}  {conf:.1f}%  (crop {len(rc.content):,} bytes OK)")

        # POST result
        requests.post(
            f"{SERVER}/result",
            params={"session": session, "index": i, "label": label, "conf": conf},
            timeout=10,
        )

    # ---- 4. Finalize ----
    rf = requests.post(f"{SERVER}/finalize", params={"session": session}, timeout=15)
    rf.raise_for_status()
    summary = rf.json()
    print(f"\n{'─'*40}")
    print(f"📊  สรุปผล:")
    print(f"   ✅ Healthy   : {summary['healthy']} ต้น")
    print(f"   ❌ UnHealthy : {summary['unhealthy']} ต้น")
    print(f"   📦 Total     : {summary['total']} ต้น")
    print(f"\n🖼   ดูผลได้ที่ {SERVER}/result.jpg")
    print(f"🌐  Dashboard : {SERVER}")
    print('='*50 + "\n")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\fame2\Downloads\images_of_Tree_test\Tree_1783503264567.jpg"
    simulate(path)
