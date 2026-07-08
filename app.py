# =====================================================================
# app.py — SmartFarm AI Server V2 (Entry Point)
# =====================================================================
# เซิร์ฟเวอร์หลักสำหรับระบบตรวจสุขภาพต้นกรีนโอ๊คอัตโนมัติ
#
# Flow การทำงาน:
#   1. ESP32-CAM ถ่ายภาพ → POST /upload
#   2. Server crop ต้นตาม Fixed Zone เป็น 96x96
#   3. ESP32 ขอ crop ทีละต้น → GET /crop?session=XXX&index=N
#   4. Edge Impulse วิเคราะห์ → POST /result?session=XXX&index=N
#   5. ESP32 แจ้งครบ → POST /finalize?session=XXX
#   6. Server สร้าง result.jpg
#
# APIs (ต้องคงไว้ ห้ามเปลี่ยน):
#   POST /upload   — รับภาพจาก ESP32
#   GET  /crop     — ส่ง crop ให้ ESP32
#   POST /result   — รับผลวิเคราะห์จาก ESP32
#   POST /finalize — สรุปผล
# =====================================================================

import os
import time
import threading
import logging
import numpy as np
import cv2
from datetime import datetime
from flask import Flask, request, jsonify, Response

from config import (
    HOST, PORT, DEBUG,
    UPLOAD_DIR,
    LATEST_PHOTO_FILENAME,
)
from image_processor import find_fixed_zone_crops, save_result_image
from session import SessionManager
from dashboard import dashboard_bp, init_dashboard, update_stats
from zones import load_zones, save_zones, validate_zones

# -------------------------------------------------------
# ตั้งค่า Logging — แสดงผลใน Console แบบ SmartFarm V2
# -------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("SmartFarm")

# -------------------------------------------------------
# แสดง Banner ตอนเริ่มระบบ
# -------------------------------------------------------
BANNER = """
=================================================
   SmartFarm AI Server V2
=================================================
"""

# -------------------------------------------------------
# สร้าง Flask App และ Session Manager
# -------------------------------------------------------
app = Flask(__name__)

# Session Manager: Thread-Safe, Auto Cleanup
session_manager = SessionManager()

# Stats shared กับ Dashboard
_stats: dict = {
    "healthy": 0,
    "unhealthy": 0,
    "total": 0,
    "last_scan": None,
    "status": "🟢 ระบบพร้อมใช้งาน",
}
_stats_lock = threading.Lock()

# เชื่อม Dashboard Blueprint
app.register_blueprint(dashboard_bp)
init_dashboard(_stats, _stats_lock)

# path ภาพล่าสุด
LATEST_PHOTO_PATH = os.path.join(UPLOAD_DIR, LATEST_PHOTO_FILENAME)


# =====================================================================
# Helper Functions
# =====================================================================

def _update_status(message: str) -> None:
    """อัพเดตสถานะใน stats dict (แสดงบน Dashboard)"""
    with _stats_lock:
        _stats["status"] = message


def _build_result_url(base_url: str) -> str:
    """
    สร้าง URL สำหรับภาพผลลัพธ์จาก base URL ของ request

    Args:
        base_url: request.url_root เช่น "https://example.com/"

    Returns:
        URL เต็มของ result.jpg เช่น "https://example.com/result.jpg"
    """
    return base_url.rstrip("/") + "/result.jpg"


# =====================================================================
# ESP32 API Routes — ห้ามเปลี่ยน endpoint หรือ response format
# =====================================================================

