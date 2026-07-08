# =====================================================================
# image_processor.py — ประมวลผลภาพด้วย OpenCV
# =====================================================================
# ไฟล์นี้รับผิดชอบการ:
#   1. [Fixed Zone] Crop ต้นตามโซนที่ผู้ใช้กำหนด (find_fixed_zone_crops)
#   2. [Legacy]     ค้นหาต้นกรีนโอ๊คด้วยการกรองสีเขียว (find_green_oak_crops)
#   3. Crop ต้นออกมาเป็นภาพ 96x96 ส่งให้ Edge Impulse วิเคราะห์
#   4. วาดกรอบผลการตรวจลงบนภาพต้นฉบับ สร้าง result.jpg
# =====================================================================

import os
import logging
import numpy as np
import cv2
from datetime import datetime
from typing import List, Tuple, Dict, Optional, Any

from config import (
    CROP_SIZE,
    MAX_CROPS_PER_PHOTO,
    MIN_PLANT_AREA,
    MAX_PLANT_AREA_RATIO,
    NMS_IOU_THRESHOLD,
    PADDING_RATIO,
    GREEN_HSV_LOWER,
    GREEN_HSV_UPPER,
    UPLOAD_DIR,
    RESULT_PHOTO_FILENAME,
)

# Logger เฉพาะโมดูลนี้
logger = logging.getLogger(__name__)

# ประเภทสำหรับกรอบตำแหน่ง (x0, y0, x1, y1)
BBox = Tuple[int, int, int, int]


# -------------------------------------------------------
# NMS — ลบกรอบที่ซ้อนทับกันซ้ำ
# -------------------------------------------------------

def _nms_bboxes(bboxes: List[BBox], iou_threshold: float) -> List[int]:
    """
    Non-Maximum Suppression: คืน index ของกรอบที่ควรเก็บไว้

    เรียง bboxes จากพื้นที่ใหญ่ → เล็ก ถ้ากรอบไหน IoU กับกรอบที่
    เลือกไปแล้วเกิน iou_threshold → ตัดทิ้ง (ถือว่าตรวจต้นเดียวกัน)

    Args:
        bboxes: รายการ (x0, y0, x1, y1)
        iou_threshold: ค่า IoU สูงสุดที่ยอมให้ซ้อนกันได้

    Returns:
        รายการ index ที่ผ่าน NMS
    """
    if not bboxes:
        return []

    boxes = np.array(bboxes, dtype=float)
    x0 = boxes[:, 0]
    y0 = boxes[:, 1]
    x1 = boxes[:, 2]
    y1 = boxes[:, 3]
    areas = (x1 - x0) * (y1 - y0)

    # เรียงจากพื้นที่ใหญ่ไปเล็ก (ต้นใหญ่ได้สิทธิ์ก่อน)
    order = areas.argsort()[::-1]
    keep: List[int] = []

    while order.size > 0:
        i = int(order[0])
        keep.append(i)

        # คำนวณ IoU ระหว่างกรอบที่เลือกกับกรอบที่เหลือ
        ix0 = np.maximum(x0[i], x0[order[1:]])
        iy0 = np.maximum(y0[i], y0[order[1:]])
        ix1 = np.minimum(x1[i], x1[order[1:]])
        iy1 = np.minimum(y1[i], y1[order[1:]])

        inter_w = np.maximum(0.0, ix1 - ix0)
        inter_h = np.maximum(0.0, iy1 - iy0)
        inter   = inter_w * inter_h
        union   = areas[i] + areas[order[1:]] - inter + 1e-6
        iou     = inter / union

        # เก็บเฉพาะกรอบที่ไม่ซ้อนเกิน threshold
        order = order[1:][iou <= iou_threshold]

    return keep


# -------------------------------------------------------
# ส่วนค้นหาต้นไม้
# -------------------------------------------------------

