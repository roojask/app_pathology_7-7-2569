import os
import sys
import json
import re
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.nlp.normalizer import normalize_text
from src.nlp.extractor import extract_data_15_sections

with open(BASE_DIR / 'data' / 'dataset_1000' / 'ground_truth_1000_pure.json', 'r', encoding='utf-8') as f:
    gt_data = json.load(f)

csv_path = BASE_DIR / 'benchmarks' / 'thesis_eval_outputs' / 'benchmark_1000_cases_overnight.csv'
df = pd.read_csv(csv_path)
pw_df = df[df['system'].str.contains('PathoWhisper', case=False, na=False)].copy()

def are_num_equal(a, b):
    if a is None and b is None: return True
    if a is None or b is None: return False
    try: return abs(float(a) - float(b)) < 0.05
    except: return str(a).strip().lower() == str(b).strip().lower()

def are_dims_equal(list_a, list_b):
    if list_a is None and list_b is None: return True
    if not isinstance(list_a, list) or not isinstance(list_b, list): return False
    if len(list_a) != len(list_b): return False
    try: return all(abs(float(a) - float(b)) < 0.05 for a, b in zip(list_a, list_b))
    except: return list_a == list_b

def are_strings_equal(a, b):
    if a is None and b is None: return True
    if a is None or b is None: return False
    s_a = re.sub(r'[\s\-_]+', '', str(a).lower())
    s_b = re.sub(r'[\s\-_]+', '', str(b).lower())
    return s_a == s_b

# Improved extractor function with targeted fixes
def extract_improved(text):
    t = normalize_text(text)
    data = {"_low_confidence": []}

    # 1. Surgical Number (handles S-24-10-27, 24-10-27, S-24-10-62, etc.)
    m = re.search(r"(?:surgical number|specimen|s-)?\s*(?:is\s+)?([sS]?\s*-?\s*\d{2}(?:\s*[-–\s]\s*\d{2,4})+|\b\d{2}-\d{4,}\b|[sS]?\s*-?\s*\d{2}\s*-?\s*\d+)", t, re.IGNORECASE)
    if m:
        raw_s = m.group(1).replace(" ", "").upper()
        # Merge split last 4 digits: e.g. 24-10-27 -> 24-1027, S-24-10-27 -> S-24-1027
        parts = [p for p in re.split(r'[-–]', raw_s) if p]
        if len(parts) == 3 and len(parts[0]) == 2 and len(parts[1]) == 2 and len(parts[2]) == 2:
            raw_s = f"S-{parts[0]}-{parts[1]}{parts[2]}"
        elif len(parts) == 4 and parts[0] == 'S' and len(parts[1]) == 2 and len(parts[2]) == 2 and len(parts[3]) == 2:
            raw_s = f"S-{parts[1]}-{parts[2]}{parts[3]}"
        elif not raw_s.startswith("S-"):
            if raw_s.startswith("S"): raw_s = f"S-{raw_s[1:]}"
            else: raw_s = f"S-{raw_s}"
        if re.match(r"^S-\d{5,}$", raw_s):
            raw_s = f"S-{raw_s[2:4]}-{raw_s[4:]}"
        data["s0_surgical_no"] = raw_s
        t = t.replace(m.group(1), "")

    # 2. Side & Procedure
    right_idx = t.rfind("right")
    left_idx = t.rfind("left")
    if right_idx != -1 or left_idx != -1:
        data["s1_side"] = "right" if right_idx > left_idx else "left"

    if "modified" in t: data["s2_proc"] = "modified"
    elif "simple" in t: data["s2_proc"] = "simple"

    # 3. Specimen Overall Dimensions
    m_specs = list(re.finditer(r"(?:mastectomy|specimen|overall size|specimen size|total specimen|measuring|dimensions are)[\s\S]{0,60}?([\d.]+)\s*(?:cm|mm)?\s*x\s*([\d.]+)\s*(?:cm|mm)?\s*x\s*([\d.]+)", t, re.IGNORECASE))
    if m_specs:
        m = m_specs[0]
        data["s3_dims"] = [m.group(1).rstrip('.'), m.group(2).rstrip('.'), m.group(3).rstrip('.')]
        t = t[:m.start()] + " [SPECIMEN_DIMS] " + t[m.end():]
    else:
        generic_matches = list(re.finditer(r"(?<!-)(?<!\d)([\d.]+)\s*(?:cm|mm)?\s*x\s*([\d.]+)\s*(?:cm|mm)?\s*x\s*([\d.]+)", t, re.IGNORECASE))
        if generic_matches:
            m = generic_matches[0]
            data["s3_dims"] = [m.group(1).rstrip('.'), m.group(2).rstrip('.'), m.group(3).rstrip('.')]
            t = t[:m.start()] + " [SPECIMEN_DIMS] " + t[m.end():]

    # 4. Infiltrative Mass Dimensions (Fix: Do not skip if mass keyword occurs closer than mastectomy keyword)
    if "no discrete mass" in t or "entirely fibrocystic" in t:
        data["s10_infiltrative"] = False
    elif "infiltrative" in t or "mass" in t or "lesion" in t or "tumor" in t:
        data["s10_infiltrative"] = True
        all_3d_dims = list(re.finditer(r"([\d.]+)\s*(?:cm|mm)?\s*x\s*([\d.]+)\s*(?:cm|mm)?\s*x\s*([\d.]+)", t))
        mass_dim_match = None

        for m in reversed(all_3d_dims):
            start, end = m.start(), m.end()
            pre_context = t[max(0, start-60) : start].lower()
            post_context = t[end : min(len(t), end+50)].lower()

            if "without dimension" in post_context or "no dimension" in post_context:
                continue

            mass_kw_pos = max([pre_context.rfind(kw) for kw in ["infiltrative", "mass", "lesion", "tumor"]] + [-1])
            spec_kw_pos = max([pre_context.rfind(kw) for kw in ["mastectomy", "specimen", "overall size"]] + [-1])

            # Only skip if specimen keyword is STRICTLY AFTER mass keyword
            if spec_kw_pos > mass_kw_pos:
                continue

            if mass_kw_pos != -1 or (any(kw in post_context for kw in ["infiltrative", "mass", "lesion", "tumor"]) and "measuring" not in pre_context):
                mass_dim_match = m
                break

        if mass_dim_match:
            data["s10_inf_dims"] = [mass_dim_match.group(1).rstrip('.'), mass_dim_match.group(2).rstrip('.'), mass_dim_match.group(3).rstrip('.')]
            t = t[:mass_dim_match.start()] + " [MASS_DIMS] " + t[mass_dim_match.end():]

    # 5. Margins (Fix: Support punctuation like commas or periods after margin)
    margins = ["deep", "superior", "inferior", "medial", "lateral", "skin"]
    for m_name in margins:
        regex = rf"(?:{m_name}(?:\s+(?:surgical|resection|fascial))?\s*margin|\b{m_name}\b)\s*[,.:;]?\s*(?:is\s+(?:close\s+(?:at|to)|free\s+(?:at|to)|measured\s+(?:at|to)|involved\s+(?:at|to))?|at|=|:|\bclose\s+at\b|\bfree\s+at\b)?\s*[,.:;]?\s*([\d.]+)(?:\s*(?:cm|mm))?"
        m = re.search(regex, t, re.IGNORECASE)
        if not m:
            regex = rf"([\d.]+)(?:\s*(?:cm|mm))?\s*(?:cm\s*)?(?:from|at)\s*(?:the\s*)?{m_name}(?:\s+(?:surgical|resection|fascial))?(?:\s*margin)?"
            m = re.search(regex, t, re.IGNORECASE)
        if m:
            data[f"s11_{m_name}"] = m.group(1).rstrip('.')

    return data

