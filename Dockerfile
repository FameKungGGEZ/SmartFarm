FROM python:3.11-slim

WORKDIR /app

# ติดตั้ง system libraries ที่ OpenCV ต้องการ
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      libgl1 \
      libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# ติดตั้ง Python dependencies ก่อน (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy โค้ดทั้งหมด
COPY . .

# สร้างโฟลเดอร์เก็บภาพ
RUN mkdir -p photos

EXPOSE 5000

CMD ["gunicorn", "app:app", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "1", \
     "--threads", "4", \
     "--timeout", "120"]
