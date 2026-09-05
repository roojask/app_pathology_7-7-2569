import re

def normalize_text(text):
    t = text.lower()
    t = t.replace("comma", ",")
    
    # 1. แปลงคำศัพท์เชื่อมและซ่อมตัวเลขขนาดมิติติดกัน (Dimension Repair)
    t = re.sub(r"\bby\b", "x", t)
    t = re.sub(r"\btimes\b", "x", t)
    t = re.sub(r"(\d+\.\d{1,2})\.?:?(\d+\.\d{1,2})\.?:?\s*(\d+\.\d{1,2})", r"\1 x \2 x \3", t)
    
    # 2. ระบบแก้คำผิดอัจฉริยะ (Smart Self-Correction)
    t = re.sub(r"([\d.]+\s*x\s*[\d.]+(?:\s*x\s*[\d.]+)?)(?:[\s\.,]*(?:cm|centimeters|mm))?[\s\.,]*(?:sorry|wait|weight|correction|actually|no wait|แก้เป็น|ขอแก้|ไม่ใช่|เปลี่ยนเป็น)+[\s\.,]*(?:measuring|size is|it is|actually)?\s*", "", t)
    
    # 2.5. แปลงคำอ่านภาษาไทย-อังกฤษ (Thai-English Phonetic Normalization)
    t = t.replace("ข้างขวา", " right ").replace("เต้าขวา", " right ").replace("ขวา", " right ")
    t = t.replace("ข้างซ้าย", " left ").replace("เต้าซ้าย", " left ").replace("ซ้าย", " left ")
    t = t.replace("ตัดเต้านม", " mastectomy ").replace("มาสเทค", " mastectomy ")
    t = t.replace("มอดิฟายด์", "modified").replace("มอดิฟาย", "modified")
    t = t.replace("แรดิคัล", "radical").replace("เรดิคัล", "radical")
    t = t.replace("ซิมเปิล", "simple")
    t = t.replace("ก้อนเนื้อ", " mass ").replace("ก้อน", " mass ").replace("แมส", " mass ")
    t = t.replace("ต่อมน้ำเหลือง", " lymph nodes ").replace("รักแร้", " axillary ")
    t = t.replace("ขอบตัด", " margin ").replace("ขอบลึก", " deep margin ")
    t = t.replace("ขอบบน", " superior margin ").replace("ขอบล่าง", " inferior margin ")
    t = t.replace("ขอบใน", " medial margin ").replace("ขอบนอก", " lateral margin ")
    t = t.replace("บนนอก", " upper outer ").replace("บนใน", " upper inner ")
    t = t.replace("ล่างนอก", " lower outer ").replace("ล่างใน", " lower inner ")
    t = t.replace("กึ่งกลาง", " central ")
    t = t.replace("ขนาด", " measuring ")
    t = t.replace("คูณ", " x ")
    
    # 3. แปลงหน่วยและคำพ้องความหมาย (Synonyms)
    t = t.replace("centimeters", "cm").replace("centimeter", "cm")
    t = t.replace("millimeter", "mm").replace("millimeters", "mm")
    
    # แก้บั๊ก Whisper ถอดเสียง equals เป็น =s
    t = t.replace("=s", "=").replace("equals", "=").replace("equal", "=")
    
    t = re.sub(r"\bx\s+(?:cm|centimeters?)\s+from", "8 cm from", t)
    t = t.replace("mast", "mass") 
    t = t.replace("medium margin", "medial margin")
    t = t.replace("massectomy", "mastectomy")
    t = t.replace("slit-like", "slit like")
    t = t.replace("the resected", "deep resected")
    
    # Synonyms & Phonetic Repair (Medical Terms)
    t = re.sub(r"\bs24[\s\-\.]*(\d{3,4})\b", r"s-24-\1", t)
    t = re.sub(r"(\d+\.\d)\s*s\s*(\d+\.\d)\s*s\s*(\d+\.\d)", r"\1 x \2 x \3", t)
    t = t.replace("modify radical", "modified radical").replace("left-modified", "left modified").replace("right-modified", "right modified")
    t = t.replace("papilla", "nipple")
    t = t.replace("tissue", "specimen")
    t = t.replace("cutaneous", "skin")
    t = t.replace("lesion", "mass")
    t = t.replace("tumor", "mass")
    t = t.replace("averted", "everted")
    
    return t