# Evaluate comparison
cur_s0, cur_s10, cur_s11 = 0, 0, 0
fix_s0, fix_s10, fix_s11 = 0, 0, 0

for _, r in pw_df.iterrows():
    cid = r['case_id']
    gt = gt_data[cid]
    hyp = str(r['hyp_text'])

    d_cur = extract_data_15_sections(hyp)
    d_fix = extract_improved(hyp)

    # s0_surgical_no
    g_s0 = gt.get('s0_surgical_no')
    if are_strings_equal(g_s0, d_cur.get('s0_surgical_no')): cur_s0 += 1
    if are_strings_equal(g_s0, d_fix.get('s0_surgical_no')): fix_s0 += 1

    # s10_inf_dims
    g_s10 = gt.get('s10_inf_dims')
    if are_dims_equal(g_s10, d_cur.get('s10_inf_dims')): cur_s10 += 1
    if are_dims_equal(g_s10, d_fix.get('s10_inf_dims')): fix_s10 += 1

    # s11_deep_margin
    g_s11 = gt.get('s11_deep_margin')
    if are_num_equal(g_s11, d_cur.get('s11_deep')): cur_s11 += 1
    if are_num_equal(g_s11, d_fix.get('s11_deep')): fix_s11 += 1

print("=" * 70)
print("ACCURACY COMPARISON (1,000 CASES) - BEFORE vs AFTER TARGETED FIXES")
print("=" * 70)
print(f"{'Field':<25} | {'Before Fix':<15} | {'After Fix':<15} | {'Delta':<10}")
print("-" * 70)
print(f"{'s0_surgical_no':<25} | {cur_s0:>4}/1000 ({cur_s0/10:.1f}%) | {fix_s0:>4}/1000 ({fix_s0/10:.1f}%) | +{fix_s0 - cur_s0} cases")
print(f"{'s10_inf_dims':<25} | {cur_s10:>4}/1000 ({cur_s10/10:.1f}%) | {fix_s10:>4}/1000 ({fix_s10/10:.1f}%) | +{fix_s10 - cur_s10} cases")
print(f"{'s11_deep_margin':<25} | {cur_s11:>4}/1000 ({cur_s11/10:.1f}%) | {fix_s11:>4}/1000 ({fix_s11/10:.1f}%) | +{fix_s11 - cur_s11} cases")
print("=" * 70)
