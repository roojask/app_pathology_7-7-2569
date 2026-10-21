"""
make_finetune_data.py -- leakage-safe dataset for the LoRA pilot (and Test B/C).

DESIGN
  * Every case starts from STRUCTURED values (the 15 fields), so the ground truth
    is known by construction (same keys/format as ground_truth_1000_pure.json:
    cat_idx, raw_text, s0..s14). No hand labelling, no regex-derived labels.
  * The text is rendered from phrase banks. Each slot has 7 phrasings; the split
    decides which phrasings may be used:
        train: 0-3   val: 4   test: 5-6        (test phrasings are never seen)
    Out-of-order reports (category 2) use block orders 0-4 / 5 / 6-7, and
    self-correction cues are split too (train: sorry, correction; val: wait;
    test: actually, no wait).
  * Voices are split: train/val use SEEN voices; the test texts are rendered twice:
        test_seen   -> same voices as train   (isolates the effect of new templates)
        test_unseen -> unseen accents/speakers (adds the effect of new voices)
    Both share text_id, so they can be compared pairwise.
  * Sizes (1000 audio files): train 600, val 100, test texts 150 x 2 voice sets = 300.
    All splits are balanced over the 10 categories of the thesis.
  * Surgical numbers are S-25/26-2xxx (never in the original S-24-1xxx..2xxx range
    and never S-26-1001, the example inside the P4 prompt).

USAGE
  python make_finetune_data.py --out data/dataset_ft --no-audio --floor
  python make_finetune_data.py --out data/dataset_ft --audio --noise-file noise/fume_hood.wav
  (--floor runs the repo extractor on the generated TEXT: it shows how much of any later
   CER_case difference is extractor brittleness on new phrasings, not ASR.)

Limits (state them in the thesis): the grammar is still synthetic; it widens the
phrasing but is not physician language. Ask the co-advisor to review 30-50 sentences.
"""
import argparse
import asyncio
import csv
import json
import random
import re
import sys
from pathlib import Path

# Add project root and bin to PATH
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
try:
    from configs.config import Config
except ImportError:
    pass

N_CAT = 10
PER_CAT = {"train": 60, "val": 10, "test": 15}
ALLOWED = {"train": [0, 1, 2, 3], "val": [4], "test": [5, 6]}
ORDER_IDX = {"train": [0, 1, 2, 3, 4], "val": [5], "test": [6, 7]}
CUES = {"train": ["sorry", "correction"], "val": ["wait"], "test": ["actually", "no wait"]}

SEEN_VOICES = ["en-US-ChristopherNeural", "en-US-JennyNeural", "en-US-GuyNeural", "en-US-AriaNeural"]
UNSEEN_VOICES = ["en-GB-RyanNeural", "en-AU-WilliamNeural", "en-IN-PrabhatNeural", "en-IN-NeerjaNeural"]
RATES = ["-10%", "+0%", "+10%", "+20%"]

SIDES = ["right", "left"]
PROCS = [("modified radical mastectomy", "modified"), ("simple mastectomy", "simple")]
QUADS = ["upper inner", "upper outer", "lower inner", "lower outer", "central"]

ID_BANK = ["Surgical number {sn}.", "Specimen {sn}.", "Case number {sn}.",
           "Surgical specimen number {sn}.", "Accession number {sn}.",
           "This is surgical case {sn}.", "Number {sn}."]
SPEC_BANK = ["Received in formalin is a {side} {proc} specimen measuring {d} cm.",
             "The specimen is a {side} {proc} that measures {d} cm.",
             "{side} {proc} specimen, measuring {d} cm.",
             "We received a {side} {proc} with overall dimensions of {d} cm.",
             "This is a {side} {proc}, {d} cm in size.",
             "A {side} {proc} specimen is submitted and it measures {d} cm.",
             "The {side} {proc} measures {d} cm."]
SKIN_BANK = [("The skin ellipse measures {a} x {b} cm.", "The skin ellipse is present."),
             ("Skin ellipse, {a} x {b} cm.", "Skin ellipse is attached."),
             ("An ellipse of skin measuring {a} x {b} cm is present.", "An ellipse of skin is present."),
             ("There is a skin ellipse of {a} x {b} cm.", "There is a skin ellipse."),
             ("Attached skin ellipse is {a} x {b} cm.", "Skin is attached."),
             ("The overlying skin measures {a} x {b} cm.", "The overlying skin is present."),
             ("Skin ellipse measures {a} x {b} cm.", "A skin ellipse is attached.")]
