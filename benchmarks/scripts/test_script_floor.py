import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from scripts.eval_clinical_core_metrics import KEYS, CRIT, cmp, mapped
from src.nlp.extractor import extract_data_15_sections

pure_path = BASE_DIR / "data" / "dataset_1000" / "ground_truth_1000_pure.json"
with open(pure_path, "r", encoding="utf-8") as f:
    gt_pure = json.load(f)

for cid in ["case_0001", "case_0002", "case_0003"]:
    d = gt_pure[cid]
    raw = d["raw_text"]
    pred = extract_data_15_sections(raw)
    pm = mapped(pred)
    statuses = {k: cmp(k, d[k], pm[k]) for k in KEYS}
    crit_errs = [k for k in CRIT if statuses[k] in ("FN", "FP", "WRONG")]
    all_errs = [k for k in KEYS if statuses[k] in ("FN", "FP", "WRONG")]
    cer_case = 1 if len(crit_errs) > 0 else 0
    slot_acc = round(((len(KEYS) - len(all_errs)) / len(KEYS)) * 100.0, 2)
    print(f"{cid}: CER_case={cer_case}, SlotAcc={slot_acc}%")
    assert cer_case == 0, f"Failed CER on {cid}: {crit_errs}"
    assert slot_acc == 100.0, f"Failed SlotAcc on {cid}: {all_errs}"

print("✅ Script Floor Assertion Passed 100% on cases 1, 2, 3!")