def find_green_oak_crops(
    image_bgr: np.ndarray,
) -> Tuple[List[np.ndarray], List[BBox]]:
    """
    ค้นหาต้นกรีนโอ๊คในภาพด้วยการกรองสีเขียว HSV และ Morphological operations

    ขั้นตอน:
        1. แปลง BGR → HSV
        2. สร้าง mask สีเขียว
        3. ทำ morphological open (ลบ noise) / close (เชื่อมใบในต้นเดียว)
           — ใช้ kernel ขนาดเล็กลงและ iteration น้อยลง เพื่อไม่ให้
             ต้นที่อยู่ใกล้กันถูก merge เป็น blob เดียว
        4. หา contours กรองตามขนาด (ขั้นต่ำ + สูงสุด) และรูปร่าง
        5. ใช้ NMS กำจัดกรอบที่ซ้อนทับกัน (ตรวจต้นเดิมซ้ำ)
        6. Crop แต่ละก้อนพร้อมขยายขอบ 15%

    Args:
        image_bgr: ภาพต้นฉบับในรูปแบบ BGR (numpy array)

    Returns:
        crops: รายการภาพครอป RGB ขนาด 96x96 (ส่งให้ Edge Impulse)
        bboxes: รายการ (x0, y0, x1, y1) ของแต่ละต้นในภาพต้นฉบับ
    """
    h, w = image_bgr.shape[:2]
    max_area = h * w * MAX_PLANT_AREA_RATIO

    # ---- ขั้นตอนที่ 1: แปลงสีและสร้าง mask ----
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)

    lower = np.array(GREEN_HSV_LOWER, dtype=np.uint8)
    upper = np.array(GREEN_HSV_UPPER, dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)

    # ---- ขั้นตอนที่ 2: ทำความสะอาด mask ----
    # kernel 5×5 (ลดจาก 7×7) + CLOSE iterations=1 (ลดจาก 2)
    # เหตุผล: kernel ใหญ่/iterations มาก → เชื่อมต้นข้างเคียงเป็น blob เดียว
    #          ทำให้ฝั่งซ้าย 3 ต้น merge เป็น column เดียว aspect ratio > 3.5
    #          และโดน is_plant_shape กรองออกไป
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel, iterations=1)  # ลบจุดเล็ก
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)  # เชื่อมใบในต้นเดียว

    # ---- ขั้นตอนที่ 3: หา contours ----
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # กรองพื้นที่: ต้องอยู่ระหว่าง MIN_PLANT_AREA ถึง max_area
    # — ต่ำกว่า MIN = noise, สูงกว่า max = หลายต้นถูก merge → ข้ามไป
    contours = [
        c for c in contours
        if MIN_PLANT_AREA <= cv2.contourArea(c) <= max_area
    ]

    # กรอง Shape: ต้นกรีนโอ๊คต้องมีรูปร่างก้อนกลม ไม่ยาวเรียว
    def is_plant_shape(c) -> bool:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw == 0 or ch == 0:
            return False
        ratio = max(cw, ch) / min(cw, ch)
        if ratio > 3.5:
            return False  # รูปร่างยาวเกินไป ไม่ใช่ต้นผักกาด
        # density: พื้นที่ contour / พื้นที่ bounding box ต้องไม่ต่ำกว่า 20%
        density = cv2.contourArea(c) / (cw * ch)
        if density < 0.20:
            return False  # บางเกินไป ไม่ใช่ก้อนใบ
        return True

    contours = [c for c in contours if is_plant_shape(c)]

    # เรียงจากก้อนใหญ่ไปเล็ก และจำกัดจำนวนสูงสุด
    contours.sort(key=cv2.contourArea, reverse=True)
    contours = contours[:MAX_CROPS_PER_PHOTO]

    logger.info(f"🌿 พบ contour ที่ผ่านเกณฑ์ {len(contours)} ก้อน (ก่อน NMS)")

    # ---- ขั้นตอนที่ 4: สร้าง bbox ทุกต้น ----
    raw_crops:  List[np.ndarray] = []
    raw_bboxes: List[BBox]       = []

    for idx, c in enumerate(contours):
        x, y, cw, ch = cv2.boundingRect(c)

        # ขยายกรอบออก PADDING_RATIO % รอบต้น เพื่อไม่ให้ตัดขอบใบ
        pad = int(max(cw, ch) * PADDING_RATIO)
        x0 = max(0, x - pad)
        y0 = max(0, y - pad)
        x1 = min(w, x + cw + pad)
        y1 = min(h, y + ch + pad)

        crop_view = image_bgr[y0:y1, x0:x1]
        if crop_view.size == 0:
            logger.debug(f"  ต้นที่ {idx+1}: crop ว่างเปล่า ข้ามไป")
            continue

        # Resize → 96×96 และแปลงเป็น RGB สำหรับ Edge Impulse
        crop_resized = cv2.resize(
            crop_view,
            (CROP_SIZE, CROP_SIZE),
            interpolation=cv2.INTER_AREA,  # INTER_AREA ดีที่สุดสำหรับ downscale
        )
        crop_rgb = cv2.cvtColor(crop_resized, cv2.COLOR_BGR2RGB)

        raw_crops.append(crop_rgb)
        raw_bboxes.append((x0, y0, x1, y1))
        logger.debug(
            f"  ต้นที่ {idx+1}: bbox=({x0},{y0},{x1},{y1}) "
            f"area={cv2.contourArea(c):.0f}px²"
        )

    # ---- ขั้นตอนที่ 5: NMS — ลบกรอบที่ซ้อนกัน (ตรวจต้นซ้ำ) ----
    keep = _nms_bboxes(raw_bboxes, NMS_IOU_THRESHOLD)
    crops  = [raw_crops[i]  for i in keep]
    bboxes = [raw_bboxes[i] for i in keep]

    logger.info(
        f"✅ หลัง NMS เหลือ {len(bboxes)} ต้น "
        f"(ตัดทิ้ง {len(raw_bboxes) - len(bboxes)} กรอบซ้ำ)"
    )

    return crops, bboxes