MASS_BANK = ["Sectioning reveals an infiltrative firm white mass{mdesc}{qp}.",
             "There is an infiltrative mass{mdesc}{qp}.",
             "An infiltrative yellow white mass{mdesc} is identified{qp}.",
             "The tumor is an infiltrative lesion{mdesc}{qp}.",
             "On sectioning, an infiltrative mass is seen{qp}{mdesc}.",
             "We find a poorly circumscribed infiltrative mass{mdesc}{qp}.",
             "Infiltrative mass{mdesc} noted{qp}."]
BENIGN_BANK = ["Sectioning reveals no discrete mass and entirely fibrocystic change.",
               "The cut surface shows fibrocystic change without a discrete mass.",
               "No mass lesion is identified. The breast parenchyma is fibrocystic.",
               "There is no discrete lesion, only fibrocystic change.",
               "Sectioning shows unremarkable fibrocystic breast tissue with no mass.",
               "Fibrocystic change is present and no discrete mass is seen.",
               "No discrete mass is identified and the tissue is fibrocystic."]
DEEP_BANK = ["The deep margin is {x} cm from the tumor.", "Distance to the deep margin is {x} cm.",
             "Deep margin {x} cm.", "The closest deep surgical margin measures {x} cm.",
             "The mass is {x} cm from the deep margin.", "The tumor lies {x} cm from the deep resection margin.",
             "Deep margin is clear at {x} cm."]
NODES_BANK = ["{n} lymph nodes are identified, ranging from {lo} to {hi} cm in greatest dimension.",
              "Axillary contents with {n} lymph nodes, the largest measuring {hi} cm.",
              "Identified {n} axillary lymph nodes.",
              "The axillary tail yields {n} lymph nodes measuring {lo} to {hi} cm.",
              "A total of {n} lymph nodes are found in the axillary fat.",
              "There are {n} axillary lymph nodes, up to {hi} cm.",
              "Axillary content includes {n} nodes."]
DCIS_BANK = ["Findings are suspicious for ductal carcinoma in situ with microinvasion.",
             "Histology is pending for ductal carcinoma in situ with microinvasion.",
             "Microinvasion is suspected in the setting of ductal carcinoma in situ.",
             "Please evaluate for microinvasive ductal carcinoma.",
             "Ductal carcinoma in situ with possible microinvasion is the clinical impression.",
             "The clinical impression is ductal carcinoma in situ, rule out microinvasion.",
             "Rule out microinvasion in ductal carcinoma in situ."]
NIPPLE_SCAR_BANK = [
    "The nipple is {nip}. A healed biopsy scar measuring {sc} cm is present.",
    "Nipple appears {nip}, and a {sc} cm surgical scar is noted on the skin.",
    "Examination shows an {nip} nipple with a previous biopsy scar of {sc} cm.",
    "There is a {sc} cm biopsy scar and the nipple is {nip}.",
    "Overlying nipple is {nip}, accompanied by a {sc} cm biopsy scar.",
    "The nipple is {nip} and a {sc} cm healed scar is identified.",
    "A {sc} cm biopsy scar is seen near the {nip} nipple.",
]
CAVITY_RESIDUAL_BANK = [
    "Sectioning reveals a previous surgical cavity measuring {cav} cm with a residual mass measuring {res} cm.",
    "There is a previous surgical cavity of {cav} cm containing a residual mass of {res} cm.",
    "A previous surgical cavity measuring {cav} cm is identified, with an adjacent residual mass measuring {res} cm.",
    "Cut section shows a {cav} cm previous surgical cavity and a residual mass measuring {res} cm.",
    "We identify a previous surgical cavity measuring {cav} cm with a {res} cm residual mass.",
    "A previous surgical cavity, {cav} cm, is present with a residual mass measuring {res} cm.",
    "On sectioning, a previous surgical cavity measures {cav} cm and a residual mass measures {res} cm.",
]
COMPACT_BANK = [
    "{sn} {side} {proc} {d}cm infiltrative mass {m}cm {quad} quadrant skin {sk}cm deep margin {x}cm {n} nodes.",
    "{sn} {side} {proc} {d}cm skin {sk}cm infiltrative mass {m}cm {quad} quadrant {n} nodes deep margin {x}cm.",
    "{sn} {proc} {side} {d}cm infiltrative mass {m}cm {quad} quadrant deep margin {x}cm skin {sk}cm {n} lymph nodes.",
    "Specimen {sn} {side} {proc} {d}cm skin {sk}cm {quad} quadrant infiltrative mass {m}cm deep margin {x}cm {n} nodes.",
    "{sn} {side} {proc} {d}cm infiltrative mass {m}cm {quad} quadrant {n} nodes skin {sk}cm deep margin {x}cm.",
    "{sn} {side} {proc} {d}cm skin {sk}cm deep margin {x}cm infiltrative mass {m}cm {quad} quadrant {n} lymph nodes.",
    "{sn} {proc} {side} {d}cm {n} nodes infiltrative mass {m}cm {quad} quadrant deep margin {x}cm skin {sk}cm."]
