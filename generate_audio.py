from gtts import gTTS
import os

# 1. ใส่สคริปต์ข้อความที่ต้องการแปลงเป็นเสียง
text = """
Specimen S-25-9999. Received in formalin is a left modified radical mastectomy specimen.
The overall specimen measuring 18 by 12 by 6 cm, with axillary content measuring 8 by 5 by 3 cm. The skin ellipse is 14 by 6 cm and shows an ulceration 2 by 1 cm. The nipple shows inverted and shows ulceration.
There is an infiltrative firm yellow white mass measuring 3 by 2 by 2 centimeters... wait, sorry, measuring 4.5 by 3.5 by 2.5 centimeters.
in the upper outer quadrant. Tumor is located It is 1.5 cm from deep margin, 2.0 cm from superior margin, 3.5 cm from inferior margin, 1.0 cm from medial margin, 4.0 cm from lateral margin, and 0.5 cm from skin.
The remaining of breast tissue is unremarkable. I found exactly 16 lymph nodes. The size ranges from 0.3 up to 2.8 cm in diameter.
Representative sections are submitted as: A1 equals nipple, A2 to A4 equals mass, A5 equals deep resected margin, A6 equals sampling upper outer quadrant, A7 to A10 equals axillary lymph nodes.
"""

# 2. ตั้งค่าและแปลงข้อความเป็นเสียง (lang='en' คือภาษาอังกฤษ)
print("⏳ กำลังสร้างไฟล์เสียง กรุณารอสักครู่...")
tts = gTTS(text=text, lang='en', slow=False)

# 3. บันทึกไฟล์
output_filename = "stress_test_dictation.mp3"
tts.save(output_filename)

print(f"✅ สร้างไฟล์เสียงสำเร็จ! บันทึกชื่อ: {output_filename}")

# (ทางเลือกเสริม) สั่งให้ระบบเปิดไฟล์เสียงเล่นทันทีที่สร้างเสร็จ (สำหรับ Windows)
# os.system(f"start {output_filename}")
# สำหรับ Mac ให้เปลี่ยนเป็น: os.system(f"afplay {output_filename}")