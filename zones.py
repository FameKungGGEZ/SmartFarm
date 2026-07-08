# =====================================================================
# zones.py — จัดการโซน crop แบบ Fixed Grid
# =====================================================================
# แทนที่การ detect สีเขียว HSV ด้วยตำแหน่งคงที่ที่ผู้ใช้กำหนดเอง
# พิกัดเก็บเป็น สัดส่วน 0.0–1.0 ของขนาดภาพ (รองรับทุก resolution)
#
# zone schema:
#   { "id": 1, "x": 0.02, "y": 0.02, "w": 0.38, "h": 0.30 }
#   x,y = มุมซ้ายบน, w,h = ความกว้าง/สูง  (ทุกค่าเป็น fraction 0–1)
# =====================================================================

import json
import os
import logging

logger = logging.getLogger(__name__)

# ไฟล์เก็บโซน — เปลี่ยนได้ผ่าน ENV ZONES_FILE
ZONES_FILE: str = os.environ.get("ZONES_FILE", "zones.json")

# -------------------------------------------------------
# โซน default: 6 ต้น ในแนว 2 คอลัมน์ × 3 แถว
# ปรับให้ตรงกับภาพจริงผ่านหน้า /calibrate
# -------------------------------------------------------
# พิกัด calibrate จากภาพจริง ESP32-CAM (ต้นกรีนโอ๊ค 6 ต้น)
# เลย์เอาต์: 2 คอลัมน์ × 3 แถว มีช่องน้ำสีขาวคั่นกลาง
# โซนเป็นสี่เหลี่ยมจัตุรัส w == h == 0.30
#   center ซ้าย  cx=0.225, center ขวา cx=0.775
#   แถวบน cy=0.17, แถวกลาง cy=0.495, แถวล่าง cy=0.825
DEFAULT_ZONES: list = [
    {"id": 1, "x": 0.075, "y": 0.020, "w": 0.30, "h": 0.30},   # แถว1-ซ้าย
    {"id": 2, "x": 0.625, "y": 0.020, "w": 0.30, "h": 0.30},   # แถว1-ขวา
    {"id": 3, "x": 0.075, "y": 0.345, "w": 0.30, "h": 0.30},   # แถว2-ซ้าย
    {"id": 4, "x": 0.625, "y": 0.345, "w": 0.30, "h": 0.30},   # แถว2-ขวา
    {"id": 5, "x": 0.075, "y": 0.675, "w": 0.30, "h": 0.30},   # แถว3-ซ้าย
    {"id": 6, "x": 0.625, "y": 0.675, "w": 0.30, "h": 0.30},   # แถว3-ขวา
]

# สีแสดงแต่ละโซนบนหน้า calibrate (BGR สำหรับ OpenCV)
ZONE_COLORS_BGR: list = [
    (0, 215, 90),    # เขียวสด
    (0, 165, 255),   # ส้ม
    (255, 100, 50),  # น้ำเงิน
    (200, 50, 255),  # ม่วง
    (50, 230, 230),  # เหลือง
    (0, 100, 255),   # แดง
]


def load_zones() -> list:
    """
    โหลดโซนจากไฟล์ zones.json
    ถ้าไม่มีไฟล์ หรือ parse ไม่ได้ → คืน DEFAULT_ZONES
    """
    if os.path.exists(ZONES_FILE):
        try:
            with open(ZONES_FILE, encoding="utf-8") as f:
                zones = json.load(f)
            logger.info(f"โหลดโซนสำเร็จ: {len(zones)} โซน จาก {ZONES_FILE}")
            return zones
        except Exception as e:
            logger.warning(f"โหลดโซนไม่สำเร็จ ({e}) → ใช้ค่า default")
    return list(DEFAULT_ZONES)


def save_zones(zones: list) -> None:
    """
    บันทึกโซนลง zones.json
    Raises IOError ถ้าบันทึกไม่ได้
    """
    with open(ZONES_FILE, "w", encoding="utf-8") as f:
        json.dump(zones, f, indent=2, ensure_ascii=False)
    logger.info(f"บันทึกโซนสำเร็จ: {len(zones)} โซน → {ZONES_FILE}")


def validate_zones(zones: list) -> tuple[bool, str]:
    """
    ตรวจสอบว่า zones มีรูปแบบถูกต้อง

    Returns:
        (is_valid, error_message)
    """
    if not isinstance(zones, list) or len(zones) == 0:
        return False, "zones ต้องเป็น list และมีอย่างน้อย 1 โซน"

    for i, z in enumerate(zones):
        for key in ("id", "x", "y", "w", "h"):
            if key not in z:
                return False, f"โซน index {i} ขาด field '{key}'"
        for key in ("x", "y", "w", "h"):
            v = z[key]
            if not isinstance(v, (int, float)) or not (0.0 <= v <= 1.0):
                return False, f"โซน id={z.get('id')} field '{key}'={v} ต้องอยู่ระหว่าง 0.0–1.0"
        if z["x"] + z["w"] > 1.01 or z["y"] + z["h"] > 1.01:
            return False, f"โซน id={z.get('id')} เกินขอบภาพ (x+w หรือ y+h > 1.0)"

    return True, ""