ORDERS = [["MASS", "SPEC", "ID", "SKIN", "DEEP", "NODES"], ["SPEC", "NODES", "MASS", "SKIN", "DEEP", "ID"],
          ["ID", "MASS", "DEEP", "SPEC", "SKIN", "NODES"], ["SKIN", "SPEC", "ID", "MASS", "NODES", "DEEP"],
          ["NODES", "MASS", "SPEC", "DEEP", "SKIN", "ID"], ["DEEP", "MASS", "ID", "SPEC", "NODES", "SKIN"],
          ["MASS", "DEEP", "SKIN", "ID", "SPEC", "NODES"], ["ID", "NODES", "SKIN", "MASS", "SPEC", "DEEP"]]
STD_ORDER = ["ID", "SPEC", "SKIN", "MASS", "DEEP", "NODES"]

# presence rules follow build_pure_gt() in eval_pure_gt_15_fields.py
HAS_SKIN = {1, 2, 3, 4, 7}; SKIN_DIMS = {1, 2, 4, 7}; MASS_DIMS = {1, 2, 3, 4, 7, 8, 9}
HAS_QUAD = {1, 2, 4, 7, 9}; HAS_NODES = {1, 2, 3, 5, 7, 9}; HAS_DEEP = {1, 2, 4, 7, 8, 9, 10}; NO_MASS = {5, 6, 10}


def cap(s):
    return s[:1].upper() + s[1:]


def dims(*v):
    return " x ".join(str(x) for x in v)


