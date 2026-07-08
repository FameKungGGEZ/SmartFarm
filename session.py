# =====================================================================
# session.py — ระบบ Session Manager แบบ Thread-Safe
# =====================================================================
# รับผิดชอบการจัดการ "การตรวจสอบ 1 รอบ" (1 ภาพจาก ESP32-CAM)
# แต่ละ session เก็บ: ภาพ crop, bboxes, ผลวิเคราะห์, และเวลาสร้าง
#
# คุณสมบัติ:
#   - Thread-Safe ใช้ RLock รองรับ nested locking
#   - Auto Cleanup: background thread ลบ session หมดอายุอัตโนมัติ
#   - Timeout: session ไม่ถูกแตะนาน > SESSION_TIMEOUT วิ → ลบอัตโนมัติ
#   - รองรับหลาย Session พร้อมกัน (หลาย ESP32 หรือ retry กลางทาง)
#   - ป้องกัน Memory Leak: ปล่อยอ้างอิง numpy array ตอนลบ
# =====================================================================

import time
import threading
import logging
import numpy as np
from typing import Optional, Dict, List, Any, Tuple

from config import SESSION_TIMEOUT, CLEANUP_INTERVAL

# Logger เฉพาะโมดูลนี้
logger = logging.getLogger(__name__)

# ประเภทย่อสำหรับผลการตรวจ
ResultDict = Optional[Dict[str, Any]]
BBox = Tuple[int, int, int, int]


# -------------------------------------------------------
# SessionData — ข้อมูลของ 1 session
# -------------------------------------------------------

class SessionData:
    """
    เก็บข้อมูลทั้งหมดสำหรับการสแกน 1 ครั้ง

    Attributes:
        session_id: ID เอกลักษณ์ของ session (millisecond timestamp)
        crops: รายการภาพ crop RGB 96x96 ส่งให้ Edge Impulse
        bboxes: ตำแหน่งกรอบในภาพต้นฉบับ
        image_bgr: ภาพต้นฉบับ (เก็บไว้วาด result.jpg)
        photo_url: URL ภาพที่ ESP32 อัพโหลดมา
        results: ผลการตรวจ (None = ยังไม่ได้ตรวจ)
        created_at: เวลาสร้าง session
        last_accessed: เวลาเข้าถึงล่าสุด (ใช้คำนวณ timeout)
    """

    __slots__ = (
        "session_id",
        "crops",
        "bboxes",
        "image_bgr",
        "photo_url",
        "results",
        "created_at",
        "last_accessed",
    )

    def __init__(
        self,
        session_id: str,
        crops: List[np.ndarray],
        bboxes: List[BBox],
        image_bgr: np.ndarray,
        photo_url: str,
    ) -> None:
        self.session_id: str = session_id
        self.crops: List[np.ndarray] = crops
        self.bboxes: List[BBox] = bboxes
        self.image_bgr: Optional[np.ndarray] = image_bgr
        self.photo_url: str = photo_url
        self.results: List[ResultDict] = [None] * len(crops)
        self.created_at: float = time.time()
        self.last_accessed: float = time.time()

    # ---- Properties ----

    @property
    def total_plants(self) -> int:
        """จำนวนต้นที่พบในภาพ"""
        return len(self.crops)

    @property
    def completed_count(self) -> int:
        """จำนวนต้นที่ตรวจเสร็จแล้ว"""
        return sum(1 for r in self.results if r is not None)

    @property
    def is_complete(self) -> bool:
        """ตรวจทุกต้นเสร็จแล้วหรือยัง"""
        return self.completed_count == self.total_plants

    # ---- Methods ----

    def touch(self) -> None:
        """อัพเดตเวลาเข้าถึงล่าสุด (เพื่อป้องกัน timeout กลางทาง)"""
        self.last_accessed = time.time()

    def is_expired(self, timeout: float = SESSION_TIMEOUT) -> bool:
        """
        ตรวจสอบว่า session หมดอายุหรือยัง

        Args:
            timeout: ระยะเวลา (วินาที) หลังจากเข้าถึงล่าสุด

        Returns:
            True ถ้าไม่ถูกแตะนานเกิน timeout
        """
        return (time.time() - self.last_accessed) > timeout

    def set_result(self, index: int, label: str, conf: str) -> bool:
        """
        บันทึกผลการตรวจของต้นที่ index

        Args:
            index: ลำดับต้น (0-based)
            label: "Healthy" หรือ "UnHealthy"
            conf: ค่า confidence เป็น string เช่น "98.52"

        Returns:
            True ถ้า index ถูกต้อง
        """
        if index < 0 or index >= len(self.results):
            return False
        self.results[index] = {"label": label, "conf": conf}
        return True

    def get_summary(self) -> Dict[str, int]:
        """
        สรุปผลการตรวจทั้งหมด

        Returns:
            {"healthy": int, "unhealthy": int, "total": int}
        """
        healthy = sum(1 for r in self.results if r and r.get("label") == "Healthy")
        unhealthy = sum(1 for r in self.results if r and r.get("label") == "UnHealthy")
        return {
            "healthy": healthy,
            "unhealthy": unhealthy,
            "total": healthy + unhealthy,
        }

    def free_memory(self) -> None:
        """
        ปล่อยอ้างอิง numpy array เพื่อให้ GC เก็บคืน RAM
        เรียกก่อนลบ session ออกจาก dict
        """
        self.crops.clear()
        self.image_bgr = None


