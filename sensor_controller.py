# =====================================================================
# sensor_controller.py — จัดการข้อมูลเซ็นเซอร์และการควบคุมระบบ
# =====================================================================
# แทนที่ Blynk ด้วยการจัดการข้อมูลเซ็นเซอร์ภายใน server
# รองรับ real-time update ผ่าน Server-Sent Events (SSE)
# =====================================================================

import time
import threading
from typing import Dict, Optional, List, Callable
from datetime import datetime

class SensorData:
    """เก็บข้อมูลเซ็นเซอร์ล่าสุด"""
    def __init__(self):
        # ข้อมูลเซ็นเซอร์
        self.water_temp: float = 0.0
        self.air_temp: float = 0.0
        self.humidity: float = 0.0
        self.light_value: int = 0

        # สถานะการควบคุม
        self.auto_mode: bool = True  # เริ่มต้นเป็น True (Auto Mode)
        self.spray: bool = True
        self.fan: bool = True
        self.shade_closed: bool = False
        self.motor_state: str = "out"  # "in" หรือ "out"
        self.motor_working: bool = False

        # สถานะการรอยืนยันค่า (pending states)
        self.fan_pending: bool = False
        self.spray_pending: bool = False
        self.shade_pending: bool = False

        # Flag สำหรับการควบคุมจาก Web (ต้องส่งไปยัง ESP32)
        self.web_control_changed: bool = False
        self.motor_toggle_requested: bool = False

        # เวลาอัพเดทล่าสุด
        self.last_update: float = time.time()

        # Lock สำหรับ thread-safe
        self._lock = threading.Lock()

    def update(self, data: dict) -> None:
        """อัพเดทข้อมูลเซ็นเซอร์"""
        with self._lock:
            if 'water_temp' in data:
                val = data['water_temp']
                self.water_temp = float(val) if val is not None else 0.0
            if 'air_temp' in data:
                val = data['air_temp']
                self.air_temp = float(val) if val is not None else 0.0
            if 'humidity' in data:
                val = data['humidity']
                self.humidity = float(val) if val is not None else 0.0
            if 'light_value' in data:
                val = data['light_value']
                self.light_value = int(val) if val is not None else 0
            if 'auto_mode' in data:
                self.auto_mode = bool(data['auto_mode'])
            if 'spray' in data:
                self.spray = bool(data['spray'])
            if 'fan' in data:
                self.fan = bool(data['fan'])
            if 'shade_closed' in data:
                self.shade_closed = bool(data['shade_closed'])
            if 'motor_state' in data:
                self.motor_state = str(data['motor_state'])
            if 'motor_working' in data:
                self.motor_working = bool(data['motor_working'])
            if 'fan_pending' in data:
                self.fan_pending = bool(data['fan_pending'])
            if 'spray_pending' in data:
                self.spray_pending = bool(data['spray_pending'])
            if 'shade_pending' in data:
                self.shade_pending = bool(data['shade_pending'])

            self.last_update = time.time()

    def get_all(self) -> dict:
        """ดึงข้อมูลทั้งหมดแบบ thread-safe"""
        with self._lock:
            return {
                'water_temp': self.water_temp,
                'air_temp': self.air_temp,
                'humidity': self.humidity,
                'light_value': self.light_value,
                'auto_mode': self.auto_mode,
                'spray': self.spray,
                'fan': self.fan,
                'shade_closed': self.shade_closed,
                'motor_state': self.motor_state,
                'motor_working': self.motor_working,
                'fan_pending': self.fan_pending,
                'spray_pending': self.spray_pending,
                'shade_pending': self.shade_pending,
                'motor_toggle': self.motor_toggle_requested,
                'last_update': self.last_update,
                'last_update_time': datetime.fromtimestamp(self.last_update).strftime('%Y-%m-%d %H:%M:%S')
            }

    def get_controls_for_esp32(self) -> dict:
        """ดึงข้อมูลควบคุมที่จะส่งกลับไปยัง ESP32"""
        with self._lock:
            controls = {
                'auto_mode': self.auto_mode,
                'spray': self.spray,
                'fan': self.fan,
                'motor_toggle': self.motor_toggle_requested
            }
            # Reset motor toggle flag หลังส่งไปแล้ว
            self.motor_toggle_requested = False
            return controls


class SensorController:
    """ควบคุมและจัดการข้อมูลเซ็นเซอร์"""

    def __init__(self):
        self.sensor_data = SensorData()
        self._subscribers: List[Callable] = []
        self._lock = threading.Lock()

    def update_sensor_data(self, data: dict) -> None:
        """
        อัพเดทข้อมูลเซ็นเซอร์และแจ้งเตือน subscribers

        Args:
            data: dict ข้อมูลเซ็นเซอร์
        """
        self.sensor_data.update(data)
        self._notify_subscribers()

    def get_sensor_data(self) -> dict:
        """ดึงข้อมูลเซ็นเซอร์ล่าสุด"""
        return self.sensor_data.get_all()

    def set_control(self, control_type: str, value: bool) -> dict:
        """
        ตั้งค่าการควบคุมอุปกรณ์

        Args:
            control_type: "spray", "fan", "auto_mode", "motor_toggle"
            value: True/False

        Returns:
            dict สถานะปัจจุบัน
        """
        with self._lock:
            if control_type == 'spray':
                self.sensor_data.spray = value
                self.sensor_data.web_control_changed = True
            elif control_type == 'fan':
                self.sensor_data.fan = value
                self.sensor_data.web_control_changed = True
            elif control_type == 'auto_mode':
                self.sensor_data.auto_mode = value
                # Reset pending states เมื่อสลับโหมด
                self.sensor_data.fan_pending = False
                self.sensor_data.spray_pending = False
                self.sensor_data.shade_pending = False
                self.sensor_data.web_control_changed = True
            elif control_type == 'motor_toggle':
                # Toggle motor state
                if not self.sensor_data.motor_working:
                    self.sensor_data.motor_toggle_requested = True
                    self.sensor_data.web_control_changed = True

            self.sensor_data.last_update = time.time()

        self._notify_subscribers()
        return self.sensor_data.get_all()

    def subscribe(self, callback: Callable) -> None:
        """เพิ่ม subscriber สำหรับรับ notification เมื่อมีการเปลี่ยนแปลง"""
        with self._lock:
            self._subscribers.append(callback)

    def _notify_subscribers(self) -> None:
        """แจ้งเตือน subscribers ทั้งหมด"""
        with self._lock:
            data = self.sensor_data.get_all()
            for callback in self._subscribers:
                try:
                    callback(data)
                except Exception:
                    pass  # Ignore errors in callbacks


# Singleton instance
_controller: Optional[SensorController] = None

def get_controller() -> SensorController:
    """ดึง SensorController instance (Singleton)"""
    global _controller
    if _controller is None:
        _controller = SensorController()
    return _controller