def build_case(rng, split, cat, idx):
    A = ALLOWED[split]
    pick = lambda bank: bank[rng.choice(A)]
    rng_extra = random.Random(f"full15-{split}-{cat}-{idx}")
    pick_extra = lambda bank: bank[rng_extra.choice(A)]

    sn = f"S-{25 + idx % 2}-{2000 + idx:04d}"
    side = rng.choice(SIDES)
    proc_raw, proc_val = rng.choice(PROCS)
    if cat == 10:
        proc_raw, proc_val = "simple mastectomy", "simple"
    d = [round(rng.uniform(5, 30), 1), round(rng.uniform(5, 25), 1), round(rng.uniform(2, 15), 1)]
    sk = [round(rng.uniform(5, 20), 1), round(rng.uniform(2, 10), 1)]
    m = [round(rng.uniform(1, 8), 1), round(rng.uniform(1, 6), 1), round(rng.uniform(1, 5), 1)]
    n = rng.randint(3, 20)
    lo, hi = round(rng.uniform(0.1, 0.8), 1), round(rng.uniform(1.0, 3.5), 1)
    quad = rng.choice(QUADS)
    deep = round(rng.uniform(0.2, 3.0), 1)

    nip_val = rng_extra.choice(["everted", "inverted", "retracted"]) if cat == 4 else None
    scar_val = True if cat == 4 else None
    scar_len = round(rng_extra.uniform(1.2, 4.5), 1)
    cav_val = True if cat == 10 else None
    cav_d = [round(rng_extra.uniform(2.5, 6.5), 1), round(rng_extra.uniform(2.0, 5.5), 1), round(rng_extra.uniform(1.5, 4.5), 1)]
    res_d = [round(rng_extra.uniform(0.8, 3.5), 1), round(rng_extra.uniform(0.8, 3.0), 1), round(rng_extra.uniform(0.6, 2.5), 1)]

    has_inf = cat not in NO_MASS
    gt = {"cat_idx": cat, "s0_surgical_no": sn, "s1_side": side, "s2_proc": proc_val,
          "s3_dims": [str(x) for x in d],
          "s4_skin": cat in HAS_SKIN, "s5_dims": [str(x) for x in sk] if cat in SKIN_DIMS else None,
          "s6_nipple": nip_val, "s7_biopsy_scar": scar_val,
          "s8_cavity": cav_val, "s9_residual_mass": [str(x) for x in res_d] if cat == 10 else None,
          "s10_infiltrative": has_inf,
          "s10_inf_dims": [str(x) for x in m] if cat in MASS_DIMS else None,
          "s10_5_quadrant": quad if cat in HAS_QUAD else None,
          "s11_deep_margin": str(deep) if cat in HAS_DEEP else None,
          "s14_check": cat in HAS_NODES}

    # ---- compact (category 7)
    if cat == 7:
        text = pick(COMPACT_BANK).format(sn=sn, side=side, proc=proc_raw, d="x".join(map(str, d)),
                                         m="x".join(map(str, m)), quad=quad, sk="x".join(map(str, sk)),
                                         x=deep, n=n)
        return gt, text, {"order": "compact", "cue": ""}

    cue = rng.choice(CUES[split])
    side_s = side
    if cat == 3:
        wrong = "left" if side == "right" else "right"
        side_s = f"{wrong}... {cue} {side}"
    blocks = {}
    blocks["ID"] = pick(ID_BANK).format(sn=sn)
    blocks["SPEC"] = cap(pick(SPEC_BANK).format(side=side_s, proc=proc_raw, d=dims(*d)))
    if cat in HAS_SKIN:
        with_d, no_d = pick(SKIN_BANK)
        blocks["SKIN"] = (with_d.format(a=sk[0], b=sk[1]) if cat in SKIN_DIMS else no_d)
        if cat == 4:
            blocks["SKIN"] += " " + pick_extra(NIPPLE_SCAR_BANK).format(nip=nip_val, sc=scar_len)
    if has_inf:
        if cat in MASS_DIMS:
            mdesc = f" measuring {dims(*m)} cm"
            if cat == 3:
                w = [round(rng.uniform(1, 4), 1) for _ in range(3)]
                mdesc = f" measuring {dims(*w)} cm... {cue} {dims(*m)} cm"
        else:
            mdesc = ""
        qp = f" in the {quad} quadrant" if cat in HAS_QUAD else ""
        blocks["MASS"] = pick(MASS_BANK).format(mdesc=mdesc, qp=qp)
        if cat == 9:
            blocks["MASS"] += " " + pick(DCIS_BANK)
    elif cat == 6:
        blocks["MASS"] = pick(BENIGN_BANK)
    elif cat == 10:
        blocks["MASS"] = pick_extra(CAVITY_RESIDUAL_BANK).format(cav=dims(*cav_d), res=dims(*res_d))
    if cat in HAS_DEEP:
        blocks["DEEP"] = pick(DEEP_BANK).format(x=deep)
        if cat == 4:
            v = [round(rng.uniform(0.3, 3.0), 1) for _ in range(4)]
            blocks["DEEP"] += (f" Superior margin {v[0]} cm, inferior margin {v[1]} cm, "
                               f"medial margin {v[2]} cm, lateral margin {v[3]} cm.")
    if cat in HAS_NODES:
        blocks["NODES"] = pick(NODES_BANK).format(n=n, lo=lo, hi=hi)

    order_id = None
    if cat == 2:
        order_id = rng.choice(ORDER_IDX[split])
        order = ORDERS[order_id]
    else:
        order = STD_ORDER
    text = " ".join(blocks[b] for b in order if b in blocks)
    return gt, text, {"order": order_id if order_id is not None else "std", "cue": cue if cat == 3 else ""}


def build_split(split, seed, start_idx):
    rng = random.Random(f"{seed}-{split}")
    cases, idx = [], start_idx
    for cat in range(1, N_CAT + 1):
        for _ in range(PER_CAT[split]):
            gt, text, meta = build_case(rng, split, cat, idx)
            gt["raw_text"] = text
            cases.append(dict(text_id=f"{split}_{idx:04d}", gt=gt, meta=meta, split=split))
            idx += 1
    rng.shuffle(cases)
    return cases, idx