# -------------------------------------------------------
# SessionManager — จัดการ Session ทั้งหมด
# -------------------------------------------------------

class SessionManager:
    """
    จัดการ Session ทั้งหมดแบบ Thread-Safe

    Features:
        - RLock รองรับ nested locking ภายในโมดูลเดียวกัน
        - Background daemon thread ทำ cleanup ทุก CLEANUP_INTERVAL วินาที
        - ลบ session ที่ไม่ถูกแตะนาน SESSION_TIMEOUT วินาที
        - ปล่อย numpy memory ทันทีเมื่อลบ session
    """

    def __init__(
        self,
        timeout: float = SESSION_TIMEOUT,
        cleanup_interval: float = CLEANUP_INTERVAL,
    ) -> None:
        self._sessions: Dict[str, SessionData] = {}
        self._lock = threading.RLock()  # RLock รองรับการ acquire ซ้ำจาก thread เดิม
        self._timeout = timeout
        self._cleanup_interval = cleanup_interval

        # เริ่ม background cleanup thread
        self._stop_event = threading.Event()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,             # daemon: ตายพร้อม main process
            name="SmartFarm-SessionCleanup",
        )
        self._cleanup_thread.start()
        logger.info(
            f"SessionManager พร้อมใช้งาน "
            f"(timeout={timeout}s, cleanup={cleanup_interval}s)"
        )

    # ---- CRUD operations ----

    def create(
        self,
        session_id: str,
        crops: List[np.ndarray],
        bboxes: List[BBox],
        image_bgr: np.ndarray,
        photo_url: str,
    ) -> SessionData:
        """
        สร้าง session ใหม่และเก็บไว้ใน memory

        Args:
            session_id: ID เอกลักษณ์ (ส่งกลับให้ ESP32)
            crops: รายการ crop RGB 96x96
            bboxes: ตำแหน่งกรอบในภาพ
            image_bgr: ภาพต้นฉบับ BGR
            photo_url: URL ภาพจาก ESP32

        Returns:
            SessionData ที่สร้างขึ้น
        """
        session = SessionData(session_id, crops, bboxes, image_bgr, photo_url)
        with self._lock:
            self._sessions[session_id] = session
        logger.debug(
            f"สร้าง session [{session_id}] "
            f"จำนวน {len(crops)} ต้น"
        )
        return session

    def get(self, session_id: str) -> Optional[SessionData]:
        """
        ดึง session ตาม ID (อัพเดต last_accessed อัตโนมัติ)

        Args:
            session_id: ID ที่ต้องการ

        Returns:
            SessionData หรือ None ถ้าไม่พบ / หมดอายุแล้ว
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.touch()
            return session

    def delete(self, session_id: str) -> bool:
        """
        ลบ session และปล่อย memory ทันที

        Args:
            session_id: ID ที่ต้องการลบ

        Returns:
            True ถ้าพบและลบสำเร็จ
        """
        with self._lock:
            session = self._sessions.pop(session_id, None)

        if session:
            session.free_memory()
            logger.debug(f"ลบ session [{session_id}]")
            return True
        return False

    def cleanup_expired(self) -> int:
        """
        ลบ session ที่หมดอายุทั้งหมด

        Returns:
            จำนวน session ที่ถูกลบ
        """
        with self._lock:
            expired_ids = [
                k for k, v in self._sessions.items()
                if v.is_expired(self._timeout)
            ]
            expired_sessions = [self._sessions.pop(k) for k in expired_ids]

        # ปล่อย memory นอก lock เพื่อไม่บล็อก thread อื่น
        for session in expired_sessions:
            session.free_memory()

        if expired_ids:
            logger.info(
                f"Session Cleanup: ลบ {len(expired_ids)} session ที่หมดอายุ "
                f"→ [{', '.join(expired_ids)}]"
            )
        return len(expired_ids)

    def _cleanup_loop(self) -> None:
        """Loop ทำ cleanup อัตโนมัติในพื้นหลัง"""
        while not self._stop_event.wait(self._cleanup_interval):
            try:
                self.cleanup_expired()
            except Exception as e:
                logger.error(f"Session cleanup error: {e}")

    def stop(self) -> None:
        """หยุด cleanup thread (ใช้ตอน shutdown server)"""
        self._stop_event.set()

    # ---- Properties / Stats ----

    @property
    def active_count(self) -> int:
        """จำนวน session ที่ active อยู่ในขณะนี้"""
        with self._lock:
            return len(self._sessions)

    def get_all_ids(self) -> List[str]:
        """คืนรายการ ID session ทั้งหมดที่ active"""
        with self._lock:
            return list(self._sessions.keys())
