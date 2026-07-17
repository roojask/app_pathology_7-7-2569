import re

def normalize_text(text):
    t = text.lower()
    t = t.replace("comma", ",")
    
    # 1. แปลงคำศัพท์เชื่อม
    t = re.sub(r"\bby\b", "x", t)
    t = re.sub(r"\btimes\b", "x", t)
    
    # 2. ระบบแก้คำผิดอัจฉริยะ (Smart Self-Correction)
    t = re.sub(r"([\d.]+\s*x\s*[\d.]+(?:\s*x\s*[\d.]+)?)(?:[\s\.,]*(?:cm|centimeters|mm))?[\s\.,]*(?:sorry|wait|weight|correction|actually|no wait)+[\s\.,]*(?:measuring|size is|it is|actually)?\s*", "", t)
    
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
    
    # Synonyms (Medical Terms)
    t = t.replace("papilla", "nipple")
    t = t.replace("tissue", "specimen")
    t = t.replace("cutaneous", "skin")
    t = t.replace("lesion", "mass")
    t = t.replace("tumor", "mass")
    t = t.replace("averted", "everted")
    
    return t