# ------------------------------------------------------------------ diagnostics
def norm_a(t):
    """Skeleton text: ids and numbers replaced by placeholders, so n-grams measure PHRASE reuse."""
    t = re.sub(r"s-\d{2}-\d+", " idtok ", str(t).lower())
    t = re.sub(r"\d+(?:\.\d+)?", " numtok ", t)
    return " ".join(re.sub(r"[.,;:!?\-]", " ", t).split())


def ngrams(texts, n=4):
    out = set()
    for t in texts:
        w = norm_a(t).split()
        out |= {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}
    return out


def leakage_report(by_split, testA_texts=None):
    print("\n[Leakage] share of 4-/6-grams of X (numbers and ids masked) found in TRAIN text")
    for n in (4, 6):
        tr = ngrams([c["gt"]["raw_text"] for c in by_split["train"]], n)
        for s in ("val", "test"):
            g = ngrams([c["gt"]["raw_text"] for c in by_split[s]], n)
            print(f"  {n}-gram {s:<5}: {100 * len(g & tr) / max(1, len(g)):5.1f}%  ({len(g & tr)}/{len(g)})")
        if testA_texts:
            g = ngrams(testA_texts, n)
            print(f"  {n}-gram TestA : {100 * len(g & tr) / max(1, len(g)):5.1f}%  (original 300 cases vs new TRAIN)")
    print("  Generic fragments (e.g. 'lymph nodes in the') are shared by any English report, so 4-gram")
    print("  overlap is never near 0. Use the 6-gram rows and the TestA row as the contamination check.")


def floor_check(by_split, repo):
    sys.path.insert(0, str(repo))
    from src.nlp.extractor import extract_data_15_sections
    from scripts.eval_clinical_core_metrics import KEYS, CRIT, cmp, mapped
    print("\n[Extractor floor] repo extractor run on the generated TEXT (no ASR involved)")
    for s in ("train", "val", "test"):
        err_cases, fails = 0, {}
        for c in by_split[s]:
            pm = mapped(extract_data_15_sections(c["gt"]["raw_text"]))
            bad = [k for k in KEYS if cmp(k, c["gt"].get(k), pm.get(k)) in ("FN", "FP", "WRONG")]
            if any(k in CRIT for k in bad):
                err_cases += 1
            for k in bad:
                fails[k] = fails.get(k, 0) + 1
        n = len(by_split[s])
        top = sorted(fails.items(), key=lambda kv: -kv[1])[:5]
        print(f"  {s:<5}: CER_case on perfect text = {100 * err_cases / n:5.1f}%   worst fields: {top}")
    print("  Any CER_case above 0% here is extractor brittleness on new phrasings. Report ASR-level")
    print("  metrics (WER-B, critical-token errors) as primary for the fine-tuning comparison.")


# ------------------------------------------------------------------ audio
def generate_fume_hood_wav(wav_path: Path, duration_sec: int = 60, sr: int = 16000, seed: int = 2026):
    """
    Generate realistic laboratory fume-hood exhaust noise (centrifugal fan hum + duct airflow rumble).
    Combines fundamental motor/blade-pass harmonics (100 Hz, 200 Hz, 300 Hz) with
    low-pass filtered turbulent airflow noise (< 700 Hz) + mild broadband air hiss.
    """
    import numpy as np
    from scipy.signal import butter, filtfilt
    from scipy.io import wavfile

    rng = np.random.default_rng(seed)
    n = duration_sec * sr
    t = np.arange(n, dtype=np.float64) / sr

    # 1. Broadband white noise filtered into low-frequency duct rumble (< 650 Hz)
    white = rng.standard_normal(n)
    b_low, a_low = butter(4, 650.0 / (sr / 2.0), btype="low")
    duct_rumble = filtfilt(b_low, a_low, white)

    # 2. Mid-band airflow turbulence (300 - 1800 Hz)
    b_band, a_band = butter(2, [300.0 / (sr / 2.0), 1800.0 / (sr / 2.0)], btype="band")
    airflow_hiss = filtfilt(b_band, a_band, rng.standard_normal(n)) * 0.35

    # 3. Centrifugal fan blade-pass harmonics (120 Hz, 240 Hz, 360 Hz with slow amplitude modulation)
    mod = 1.0 + 0.08 * np.sin(2 * np.pi * 0.5 * t)
    fan_hum = mod * (
        0.45 * np.sin(2 * np.pi * 120.0 * t + rng.uniform(0, 2 * np.pi))
        + 0.25 * np.sin(2 * np.pi * 240.0 * t + rng.uniform(0, 2 * np.pi))
        + 0.12 * np.sin(2 * np.pi * 360.0 * t + rng.uniform(0, 2 * np.pi))
    )

    noise = duct_rumble + airflow_hiss + fan_hum
    noise = noise / (np.max(np.abs(noise)) + 1e-12) * 0.85
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(str(wav_path), sr, (noise * 32767.0).astype(np.int16))
    return wav_path


