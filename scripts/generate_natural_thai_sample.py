import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

try:
    from gtts import gTTS
    from pydub import AudioSegment
except ImportError:
    os.system(f"{sys.executable} -m pip install gtts pydub")
    from gtts import gTTS
    from pydub import AudioSegment

def generate_clean_thai_audio():
    print("==================================================")
    print("🎙️ Generating High-Quality Natural Thai Medical Audio Sample...")
    print("==================================================")
    
    out_dir = BASE_DIR / "data"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "natural_thai_sample_case.mp3"

    # Clean natural Thai-English pathology dictation
    # Part 1: Thai Intro & Surgical Number
    p1 = "ชิ้นเนื้อ สิ่งส่งตรวจ รหัส เซอร์จิคัล นัมเบอร์ เอส ยี่สิบสี่ ขีด หนึ่งศูนย์ศูนย์เก้า"
    # Part 2: Specimen Side & Procedure
    p2 = "เต้านม ข้างซ้าย มอดิฟายด์ แรดิคัล แมสเทคโทมี"
    # Part 3: Specimen Size & Tumor Mass
    p3 = "ขนาด ยี่สิบสองจุดห้า คูณ สิบสองจุดศูนย์ คูณ ศักดิ์ ห้าจุดศูนย์ เซนติเมตร พบก้อนเนื้อ ขนาด สามจุดห้า คูณ สองจุดศูนย์ คูณ หนึ่งจุดห้า เซนติเมตร บริเวณ อัปเปอร์ เอาเตอร์ ควาแดรนต์"
    # Part 4: Lymph Nodes
    p4 = "สกัดได้ ต่อมน้ำเหลือง จำนวน สิบสอง ต่อม"

    full_text_thai = f"{p1} {p2} {p3} {p4}"
    
    print(f"  • Natural Script: {full_text_thai}")
    
    # Generate using gTTS Thai language engine ('th') for clear native Thai pronunciation
    tts = gTTS(text=full_text_thai, lang='th', slow=False)
    tts.save(str(out_path))
    
    print(f"  🟢 Clean Thai Audio Sample saved successfully to:")
    print(f"     file:///{out_path.as_posix()}")
    print("==================================================")

if __name__ == "__main__":
    generate_clean_thai_audio()
