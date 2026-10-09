"""eval_fields_15.py - per-field TP/FP/FN/TN, F1, slot agreement and error-by-category tables.
Reproduces field_metrics_15_pure_gt.csv / category_errors_15_fields.csv using the SAME comparison
logic as eval_clinical_core_metrics.py (imported, not copied), so all field and case-level numbers agree.
Usage (from project root):  python scripts/eval_fields_15.py <ground_truth.json> <benchmark_cases.csv> <outdir>"""
import sys, json, importlib.util
from pathlib import Path
import pandas as pd
BASE = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(BASE))
spec = importlib.util.spec_from_file_location("core", str(Path(__file__).resolve().parent / "eval_clinical_core_metrics.py"))
core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)
gt_path, csv_path, out = sys.argv[1], sys.argv[2], Path(sys.argv[3]); out.mkdir(parents=True, exist_ok=True)
gt = json.load(open(gt_path, encoding="utf-8")); d = pd.read_csv(csv_path)
KEYS = core.KEYS; INACT = core.INACT
def run(df, col):
    res = {}
    for cid, cat, txt in zip(df.case_id, df.category_id, df[col]):
        p = core.mapped(core.extract_data_15_sections(str(txt)))
        res[cid] = (int(cat), {k: core.cmp(k, gt[cid].get(k), p.get(k)) for k in KEYS})
    return res
systems = {"Baseline": run(d[d.system.str.startswith("Base")], "hyp_text"),
           "PW": run(d[d.system.str.startswith("Patho")], "hyp_text")}
rows, caterr = [], {k: [0]*10 for k in KEYS}; slot = {}
for k in KEYS:
    row = {"Field_ID": k}; pos = sum(1 for c in gt.values() if core.has(c.get(k)))
    row["Positive_Cases"] = pos
    for name, res in systems.items():
        tp = sum(v[1][k] == "TP" for v in res.values()); tn = sum(v[1][k] == "TN" for v in res.values())
        fn = sum(v[1][k] in ("FN", "WRONG") for v in res.values()); fp = sum(v[1][k] in ("FP", "WRONG") for v in res.values())
        P = tp/(tp+fp) if tp+fp else 0; R = tp/(tp+fn) if tp+fn else 0; F = 2*P*R/(P+R) if P+R else 0
        row[f"_{name}_F1raw"] = 100*F
        row.update({f"{name}_Prec": round(100*P, 1), f"{name}_Rec": round(100*R, 1), f"{name}_F1": round(100*F, 1),
                    f"{name}_TP": tp, f"{name}_FP": fp, f"{name}_FN": fn, f"{name}_TN": tn})
        slot[name] = slot.get(name, 0) + tp + tn
        if name == "PW":
            for v in res.values():
                if v[1][k] not in ("TP", "TN"): caterr[k][v[0]-1] += 1
    rows.append(row)
df = pd.DataFrame(rows); df.drop(columns=[c for c in df.columns if c.startswith("_")]).to_csv(out/"field_metrics_15_pure_gt_v2.csv", index=False, encoding="utf-8-sig")
ev = df[df.Positive_Cases > 0]
print("Evaluable fields:", len(ev))
for n in ("Baseline", "PW"): print(f"{n}: Macro-F1 (11 fields) = {ev['_'+n+'_F1raw'].mean():.2f}  slot agreement = {slot[n]}/15000 = {100*slot[n]/15000:.2f}%")
print("PW slot errors by field:", {k: sum(v) for k, v in caterr.items() if sum(v)}, "total", sum(sum(v) for v in caterr.values()))
pd.DataFrame([{"Field_ID": k, **{f"Cat_{i+1}": v[i] for i in range(10)}, "Total_Errors": sum(v)} for k, v in caterr.items()]).to_csv(out/"category_errors_15_fields_v2.csv", index=False, encoding="utf-8-sig")
print(df[["Field_ID","Positive_Cases","Baseline_F1","PW_F1","Baseline_TP","Baseline_FP","Baseline_FN","PW_TP","PW_FP","PW_FN"]].to_string(index=False))