def mix_noise(speech, noise, snr_db, rng=None):
    import numpy as np
    n_speech = len(speech)
    if len(noise) > n_speech:
        start = rng.randint(0, len(noise) - n_speech) if rng is not None else 0
        n_seg = noise[start:start + n_speech].astype("float64")
    else:
        n_seg = np.resize(noise, n_speech).astype("float64")
    # Measure active speech power (excluding digital silence pauses)
    active = speech[np.abs(speech) > 0.01]
    ps = float(np.mean(active ** 2)) + 1e-12 if len(active) > 100 else float(np.mean(speech ** 2)) + 1e-12
    pn = float(np.mean(n_seg ** 2)) + 1e-12
    k = (ps / (pn * (10.0 ** (snr_db / 10.0)))) ** 0.5
    return np.clip(speech + k * n_seg, -1.0, 1.0)


async def synth_all(jobs, out_dir, noise_file, seed):
    import edge_tts
    import numpy as np
    from scipy.io import wavfile
    from faster_whisper.audio import decode_audio

    noise = None
    if noise_file and Path(noise_file).exists():
        noise = decode_audio(str(noise_file), sampling_rate=16000).astype("float64")

    clean_dir = out_dir.parent / "audio_clean"
    clean_dir.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(8)
    total = len(jobs)
    done_count = 0

    async def one(idx_job, job):
        nonlocal done_count
        async with sem:
            path = out_dir / f"{job['case_id']}.wav"
            clean_path = clean_dir / f"{job['case_id']}.wav"
            if path.exists() and (job["snr_db"] is None or clean_path.exists()):
                done_count += 1
                return
            tmp = out_dir / f"{job['case_id']}.tmp.mp3"
            for attempt in range(4):
                try:
                    await edge_tts.Communicate(job["text"], job["voice"], rate=job["rate"]).save(str(tmp))
                    break
                except Exception:
                    if attempt == 3:
                        raise
                    await asyncio.sleep(2 * (attempt + 1))
            x = decode_audio(str(tmp), sampling_rate=16000).astype("float64")
            tmp.unlink(missing_ok=True)

            # Save clean copy if this case is noisy or part of Category 8 / Val / Test
            if job["snr_db"] is not None or job["split"] != "train":
                wavfile.write(str(clean_path), 16000, (np.clip(x, -1.0, 1.0) * 32767.0).astype(np.int16))

            if job["snr_db"] is not None and noise is not None:
                job_rng = random.Random(f"{seed}-{job['case_id']}")
                y = mix_noise(x, noise, job["snr_db"], rng=job_rng)
            else:
                y = np.clip(x, -1.0, 1.0)
            wavfile.write(str(path), 16000, (y * 32767.0).astype(np.int16))
            done_count += 1
            if done_count == 1 or done_count % 50 == 0 or done_count == total:
                print(f"  [TTS Progress] {done_count}/{total} audio files synthesized (latest: {job['case_id']})...", flush=True)

    if jobs:
        # Synthesize val and test splits first so evaluation sets are ready immediately, then train
        priority = {"val": 0, "test_seen": 1, "test_unseen": 2, "train": 3}
        ordered_jobs = sorted(jobs, key=lambda j: priority.get(j["split"], 9))
        await one(0, ordered_jobs[0])
        if len(ordered_jobs) > 1:
            await asyncio.gather(*[one(i, j) for i, j in enumerate(ordered_jobs[1:], 1)])