# -------------------------------------------------------
# Fixed Zone Crop — ครอปตามโซนที่ผู้ใช้กำหนดตายตัว
# -------------------------------------------------------

def find_fixed_zone_crops(
    image_bgr: np.ndarray,
    zones: list,
) -> Tuple[List[np.ndarray], List[BBox]]:
    """
    Crop ภาพตามโซนพิกัดคงที่ที่ผู้ใช้กำหนด (ไม่ใช้ HSV detection)

    เหมาะสำหรับกล้องที่ติดตั้งตายตัว และรู้จำนวน+ตำแหน่งต้นแน่นอน
    ไม่มีปัญหา merge ต้นหรือ detect ผิดตำแหน่ง

    Args:
        image_bgr: ภาพต้นฉบับ BGR จาก ESP32-CAM
        zones: รายการโซนจาก zones.load_zones()
                แต่ละโซน: {"id": N, "x": 0.0–1.0, "y": 0.0–1.0,
                            "w": 0.0–1.0, "h": 0.0–1.0}
                พิกัดเป็น fraction ของขนาดภาพ

    Returns:
        crops:  รายการภาพ RGB ขนาด 96×96 สำหรับส่งให้ Edge Impulse
        bboxes: รายการ (x0, y0, x1, y1) เป็น pixel coordinates
    """
    h, w = image_bgr.shape[:2]
    crops:  List[np.ndarray] = []
    bboxes: List[BBox]       = []

    for zone in zones:
        # แปลง fraction → pixel (clamp ให้อยู่ในภาพ)
        x0 = max(0, int(zone["x"] * w))
        y0 = max(0, int(zone["y"] * h))
        x1 = min(w, int((zone["x"] + zone["w"]) * w))
        y1 = min(h, int((zone["y"] + zone["h"]) * h))

        if x1 <= x0 or y1 <= y0:
            logger.warning(f"โซน id={zone.get('id')} มีขนาดเป็นศูนย์ ข้ามไป")
            continue

        # Crop → Resize → RGB
        crop_view = image_bgr[y0:y1, x0:x1]
        crop_resized = cv2.resize(
            crop_view,
            (CROP_SIZE, CROP_SIZE),
            interpolation=cv2.INTER_AREA,
        )
        crop_rgb = cv2.cvtColor(crop_resized, cv2.COLOR_BGR2RGB)

        crops.append(crop_rgb)
        bboxes.append((x0, y0, x1, y1))
        logger.debug(
            f"โซน id={zone.get('id')}: "
            f"bbox=({x0},{y0},{x1},{y1}) "
            f"size={x1-x0}×{y1-y0}px"
        )

    logger.info(f"✅ Fixed Zone: crop {len(crops)} ต้น จาก {len(zones)} โซน")
    return crops, bboxes


# -------------------------------------------------------
# ส่วนสร้าง Result Image
# -------------------------------------------------------

