"""Generate a fresh text-level test set for the dimension-assignment fix.
Phrasing is deliberately different from the original 1,000-case templates.
Usage: python generate_fresh_testset.py [N] [seed]  ->  fresh_testset.json
NOTE: written by the same author who wrote the fix, so it is NOT independent evidence.
Have a teammate add phrasings, and synthesize audio from these texts to test the full pipeline."""
import json, random, sys
N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
rng = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 else 2026)
QUAD = ["upper outer quadrant", "lower outer quadrant", "upper inner quadrant", "lower inner quadrant", "central region"]
def dims(): return [f"{rng.uniform(0.6, 24):.1f}" for _ in range(3)]
def fmt(d):
    sep = rng.choice([" x ", "x", " by "]); s = sep.join(d)
    return s + rng.choice([" cm", "cm", " centimeters"]) if sep != " by " else s + " cm"
cases = {}
for i in range(1, N + 1):
    side = rng.choice(["left", "right"]); proc = rng.choice(["simple", "modified radical"])
    spec, mass = dims(), dims(); benign = rng.random() < 0.2
    sn = f"S-24-{rng.randint(1000, 1999)}"; dm = f"{rng.uniform(0.2, 3.0):.1f}"
    spec_s = rng.choice([
        f"The specimen is a {side} {proc} mastectomy measuring {fmt(spec)}.",
        f"Received is a {side} {proc} mastectomy, overall dimensions {fmt(spec)}.",
        f"{side.capitalize()} {proc} mastectomy specimen measures {fmt(spec)} overall."])
    mass_s = rng.choice([
        f"An infiltrative mass measuring {fmt(mass)} is seen in the {rng.choice(QUAD)}.",
        f"There is a firm tumor measuring {fmt(mass)} in the {rng.choice(QUAD)}.",
        f"Sectioning shows a lesion {fmt(mass)} located at the {rng.choice(QUAD)}."])
    benign_s = "Sectioning shows no discrete mass, entirely fibrocystic change."
    body = [spec_s, benign_s] if benign else ([mass_s, spec_s] if rng.random() < 0.5 else [spec_s, mass_s])
    parts = body + [f"Surgical number {sn}.", f"Deep margin {dm} cm."]
    text = " ".join(parts)
    gt = {"s0_surgical_no": sn, "s1_side": side, "s3_dims": spec, "s10_infiltrative": not benign,
          "s10_inf_dims": None if benign else mass, "s11_deep_margin": dm}
    cases[f"fresh_{i:04d}"] = {"text": text, "gt": gt, "mass_first": (not benign) and body[0] == mass_s}
json.dump(cases, open("fresh_testset.json", "w"), ensure_ascii=False, indent=1)
print(len(cases), "cases written")
