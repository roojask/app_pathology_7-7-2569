"""
run_prompt_sweep.py  --  Prompt Sensitivity Study (run on YOUR machine).

Usage (from anywhere; the repo root is auto-detected):
  python run_prompt_sweep.py --split dev  --limit 5          # smoke test (~5 min)
  python run_prompt_sweep.py --split dev                     # 200 cases x 10 variants
  python run_prompt_sweep.py --split test                    # 300 cases x 10 variants
  python run_prompt_sweep.py --split test --variants P0_none,P4_full_cap

Design (mirrors run_controlled_ablation_300cases.py so numbers are comparable):
  * same model loader (get_faster_whisper_model: small, int8, cpu, 8 threads)
  * language=en, temperature=0.0, beam_size=1, best_of=1
  * same extractor / cmp / mapped / CRIT / norm_a / norm_b as the thesis
  * --denoise off (default) uses the raw mp3, like C3/C6; 'on' uses
    denoise_audio() (afftdn + silenceremove) like C5. Keep it FIXED for the
    whole prompt study so the prompt is the only changing factor.
  * variant order is shuffled per case (seeded) to spread CPU-load drift
  * results are appended per (case, variant); re-running resumes where it stopped
"""
import argparse
import csv
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path


def find_repo(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "src").is_dir() and (p / "configs").is_dir():
            return p
    raise SystemExit("Cannot find repo root (a folder containing src/ and configs/). Use --repo.")


ap = argparse.ArgumentParser()
ap.add_argument("--repo", type=Path, default=None)
ap.add_argument("--split", choices=["dev", "test"], required=True)
ap.add_argument("--denoise", choices=["off", "on"], default="off")
ap.add_argument("--variants", default="", help="comma-separated subset, default all")
ap.add_argument("--limit", type=int, default=0, help="first N cases only (smoke test)")
ap.add_argument("--out", type=Path, default=None)
ap.add_argument("--seed", type=int, default=42)
args = ap.parse_args()

BASE = args.repo or find_repo(Path(__file__).resolve())
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

import jiwer  # noqa: E402
from configs.config import Config  # noqa: E402
from src.nlp.extractor import extract_data_15_sections, generate_confidence_flags  # noqa: E402
from src.stt.faster_whisper_engine import get_faster_whisper_model  # noqa: E402
from src.stt.whisper_model import denoise_audio  # noqa: E402
from scripts.eval_clinical_core_metrics import KEYS, CRIT, cmp, mapped  # noqa: E402
from benchmarks.scripts.text_norm_utils import norm_a, norm_b  # noqa: E402
from splits import get_split  # noqa: E402
from prompts import build_variants  # noqa: E402

DATASET = BASE / "data" / "dataset_1000"
GT_PATH = DATASET / "ground_truth_1000_pure.json"
AUDIO_DIR = DATASET / "audio"
OUT = args.out or (Path(__file__).resolve().parent / "results" / f"prompt_sweep_{args.split}_denoise{args.denoise}.csv")
OUT.parent.mkdir(parents=True, exist_ok=True)

LEXICON = ["mastectomy", "lumpectomy", "formalin", "infiltrative", "axillary", "fibrocystic",
           "circumscribed", "subareolar", "quadrant", "superior", "inferior", "medial", "lateral",
           "paraffin", "carcinoma", "everted", "inverted", "ulceration", "residual", "surgical",
           "margin", "deep", "lymph", "nodes", "right", "left"]


def edits(ref, hyp):
    """(S, D, I, N) word-level; guards empty hypothesis."""
    n = len(ref.split())
    if n == 0:
        return 0, 0, 0, 0
    if not hyp.strip():
        return 0, n, 0, n
    o = jiwer.process_words(ref, hyp)
    return o.substitutions, o.deletions, o.insertions, n


def lexicon_counts(ref_b, hyp_b):
    rc, hc = Counter(ref_b.split()), Counter(hyp_b.split())
    total = sum(rc[w] for w in LEXICON)
    hits = sum(min(rc[w], hc[w]) for w in LEXICON)
    return hits, total


def ngrams(text, n=4):
    w = norm_a(text).split()
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def leak_count(prompt, ref, hyp):
    """4-grams copied from the prompt into the output that are NOT in the reference."""
    if not prompt:
        return 0
    return len((ngrams(prompt) & ngrams(hyp)) - ngrams(ref))


def check_value_overlap(variants, gt, cases):
    """Warn if a few-shot example dimension triplet is also a ground-truth value."""
    triplets = {"P3a_format_only": [(12.5, 8.0, 3.5)], "P3b_fewshot_clinical": [(6.5, 4.0, 2.5), (1.4, 1.2, 0.9)]}
    for name, trips in triplets.items():
        if name not in variants:
            continue
        for cid, _ in cases:
            for k in ("s3_dims", "s5_dims", "s10_inf_dims"):
                v = gt[cid].get(k)
                try:
                    t = tuple(round(float(x), 1) for x in v)
                except Exception:
                    continue
                if t in trips:
                    print(f"[WARN] {name}: example dims {t} equal GT {k} of case {cid}. Change the example.")


