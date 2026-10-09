import sys, json
root = sys.argv[1]; sys.path.insert(0, root)
from src.nlp.extractor import extract_data_15_sections as ex
cases = json.load(open(sys.argv[2] if len(sys.argv)>2 else 'fresh_test/fresh_testset.json'))
def dq(a, b):
    try: return a is not None and b is not None and len(a) == len(b) and all(abs(float(x) - float(y)) < .05 for x, y in zip(a, b))
    except Exception: return False
tot = {"s3_dims": [0, 0], "s10_inf_dims": [0, 0]}; seg = {}
for cid, c in cases.items():
    p = ex(c["text"]); g = c["gt"]
    ok3 = dq(g["s3_dims"], p.get("s3_dims")); okm = (not g["s10_inf_dims"] and not p.get("s10_inf_dims")) or dq(g["s10_inf_dims"], p.get("s10_inf_dims"))
    k = "mass-first" if c["mass_first"] else "other"
    s = seg.setdefault(k, [0, 0, 0]); s[0] += 1; s[1] += ok3; s[2] += okm
for k, s in seg.items(): print(f"{k}: n={s[0]} specimen-dims correct {s[1]} ({100*s[1]/s[0]:.1f}%), mass-dims correct {s[2]} ({100*s[2]/s[0]:.1f}%)")