@app.route("/upload", methods=["POST"])
def upload():
    """
    รับภาพ JPEG จาก ESP32-CAM และหาต้นกรีนโอ๊ค

    Request:
        Body: raw JPEG bytes

    Response JSON:
        session (str): Session ID สำหรับใช้ขั้นตอนถัดไป
        crops   (int): จำนวนต้นที่พบ (0 ถ้าไม่พบ)

    ขั้นตอน:
        1. รับและ decode ภาพ
        2. บันทึก latest.jpg
        3. ค้นหาต้นกรีนโอ๊ค
        4. สร้าง session
        5. อัพเดต Dashboard สถานะเริ่มต้น
    """
    print("\n" + "=" * 50)
    print("📷 รับภาพจาก ESP32")

    # ---- รับข้อมูลภาพ ----
    img_bytes = request.get_data()
    if not img_bytes:
        logger.warning("Upload: ไม่มีข้อมูลภาพ")
        return jsonify({"error": "no image data"}), 400

    # ---- Decode JPEG → numpy array ----
    np_arr = np.frombuffer(img_bytes, dtype=np.uint8)
    image_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if image_bgr is None:
        logger.error("Upload: decode ภาพไม่สำเร็จ")
        return jsonify({"error": "image decode failed"}), 400

    logger.info(f"Upload: รับภาพสำเร็จ {image_bgr.shape[1]}x{image_bgr.shape[0]}px")

    # ---- บันทึก latest.jpg ----
    cv2.imwrite(LATEST_PHOTO_PATH, image_bgr)
    photo_url = request.url_root.rstrip("/") + "/latest.jpg"
    result_url = _build_result_url(request.url_root)

    _update_status("📸 รับภาพสำเร็จ")

    # ---- Crop ต้นไม้ด้วย Fixed Zone ----
    _update_status("🌿 กำลัง crop ต้นกรีนโอ๊ค...")
    print("🌿 กำลัง crop ต้นกรีนโอ๊ค (Fixed Zone)...")

    zones = load_zones()
    crops, bboxes = find_fixed_zone_crops(image_bgr, zones)
    plant_count = len(crops)
    print(f"crop ได้ทั้งหมด {plant_count} ต้น ({len(zones)} โซน)")

    # ---- สร้าง Session ----
    session_id = str(int(time.time() * 1000))
    session_manager.create(
        session_id=session_id,
        crops=crops,
        bboxes=bboxes,
        image_bgr=image_bgr,
        photo_url=photo_url,
    )

    # ---- อัพเดตสถานะตามผล ----
    if plant_count == 0:
        no_plant_msg = (
            "⚠️ ไม่พบต้นกรีนโอ๊คในภาพนี้\n"
            "ต้นทั้งหมด 0 ต้น\n"
            "ต้นแข็งแรง 0 ต้น\n"
            "ต้นผิดปกติ 0 ต้น"
        )
        _update_status(no_plant_msg)
        update_stats(0, 0, no_plant_msg)
        logger.info("Upload: zones โหลดได้ 0 ต้น (ตรวจสอบ zones.json)")
    else:
        status_msg = f"🌱 crop ต้นกรีนโอ๊คทั้งหมด {plant_count} ต้น"
        _update_status(status_msg)
        logger.info(f"Upload: crop {plant_count} ต้น → สร้าง session [{session_id}]")

    return jsonify({"session": session_id, "crops": plant_count})


