# =====================================================================
# dashboard.py — Blueprint สำหรับ Dashboard และ Static Routes
# =====================================================================
# จัดการ routes ที่ไม่ใช่ ESP32 API:
#   - GET /          → หน้า Dashboard HTML
#   - GET /latest.jpg → ภาพล่าสุดจาก ESP32-CAM
#   - GET /result.jpg → ภาพผลการตรวจพร้อมกรอบ
#   - GET /stats      → JSON สรุปสถิติล่าสุด
# =====================================================================

import os
import threading
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from flask import Blueprint, render_template, send_file, jsonify

from config import UPLOAD_DIR, LATEST_PHOTO_FILENAME, RESULT_PHOTO_FILENAME

# Logger เฉพาะโมดูลนี้
logger = logging.getLogger(__name__)

# สร้าง Blueprint ชื่อ "dashboard"
dashboard_bp = Blueprint("dashboard", __name__)

# -------------------------------------------------------
# Global stats — ข้อมูลสรุปล่าสุด (share กับ app.py)
# -------------------------------------------------------
# ค่าเริ่มต้นตอนเปิด server
_stats: Dict[str, Any] = {
    "healthy": 0,
    "unhealthy": 0,
    "total": 0,
    "last_scan": None,       # ISO string หรือ None
    "status": "🟢 ระบบพร้อมใช้งาน",
}
_stats_lock = threading.Lock()


def init_dashboard(stats: Dict[str, Any], lock: threading.Lock) -> None:
    """
    เชื่อมต่อ stats dict และ lock จาก app.py หลัก
    เรียกใช้ครั้งเดียวตอน create_app()

    Args:
        stats: dict เดียวกับที่ใช้ใน app.py
        lock: threading.Lock เดียวกัน
    """
    global _stats, _stats_lock
    _stats = stats
    _stats_lock = lock
    logger.info("Dashboard เชื่อมต่อ stats สำเร็จ")


def update_stats(
    healthy: int,
    unhealthy: int,
    status: str,
    scan_time: Optional[datetime] = None,
) -> None:
    """
    อัพเดตสถิติล่าสุด (เรียกจาก app.py หลังตรวจเสร็จ)

    Args:
        healthy: จำนวนต้นแข็งแรง
        unhealthy: จำนวนต้นผิดปกติ
        status: ข้อความสถานะ
        scan_time: เวลาที่สแกน (ถ้าไม่ส่งมาใช้เวลาปัจจุบัน)
    """
    if scan_time is None:
        scan_time = datetime.now()

    with _stats_lock:
        _stats["healthy"] = healthy
        _stats["unhealthy"] = unhealthy
        _stats["total"] = healthy + unhealthy
        _stats["last_scan"] = scan_time.strftime("%Y-%m-%d %H:%M:%S")
        _stats["status"] = status


# -------------------------------------------------------
# Routes
# -------------------------------------------------------

@dashboard_bp.route("/")
def index():
    """
    หน้า Dashboard หลัก — แสดงสถานะ Server, Latest Photo,
    Result Photo, จำนวน Healthy/UnHealthy/Total และ Last Scan
    """
    return render_template("index.html")


@dashboard_bp.route("/latest.jpg")
def latest_photo():
    """
    ส่งภาพล่าสุดที่ได้รับจาก ESP32-CAM
    คืน 404 ถ้ายังไม่มีภาพ
    """
    path = os.path.join(UPLOAD_DIR, LATEST_PHOTO_FILENAME)
    if not os.path.exists(path):
        return jsonify({"error": "ยังไม่มีภาพ"}), 404
    return send_file(path, mimetype="image/jpeg")


@dashboard_bp.route("/result.jpg")
def result_photo():
    """
    ส่งภาพผลการตรวจพร้อมกรอบสีและ header สรุป
    คืน 404 ถ้ายังไม่มีภาพผลลัพธ์
    """
    path = os.path.join(UPLOAD_DIR, RESULT_PHOTO_FILENAME)
    if not os.path.exists(path):
        return jsonify({"error": "ยังไม่มีภาพผลลัพธ์"}), 404
    return send_file(path, mimetype="image/jpeg")


@dashboard_bp.route("/stats")
def get_stats():
    """
    API คืนสถิติล่าสุด ใช้โดย Dashboard frontend และ external tools

    Response JSON:
        healthy    (int)    จำนวนต้นแข็งแรง
        unhealthy  (int)    จำนวนต้นผิดปกติ
        total      (int)    จำนวนต้นทั้งหมด
        last_scan  (str)    วันที่-เวลาสแกนล่าสุด หรือ null
        status     (str)    ข้อความสถานะปัจจุบัน
    """
    with _stats_lock:
        snapshot = dict(_stats)
    return jsonify(snapshot)