def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("data/dataset_ft"))
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--audio", action="store_true")
    ap.add_argument("--no-audio", dest="audio", action="store_false")
    ap.add_argument("--noise-file", default="auto", help="Path to fume-hood wav, 'auto' to synthesize, or 'none' for clean")
    ap.add_argument("--floor", action="store_true", help="run repo extractor on the text")
    ap.add_argument("--repo", type=Path, default=None)
    ap.add_argument("--testA-gt", default=None, help="ground_truth_1000_pure.json, for the leakage report")
    ap.add_argument("--testA-texts-file", default=None, help="optional JSON list of Test A texts")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "audio").mkdir(exist_ok=True)

    noise_file = args.noise_file
    if noise_file == "auto":
        noise_wav = args.out / "fume_hood_noise.wav"
        if not noise_wav.exists():
            print("Generating realistic fume-hood exhaust noise file:", noise_wav)
            generate_fume_hood_wav(noise_wav, duration_sec=60, sr=16000, seed=args.seed)
        noise_file = str(noise_wav)
    elif noise_file in (None, "none", ""):
        noise_file = None

    by_split, idx = {}, 0
    for s in ("train", "val", "test"):
        by_split[s], idx = build_split(s, args.seed, idx)
    assert len({c["gt"]["s0_surgical_no"] for sp in by_split.values() for c in sp}) == idx, "duplicate ids"

    testA = None
    if args.testA_gt:
        g = json.load(open(args.testA_gt, encoding="utf-8"))
        testA = [d["raw_text"] for d in g.values()]
    elif args.testA_texts_file:
        testA = json.load(open(args.testA_texts_file, encoding="utf-8"))

    rng = random.Random(args.seed + 1)
    manifest, jobs, gt_out = [], [], {}
    for s, label_sets in (("train", [("train", SEEN_VOICES)]), ("val", [("val", SEEN_VOICES)]),
                          ("test", [("test_seen", SEEN_VOICES), ("test_unseen", UNSEEN_VOICES)])):
        for c in by_split[s]:
            cat = c["gt"]["cat_idx"]
            for label, voices in label_sets:
                cid = f"{label}_{c['text_id'].split('_')[1]}"
                rate = "+35%" if cat == 7 else rng.choice(RATES)
                snr = None
                if noise_file:
                    if label == "train":
                        # Train: Category 8 at -10 dB, plus multi-SNR noise on ~25% of other categories for robustness
                        snr = -10 if cat == 8 else rng.choice([None, None, None, None, None, None, 10, 5, 0, -5])
                    else:
                        # Val / Test: Category 8 is strictly -10 dB Fume Hood Noise; Categories 1-7, 9-10 are Clean
                        snr = -10 if cat == 8 else None
                row = dict(case_id=cid, text_id=c["text_id"], split=label, category=cat,
                           voice=rng.choice(voices), rate=rate, snr_db=snr,
                           order=c["meta"]["order"], cue=c["meta"]["cue"], text=c["gt"]["raw_text"])
                manifest.append(row)
                gt_out[cid] = dict(c["gt"])
                jobs.append(dict(case_id=cid, split=label, text=row["text"], voice=row["voice"], rate=rate, snr_db=snr))

    with open(args.out / "manifest.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(manifest[0].keys()))
        w.writeheader(); w.writerows(manifest)
    json.dump(gt_out, open(args.out / "ground_truth_ft.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for label in ("train", "val", "test_seen", "test_unseen"):
        with open(args.out / f"{label}.jsonl", "w", encoding="utf-8") as f:
            for r in manifest:
                if r["split"] == label:
                    f.write(json.dumps({"audio": f"audio/{r['case_id']}.wav", "text": r["text"],
                                        "case_id": r["case_id"], "category": r["category"],
                                        "snr_db": r["snr_db"]},
                                       ensure_ascii=False) + "\n")
    counts = {l: sum(r["split"] == l for l in manifest) for l in ("train", "val", "test_seen", "test_unseen")}
    print("files:", counts, "| unique texts:", idx)
    print("example train:", by_split["train"][0]["gt"]["raw_text"])
    print("example test :", by_split["test"][0]["gt"]["raw_text"])

    leakage_report(by_split, testA)
    if args.floor:
        floor_check(by_split, args.repo or Path(__file__).resolve().parents[1])
    if args.audio:
        asyncio.run(synth_all(jobs, args.out / "audio", noise_file, args.seed))
        print("audio written to", args.out / "audio")
    else:
        print("\n(audio skipped; add --audio to synthesize with edge-tts)")


if __name__ == "__main__":
    main()