def _draw_header(canvas: np.ndarray, healthy: int, unhealthy: int, total: int) -> np.ndarray:
    """
    สร้าง header แถบด้านบนแสดงข้อมูลสรุป
    ออกแบบให้เป็น header สีเข้ม กว้างเท่ากับภาพ

    Args:
        canvas: ภาพต้นฉบับ (ใช้เพื่อดึงความกว้าง)
        healthy: จำนวนต้นแข็งแรง
        unhealthy: จำนวนต้นผิดปกติ
        total: จำนวนต้นทั้งหมด

    Returns:
        header: numpy array ขนาด 65px x กว้างภาพ
    """
    img_w = canvas.shape[1]
    header = np.zeros((65, img_w, 3), dtype=np.uint8)
    header[:] = (25, 25, 25)  # พื้นหลังเกือบดำ

    # ชื่อระบบ
    cv2.putText(
        header, "SmartFarm AI",
        (12, 22), cv2.FONT_HERSHEY_SIMPLEX,
        0.70, (0, 215, 90), 2, cv2.LINE_AA,
    )

    # วันที่และเวลา
    now_str = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    cv2.putText(
        header, now_str,
        (12, 48), cv2.FONT_HERSHEY_SIMPLEX,
        0.45, (160, 160, 160), 1, cv2.LINE_AA,
    )

    # สรุปผลทางขวา
    summary = f"Healthy: {healthy}   UnHealthy: {unhealthy}   Total: {total}"
    (sw, _), _ = cv2.getTextSize(summary, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
    cv2.putText(
        header, summary,
        (img_w - sw - 12, 38),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48, (200, 200, 200), 1, cv2.LINE_AA,
    )

    return header


def draw_result_image(
    image_bgr: np.ndarray,
    bboxes: List[BBox],
    results: List[Optional[Dict[str, Any]]],
) -> np.ndarray:
    """
    วาดกรอบผลการตรวจและสร้างภาพผลลัพธ์พร้อม header

    - Healthy → กรอบสีเขียว (0, 200, 0)
    - UnHealthy → กรอบสีแดง (0, 0, 220)
    แต่ละต้นแสดง: Plant #N, Healthy/UnHealthy, Confidence%
    ด้านบนแสดง: SmartFarm AI, วันที่-เวลา, สรุปผล

    Args:
        image_bgr: ภาพต้นฉบับ BGR
        bboxes: รายการ (x0, y0, x1, y1) ของแต่ละต้น
        results: รายการผลการตรวจ {"label": ..., "conf": ...}

    Returns:
        ภาพผลลัพธ์ BGR พร้อม header และกรอบ
    """
    # นับผล
    healthy_count   = sum(1 for r in results if r and r.get("label") == "Healthy")
    unhealthy_count = sum(1 for r in results if r and r.get("label") == "UnHealthy")
    total = healthy_count + unhealthy_count

    # Copy ภาพก่อนวาดเพื่อไม่แก้ original
    result_img = image_bgr.copy()

    # ---- วาดกรอบแต่ละต้น ----
    for i, (bbox, res) in enumerate(zip(bboxes, results)):
        if res is None:
            continue  # ต้นที่ยังไม่มีผล

        x0, y0, x1, y1 = bbox
        label: str   = res.get("label", "Unknown")
        conf: float  = float(res.get("conf", 0.0))

        # กำหนดสีตามผล
        color     = (0, 200, 0) if label == "Healthy" else (0, 0, 220)
        thickness = 2

        # วาดกรอบสี่เหลี่ยม
        cv2.rectangle(result_img, (x0, y0), (x1, y1), color, thickness)

        # ---- Label text ----
        label_text = f"Plant #{i+1}  {label}  {conf:.1f}%"
        font_scale = 0.50
        font_thick = 1
        (tw, th), baseline = cv2.getTextSize(
            label_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thick
        )

        # ตำแหน่งข้อความเหนือกรอบ (ถ้าชิดขอบบนให้ย้ายลง)
        text_y = y0 - 8 if y0 - 8 > th + 4 else y1 + th + 8

        # พื้นหลังข้อความ (กล่องสี)
        cv2.rectangle(
            result_img,
            (x0, text_y - th - 4),
            (x0 + tw + 8, text_y + baseline),
            color,
            -1,  # filled
        )

        # ข้อความสีขาว
        cv2.putText(
            result_img,
            label_text,
            (x0 + 4, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (255, 255, 255),
            font_thick,
            cv2.LINE_AA,
        )

    # ---- สร้าง header แถบด้านบน ----
    header = _draw_header(result_img, healthy_count, unhealthy_count, total)

    # รวม header + ภาพ (vstack ต้องมี shape ที่ตรงกันในมิติที่ 1)
    result_with_header = np.vstack([header, result_img])
    return result_with_header


def save_result_image(
    image_bgr: np.ndarray,
    bboxes: List[BBox],
    results: List[Optional[Dict[str, Any]]],
) -> str:
    """
    สร้างภาพผลลัพธ์และบันทึกเป็น photos/result.jpg

    Args:
        image_bgr: ภาพต้นฉบับ BGR
        bboxes: ตำแหน่งกรอบแต่ละต้น
        results: ผลการตรวจจาก Edge Impulse

    Returns:
        path ที่บันทึกไว้ เช่น "photos/result.jpg"
    """
    logger.info("🖼  กำลังสร้าง Result.jpg ...")
    result_img = draw_result_image(image_bgr, bboxes, results)
    result_path = os.path.join(UPLOAD_DIR, RESULT_PHOTO_FILENAME)

    success = cv2.imwrite(result_path, result_img)
    if not success:
        logger.error(f"บันทึก result image ไม่สำเร็จ: {result_path}")
    else:
        logger.info(f"✔  บันทึก result image สำเร็จ: {result_path}")

    return result_path
