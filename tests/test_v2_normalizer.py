import re

def normalize_text_v2(text):
    t = text.lower()
    t = t.replace("comma", ",")
    
    # 1. Dimension Repair
    t = re.sub(r"\bby\b", "x", t)
    t = re.sub(r"\btimes\b", "x", t)
    t = re.sub(r"(\d+\.\d{1,2})\.?:?(\d+\.\d{1,2})\.?:?\s*(\d+\.\d{1,2})", r"\1 x \2 x \3", t)
    
    # 2. Smart Self-Correction:
    # Rule 2.1: 2D/3D Dimension Self-Correction:
    # Requires (Dim 1) + (correction signal) + (Dim 2) -> keep only Dim 2!
    dim_pattern = r"(\d+(?:\.\d+)?\s*x\s*\d+(?:\.\d+)?(?:\s*x\s*\d+(?:\.\d+)?)?(?:\s*(?:cm|centimeters|mm))?)"
    signal_2d = r"(?:[\s\.,]*(?:sorry|wait|weight|correction|no wait|แก้เป็น|ขอแก้|ไม่ใช่|เปลี่ยนเป็น)+[\s\.,]*(?:measuring|size is|it is|actually)?\s*)"
    full_2d_corr = rf"{dim_pattern}{signal_2d}{dim_pattern}"
    
    t = re.sub(full_2d_corr, r"\2", t)
    
    # Rule 2.2: 1D Dimension Self-Correction:
    # Requires (Num 1 + unit) + (signal) + (Num 2 + unit) -> keep Num 2 + unit!
    signal_1d = r"(?:sorry|wait|correction|no wait|แก้เป็น|ขอแก้|no)"
    pat_1d = rf"\b(\d+(?:\.\d+)?)\s*(cm|centimeters|mm)\s*(?:{signal_1d})\s+(\d+(?:\.\d+)?)\s*(cm|centimeters|mm)\b"
    t = re.sub(pat_1d, r"\3 \4", t)
    
    return t

test_cases = [
    ("TC-01", "infiltrative mass measuring 2.0 x 3.0 x 1.0 cm sorry 2.5 x 3.5 x 1.5 cm", "infiltrative mass measuring 2.5 x 3.5 x 1.5 cm"),
    ("TC-02", "10 x 5 x 2 cm, weight is 450 grams", "10 x 5 x 2 cm, weight is 450 grams"),
    ("TC-03", "10 x 5 x 2 cm, weight of 450 grams", "10 x 5 x 2 cm, weight of 450 grams"),
    ("TC-04", "10 x 5 x 2 cm, weight: 450 g", "10 x 5 x 2 cm, weight: 450 g"),
    ("TC-05", "10 x 5 x 2 cm, weight 0.45 kg", "10 x 5 x 2 cm, weight 0.45 kg"),
    ("TC-06", "10 x 5 x 2 cm, weight four hundred fifty grams", "10 x 5 x 2 cm, weight four hundred fifty grams"),
    ("TC-07", "10 x 5 x 2 cm. Actually the skin ellipse measures 5 x 2 cm", "10 x 5 x 2 cm. actually the skin ellipse measures 5 x 2 cm"),
    ("TC-08", "5.3 x 2.4 x 2.9 cm weight margin is 3.0 cm", "5.3 x 2.4 x 2.9 cm weight margin is 3.0 cm"),
    ("TC-09", "margin 2 mm no 3 lymph nodes", "margin 2 mm no 3 lymph nodes"),
    ("TC-10", "mass measuring 2 cm no 3 cm", "mass measuring 3 cm"),
    ("TC-11", "mass measuring 2.0 x 3.0 x 1.0 cm weight 2.5 x 3.5 x 1.5 cm", "mass measuring 2.5 x 3.5 x 1.5 cm"),
    ("TC-12", "specimen measuring 10 x 5 x 2 cm, weight 450 grams", "specimen measuring 10 x 5 x 2 cm, weight 450 grams"),
    ("TC-13", "no discrete mass identified", "no discrete mass identified"),
    ("TC-14", "actually there is no mass in the upper outer quadrant", "actually there is no mass in the upper outer quadrant")
]

all_pass = True
for tid, inp, exp in test_cases:
    out = normalize_text_v2(inp).strip()
    out_clean = " ".join(out.split())
    exp_clean = " ".join(exp.lower().split())
    ok = (out_clean == exp_clean)
    if not ok: all_pass = False
    print(f"{tid}: {'PASS' if ok else 'FAIL'} | Got: '{out_clean}' | Expected: '{exp_clean}'")

print("="*60)
print(f"Overall Result: {'14/14 ALL PASS (100.0%)' if all_pass else 'SOME FAILED'}")
