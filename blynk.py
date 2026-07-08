# =====================================================================
# blynk.py — จัดการการส่งข้อมูลขึ้น Blynk IoT Platform
# =====================================================================
# ไฟล์นี้รวบรวมฟังก์ชันทั้งหมดที่ใช้ติดต่อกับ Blynk
# แยกออกมาเพื่อให้ง่ายต่อการสลับ Platform ในอนาคต
# =====================================================================

import logging
import threading
import requests
from config import (
    BLYNK_TOKEN,
    BLYNK_API,
    BLYNK_PIN_HEALTHY,
    BLYNK_PIN_UNHEALTHY,
    BLYNK_PIN_RESULT_URL,
    BLYNK_PIN_STATUS,
)

# Logger เฉพาะโมดูลนี้
logger = logging.getLogger(__name__)


def _send_pin(pin: str, value) -> bool:
    """
    ส่งค่าไปยัง Blynk พินเดียว (internal)

    Args:
        pin: Virtual pin เช่น "V13"
        value: ค่าที่ต้องการส่ง (int, float, หรือ str)

    Returns:
        True ถ้าสำเร็จ, False ถ้าล้มเหลว
    """
    try:
        params = {"token": BLYNK_TOKEN, pin: value}
        resp = requests.get(BLYNK_API, params=params, timeout=10)
        if resp.status_code == 200:
            return True
        logger.warning(f"Blynk pin {pin} ตอบกลับ HTTP {resp.status_code}: {resp.text[:100]}")
        return False
    except requests.exceptions.Timeout:
        logger.error(f"Blynk timeout ที่ pin {pin}")
        return False
    except requests.exceptions.ConnectionError:
        logger.error(f"Blynk เชื่อมต่อไม่ได้ที่ pin {pin}")
        return False
    except Exception as e:
        logger.error(f"Blynk error ที่ pin {pin}: {e}")
        return False


def update_blynk(values: dict) -> bool:
    """
    ส่งค่าหลายพินขึ้น Blynk พร้อมกัน
    ถ้าส่งไม่สำเร็จจะ log error โดยไม่ raise exception

    Args:
        values: dict ของ {pin: value} เช่น {"V13": 5, "V18": "สถานะ"}

    Returns:
        True ถ้าทุกพินสำเร็จ
    """
    success = True
    for pin, value in values.items():
        if not _send_pin(pin, value):
            success = False
    return success


def set_status(message: str) -> bool:
    """
    อัพเดตข้อความสถานะบน Blynk V18 เพียงอย่างเดียว
    ใช้บ่อยระหว่างการประมวลผลเพื่อแจ้งความคืบหน้า

    Args:
        message: ข้อความสถานะ เช่น "🌿 กำลังค้นหาต้นกรีนโอ๊ค..."
    """
    logger.info(f"☁️  Blynk Status → {message}")
    return _send_pin(BLYNK_PIN_STATUS, message)


def set_status_async(message: str):
    """
    อัพเดตสถานะแบบ Non-blocking (ใช้ background thread)
    เหมาะสำหรับอัพเดตระหว่างขั้นตอนที่ต้องการความเร็ว

    Args:
        message: ข้อความสถานะ
    """
    t = threading.Thread(
        target=set_status,
        args=(message,),
        daemon=True,
        name="BlynkStatusUpdate"
    )
    t.start()


def set_scan_result(healthy: int, unhealthy: int, result_url: str) -> bool:
    """
    อัพเดตผลการสแกนทั้งหมดขึ้น Blynk ในครั้งเดียว

    Args:
        healthy: จำนวนต้นแข็งแรง
        unhealthy: จำนวนต้นผิดปกติ
        result_url: URL ภาพผลลัพธ์

    Returns:
        True ถ้าทุกพินสำเร็จ
    """
    total = healthy + unhealthy

    # สร้างข้อความสรุปผล
    if total == 0:
        status = (
            "⚠️ ไม่พบต้นกรีนโอ๊คในภาพนี้\n"
            "ต้นทั้งหมด 0 ต้น\n"
            "ต้นแข็งแรง 0 ต้น\n"
            "ต้นผิดปกติ 0 ต้น"
        )
    else:
        status = (
            f"✅ ตรวจสอบเสร็จแล้ว\n"
            f"📊 ผลการตรวจ\n"
            f"ต้นทั้งหมด {total} ต้น\n"
            f"ต้นแข็งแรง {healthy} ต้น\n"
            f"ต้นผิดปกติ {unhealthy} ต้น"
        )

    logger.info(f"☁️  Blynk Result → Healthy:{healthy} UnHealthy:{unhealthy} Total:{total}")

    return update_blynk({
        BLYNK_PIN_HEALTHY: healthy,
        BLYNK_PIN_UNHEALTHY: unhealthy,
        BLYNK_PIN_RESULT_URL: result_url,
        BLYNK_PIN_STATUS: status,
    })


def set_photo_received(photo_url: str) -> bool:
    """
    แจ้ง Blynk ว่ารับภาพใหม่แล้ว อัพเดต URL ภาพล่าสุด

    Args:
        photo_url: URL ภาพที่รับมาจาก ESP32-CAM
    """
    return _send_pin(BLYNK_PIN_RESULT_URL, photo_url)