def main():
    gt = json.load(open(GT_PATH, encoding="utf-8"))
    cases = get_split(gt, args.split)
    if args.limit:
        cases = cases[:args.limit]

    model = get_faster_whisper_model()
    tok = model.hf_tokenizer

    def count_tokens(text):
        return len(tok.encode(" " + text.strip(), add_special_tokens=False).ids)

    variants = build_variants(Config.PATHOLOGY_PROMPT, count_tokens)
    if args.variants:
        keep = [v.strip() for v in args.variants.split(",")]
        unknown = [v for v in keep if v not in variants]
        if unknown:
            raise SystemExit(f"unknown variants: {unknown}; available: {list(variants)}")
        variants = {k: variants[k] for k in keep}

    print(f"split={args.split} cases={len(cases)} denoise={args.denoise} variants={len(variants)}")
    for k, v in variants.items():
        print(f"  {k:<22} tokens={count_tokens(v) if v else 0}")
    check_value_overlap(variants, gt, cases)

    # resume
    done = set()
    if OUT.exists():
        with open(OUT, encoding="utf-8", newline="") as f:
            done = {(r["case_id"], r["variant"]) for r in csv.DictReader(f)}
        print(f"resuming: {len(done)} rows already in {OUT.name}")

    # warmup (2 passes, like the thesis ablation)
    first_audio = AUDIO_DIR / f"{cases[0][0]}.mp3"
    for _ in range(2):
        segs, _ = model.transcribe(str(first_audio), language="en", beam_size=1)
        _ = [s.text for s in segs]

    header = (["split", "denoise", "case_id", "category", "variant", "prompt_tokens",
               "wer_a", "wer_b", "S_a", "D_a", "I_a", "N_a", "S_b", "D_b", "I_b", "N_b",
               "cer_case", "n_omission", "n_commission", "crit_omission", "crit_commission",
               "lex_hits", "lex_total", "leak_ngrams", "flag_n", "lowconf_n", "latency_s", "hyp"]
              + [f"st_{k}" for k in KEYS])
    new_file = not OUT.exists()
    fh = open(OUT, "a", encoding="utf-8", newline="")
    w = csv.DictWriter(fh, fieldnames=header)
    if new_file:
        w.writeheader()

    t_start = time.time()
    for ci, (cid, cat) in enumerate(cases, 1):
        ref = gt[cid]["raw_text"]
        audio = AUDIO_DIR / f"{cid}.mp3"
        if args.denoise == "on":
            audio = denoise_audio(audio)

        order = list(variants.items())
        random.Random(f"{args.seed}-{cid}").shuffle(order)

        for name, prompt in order:
            if (cid, name) in done:
                continue
            t0 = time.time()
            segs, _ = model.transcribe(str(audio), language="en", temperature=0.0,
                                       initial_prompt=prompt, beam_size=1, best_of=1)
            hyp = " ".join(s.text for s in segs).strip()  # generator consumed inside timing
            lat = time.time() - t0

            ra, ha, rb, hb = norm_a(ref), norm_a(hyp), norm_b(ref), norm_b(hyp)
            Sa, Da, Ia, Na = edits(ra, ha)
            Sb, Db, Ib, Nb = edits(rb, hb)

            pred = extract_data_15_sections(hyp)
            pm = mapped(pred)
            st = {k: cmp(k, gt[cid].get(k), pm.get(k)) for k in KEYS}
            om = sum(s == "FN" for s in st.values())
            co = sum(s in ("FP", "WRONG") for s in st.values())
            c_om = sum(st[k] == "FN" for k in CRIT)
            c_co = sum(st[k] in ("FP", "WRONG") for k in CRIT)
            lh, lt = lexicon_counts(rb, hb)

            row = dict(split=args.split, denoise=args.denoise, case_id=cid, category=cat,
                       variant=name, prompt_tokens=count_tokens(prompt) if prompt else 0,
                       wer_a=(Sa + Da + Ia) / Na if Na else 0.0, wer_b=(Sb + Db + Ib) / Nb if Nb else 0.0,
                       S_a=Sa, D_a=Da, I_a=Ia, N_a=Na, S_b=Sb, D_b=Db, I_b=Ib, N_b=Nb,
                       cer_case=int(c_om + c_co > 0), n_omission=om, n_commission=co,
                       crit_omission=c_om, crit_commission=c_co, lex_hits=lh, lex_total=lt,
                       leak_ngrams=leak_count(prompt, ref, hyp),
                       flag_n=len(generate_confidence_flags(pred)),
                       lowconf_n=len(pred.get("_low_confidence") or []),
                       latency_s=round(lat, 3), hyp=hyp)
            row.update({f"st_{k}": v for k, v in st.items()})
            w.writerow(row)
            fh.flush()

        el = time.time() - t_start
        print(f"[{ci}/{len(cases)}] {cid} cat={cat}  elapsed={el/60:.1f} min", flush=True)

    fh.close()
    print("done ->", OUT)


if __name__ == "__main__":
    main()
