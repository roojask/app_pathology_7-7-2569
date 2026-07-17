# ใช้ Python 3.11 ที่มีขนาดเล็ก
FROM python:3.11-slim

# อัปเดตระบบและติดตั้ง FFmpeg (จำเป็นมากสำหรับ Whisper)
RUN apt-get update && \
	apt-get install -y ffmpeg && \
	apt-get clean && \
	rm -rf /var/lib/apt/lists/*

# สร้างผู้ใช้ใหม่เพื่อหลีกเลี่ยงปัญหาเรื่องสิทธิ์ของ Hugging Face Spaces (UID 1000)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user
ENV PATH=/home/user/.local/bin:$PATH

# ตั้งค่าโฟลเดอร์ทำงานในระบบ Cloud
WORKDIR $HOME/app

# ติดตั้ง PyTorch รุ่น CPU-only ล่วงหน้า เพื่อป้องกันการโหลดรุ่น GPU (CUDA) ขนาด 2GB+ ซึ่งกินแรมและทำให้ Docker แครช
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# ก๊อปปี้ไฟล์ทั้งหมดในโปรเจกต์เรา ขึ้นไปบน Cloud และกำหนดสิทธิ์ให้ผู้ใช้
COPY --chown=user . $HOME/app

# ติดตั้งไลบรารีจาก requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# โหลดสมองกล NLP (spaCy) ล่วงหน้า
RUN python -m spacy download en_core_web_sm

# เปิด Port 7860
EXPOSE 7860

# คำสั่งรันแอปพลิเคชัน
CMD ["python", "app.py"]