@app.route("/crop", methods=["GET"])
def get_crop():
    """
    ส่งภาพ crop 96x96 ให้ ESP32 นำไปวิเคราะห์ด้วย Edge Impulse

    Query params:
        session (str): Session ID จาก /upload
        index   (int): ลำดับต้น (0-based)

    Response:
        application/octet-stream: RGB888 raw bytes (96*96*3 = 27648 bytes)
        ตรงกับ format ที่ Edge Impulse ต้องการพอดี
    """
    session_id = request.args.get("session", "")
    try:
        index = int(request.args.get("index", -1))
    except ValueError:
        return jsonify({"error": "index ต้องเป็นตัวเลข"}), 400

    # แจ้งความคืบหน้า
    _update_status(f"🤖 กำลังวิเคราะห์ต้นที่ {index + 1}")

    # ดึง session
    session = session_manager.get(session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404

    if index < 0 or index >= session.total_plants:
        return jsonify({"error": "index out of range"}), 404

    # ดึง crop RGB โดยไม่ต้อง copy (slice reference)
    crop_rgb = session.crops[index]

    # ส่งเป็น raw bytes RGB888
    raw_bytes = crop_rgb.tobytes()
    return Response(raw_bytes, mimetype="application/octet-stream")


@app.route("/result", methods=["POST"])
def post_result():
    """
    รับผลการวิเคราะห์จาก Edge Impulse บน ESP32

    Query params:
        session (str): Session ID
        index   (int): ลำดับต้น (0-based)
        label   (str): "Healthy" หรือ "UnHealthy"
        conf    (str): ค่า confidence เช่น "98.52"

    Response JSON:
        ok (bool): True ถ้าบันทึกสำเร็จ
    """
    session_id = request.args.get("session", "")
    label = request.args.get("label", "")
    conf = request.args.get("conf", "0")

    try:
        index = int(request.args.get("index", -1))
    except ValueError:
        return jsonify({"error": "index ต้องเป็นตัวเลข"}), 400

    # ดึง session
    session = session_manager.get(session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404

    # บันทึกผล
    if not session.set_result(index, label, conf):
        return jsonify({"error": "index out of range"}), 404

    # แสดงผลใน Console
    emoji = "✅" if label == "Healthy" else "❌"
    print(f"  Plant #{index + 1}")
    print(f"  {emoji} {label}")
    print(f"  {float(conf):.2f}%")

    logger.info(
        f"Result [{session_id}] "
        f"ต้นที่ {index + 1}: {label} {conf}% "
        f"({session.completed_count}/{session.total_plants})"
    )

    # อัพเดตสถานะบน Dashboard
    remaining = session.total_plants - session.completed_count
    if remaining > 0:
        _update_status(
            f"🤖 กำลังวิเคราะห์ต้นที่ {session.completed_count + 1} "
            f"จาก {session.total_plants}"
        )

    return jsonify({"ok": True})


@app.route("/finalize", methods=["POST"])
def finalize():
    """
    สรุปผลการตรวจทั้งหมด สร้าง result.jpg และอัพเดต Dashboard

    Query params:
        session (str): Session ID

    Response JSON:
        ok       (bool): True ถ้าสำเร็จ
        healthy  (int):  จำนวนต้นแข็งแรง
        unhealthy(int):  จำนวนต้นผิดปกติ
        total    (int):  จำนวนต้นทั้งหมด

    ขั้นตอน:
        1. รวบรวมผลทั้งหมด
        2. สร้างและบันทึก result.jpg
        3. อัพเดต Dashboard stats
        4. ลบ session ออกจาก memory
    """
    session_id = request.args.get("session", "")

    # ดึง session
    session = session_manager.get(session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404

    # ---- สรุปผล ----
    summary = session.get_summary()
    healthy = summary["healthy"]
    unhealthy = summary["unhealthy"]
    total = summary["total"]

    print("\n🖼  กำลังสร้าง Result.jpg")
    print(f"   Healthy: {healthy}  |  UnHealthy: {unhealthy}  |  Total: {total}")

    # ---- สร้าง result.jpg ----
    _update_status("🖼 กำลังสร้างภาพผลลัพธ์...")

    # บันทึกภาพผลลัพธ์พร้อมกรอบ
    if session.image_bgr is not None and len(session.bboxes) > 0:
        save_result_image(session.image_bgr, session.bboxes, session.results)
    else:
        logger.warning(f"Finalize [{session_id}]: ไม่มีภาพหรือ bboxes สำหรับสร้าง result")

    # ---- อัพเดต stats สำหรับ Dashboard ----
    final_status = (
        f"✅ ตรวจสอบเสร็จแล้ว\n"
        f"📊 ผลการตรวจ\n"
        f"ต้นทั้งหมด {total} ต้น\n"
        f"ต้นแข็งแรง {healthy} ต้น\n"
        f"ต้นผิดปกติ {unhealthy} ต้น"
    )
    update_stats(healthy, unhealthy, final_status)

    print("✔  สำเร็จ")
    print("\nWaiting next image...\n")
    logger.info(
        f"Finalize [{session_id}]: "
        f"Healthy={healthy} UnHealthy={unhealthy} Total={total}"
    )

    # ---- ลบ session ออกจาก memory ----
    session_manager.delete(session_id)

    return jsonify({
        "ok": True,
        "healthy": healthy,
        "unhealthy": unhealthy,
        "total": total,
    })


# =====================================================================
# Calibration Routes — ปรับโซน crop ผ่าน Web UI
# =====================================================================

@app.route("/latest.jpg")
def serve_latest():
    """ส่งภาพล่าสุดสำหรับ calibration preview"""
    import mimetypes
    path = LATEST_PHOTO_PATH
    if not os.path.exists(path):
        return jsonify({"error": "ยังไม่มีภาพ — ส่งภาพจาก ESP32 ก่อน"}), 404
    with open(path, "rb") as f:
        data = f.read()
    return Response(data, mimetype="image/jpeg")


@app.route("/result.jpg")
def serve_result():
    """ส่งภาพผลลัพธ์ล่าสุด"""
    path = os.path.join(UPLOAD_DIR, "result.jpg")
    if not os.path.exists(path):
        return jsonify({"error": "ยังไม่มี result image"}), 404
    with open(path, "rb") as f:
        data = f.read()
    return Response(data, mimetype="image/jpeg")


@app.route("/calibrate")
def calibrate_page():
    """หน้า Web UI สำหรับปรับตำแหน่งโซนแบบ interactive"""
    from flask import render_template
    return render_template("calibrate.html")


@app.route("/api/zones", methods=["GET"])
def api_get_zones():
    """
    ดึงโซน crop ปัจจุบัน

    Response JSON:
        zones: รายการโซน [{"id":1,"x":0.0,"y":0.0,"w":0.0,"h":0.0}, ...]
    """
    return jsonify({"zones": load_zones()})


@app.route("/api/zones", methods=["POST"])
def api_set_zones():
    """
    บันทึกโซน crop ใหม่

    Request JSON:
        zones: รายการโซน (รูปแบบเดียวกับ GET)

    Response JSON:
        ok    (bool): True ถ้าสำเร็จ
        count (int):  จำนวนโซนที่บันทึก
    """
    data = request.get_json(force=True, silent=True)
    if not data or "zones" not in data:
        return jsonify({"error": "ต้องส่ง JSON body ที่มี field 'zones'"}), 400

    zones = data["zones"]
    valid, err = validate_zones(zones)
    if not valid:
        return jsonify({"error": err}), 400

    try:
        save_zones(zones)
    except IOError as e:
        logger.error(f"บันทึกโซนไม่สำเร็จ: {e}")
        return jsonify({"error": "บันทึกไฟล์ไม่สำเร็จ"}), 500

    logger.info(f"📐 อัพเดตโซน: {len(zones)} โซน")
    return jsonify({"ok": True, "count": len(zones)})


# =====================================================================
# Startup
# =====================================================================

def _print_startup_info() -> None:
    """แสดงข้อมูลตอนเริ่ม server"""
    print(BANNER)
    print(f"🌐 Server: http://0.0.0.0:{PORT}")
    print(f"📁 Upload dir: {os.path.abspath(UPLOAD_DIR)}")
    print()


if __name__ == "__main__":
    _print_startup_info()
    app.run(host=HOST, port=PORT, debug=DEBUG, threaded=True)
