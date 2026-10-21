import json
import sys
import random
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from scripts.eval_clinical_core_metrics import KEYS, CRIT, cmp, mapped
from src.nlp.extractor import extract_data_15_sections

pure_path = BASE_DIR / "data" / "dataset_1000" / "ground_truth_1000_pure.json"
with open(pure_path, "r", encoding="utf-8") as f:
    gt_pure = json.load(f)

# Stratified sampling 30 cases per category (total 300 cases)
random.seed(42)
cats = {}
for cid, d in gt_pure.items():
    c_id = d.get("cat_idx", 1)
    cats.setdefault(c_id, []).append(cid)

selected = []
for c_id in sorted(cats.keys()):
    c_list = sorted(cats[c_id])
    sampled = random.sample(c_list, min(30, len(c_list)))
    for cid in sampled:
        selected.append(cid)

print(f"Testing script floor across all {len(selected)} sampled cases...")
failed_cases = []
for cid in selected:
    d = gt_pure[cid]
    raw = d["raw_text"]
    pred = extract_data_15_sections(raw)
    pm = mapped(pred)
    statuses = {k: cmp(k, d[k], pm[k]) for k in KEYS}
    crit_errs = [k for k in CRIT if statuses[k] in ("FN", "FP", "WRONG")]
    all_errs = [k for k in KEYS if statuses[k] in ("FN", "FP", "WRONG")]
    cer_case = 1 if len(crit_errs) > 0 else 0
    slot_acc = round(((len(KEYS) - len(all_errs)) / len(KEYS)) * 100.0, 2)
    if cer_case != 0 or slot_acc != 100.0:
        failed_cases.append((cid, cer_case, slot_acc, crit_errs, all_errs))

if failed_cases:
    print(f"FAILED on {len(failed_cases)} cases:")
    for f in failed_cases[:10]:
        print(" ", f)
else:
    print(f"SUCCESS: All {len(selected)} sampled cases passed Script Floor! (CER_case=0, SlotAcc=100.0%)")
