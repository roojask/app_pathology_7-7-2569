"""
metrics_clean.py -- Unified 3-Tier Evaluation Metrics for the Clean-Slate Thesis Redesign.

Tier 1 (Clinical ASR):
  - Normalized WER (%)
  - C-TER (%): Clinical Term Error Rate (anatomical, pathological, and surgical lexicon tokens)
  - N-DER (%): Numerical & Dimension Error Rate (numbers, specimen IDs, 'x', 'cm', 'mm')

Tier 2 (Clinical IE & Safety):
  - Active 11-Field Precision, Recall, Macro-F1, and Slot Accuracy (%)
  - Unspoken 4-Field False-Trigger Rate (%)
  - Critical Case Error Rate (CER_case, %) + Omission / Commission breakdown
  - Safety Flag Coverage (%) & Risk-Coverage Curve points

Tier 3 (Computational Efficiency):
  - Latency (s/case) & Real-Time Factor (RTF = t_proc / t_audio)
"""
import math
import re
import sys
from pathlib import Path
import numpy as np
import jiwer
from scipy import stats

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.nlp.extractor_v3 import extract_data_15_sections_v3, generate_safety_flags_v3
from scripts.eval_clinical_core_metrics import KEYS, CRIT, INACT, cmp as _legacy_cmp, dims_eq, mapped, wilson

ACTIVE_KEYS = list(KEYS)


def cmp(k, g, p):
    if k == "s9_residual_mass" and g and p:
        return "TP" if dims_eq(g, p) else "WRONG"
    return _legacy_cmp(k, g, p)

CLINICAL_TERMS = {
    "mastectomy", "modified", "radical", "simple", "specimen", "formalin",
    "infiltrative", "fibrocystic", "discrete", "mass", "lesion", "tumor", "tumour",
    "quadrant", "upper", "lower", "inner", "outer", "central",
    "margin", "margins", "deep", "superior", "inferior", "medial", "lateral", "resection", "surgical",
    "skin", "ellipse", "overlying", "axillary", "lymph", "node", "nodes",
    "ductal", "carcinoma", "situ", "microinvasion", "microinvasive",
    "unremarkable", "parenchyma", "circumscribed", "right", "left",
    "nipple", "everted", "inverted", "retracted", "biopsy", "scar", "healed", "cavity", "residual",
}

UNIT_DIM_TOKENS = {"cm", "mm", "x"}

_WORD_NUMS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
    "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18", "nineteen": "19",
    "twenty": "20", "thirty": "30",
}


def normalize_for_asr_eval(text: str) -> str:
    """
    Standardized Medical Inverse Text Normalization (ITN) applied identically to
    Reference and Hypothesis across ALL ASR architectures (Whisper, Vosk, Wav2Vec2).
    """
    if not text:
        return ""
    t = str(text).lower()
    t = t.replace("centimeters", "cm").replace("centimeter", "cm")
    t = t.replace("millimeters", "mm").replace("millimeter", "mm")
    t = t.replace("×", " x ").replace("*", " x ")

    # Convert spoken numbers ("two point five", "twenty five") for fair cross-model ITN
    tens_map = {"twenty": 20, "thirty": 30}
    ones_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
    for ten_w, ten_v in tens_map.items():
        for one_w, one_v in ones_map.items():
            t = re.sub(rf"\b{ten_w}[\s\-]+{one_w}\b", str(ten_v + one_v), t)
    for w, d in _WORD_NUMS.items():
        t = re.sub(rf"\b{w}\b", d, t)
    t = re.sub(r"(\d+)\s+point\s+(\d+)", r"\1.\2", t)

    # Normalize surgical IDs like "s 25 2001" or "s-25-2001" -> "s 25 2001"
    for _ in range(2):
        t = re.sub(r"(\d)\s*(?:x|by|times)\s*(?=\d)", r"\1 x ", t)
    t = re.sub(r"(\d)(cm|mm)\b", r"\1 \2", t)
    t = re.sub(r"[.,;:!?\-]", " ", t)
    return " ".join(t.split())


def is_numerical_or_dim_token(w: str) -> bool:
    clean = re.sub(r"[^a-z0-9.]", "", w.lower())
    if not clean:
        return False
    if clean in UNIT_DIM_TOKENS:
        return True
    return bool(re.search(r"\d", clean))


def is_clinical_term_token(w: str) -> bool:
    clean = re.sub(r"[^a-z]", "", w.lower())
    return clean in CLINICAL_TERMS


def compute_asr_metrics(ref: str, hyp: str) -> dict:
    """
    Computes Normalized WER, Clinical Term Error Rate (C-TER), and
    Numerical & Dimension Error Rate (N-DER) via dynamic programming word alignment.
    """
    r_str = normalize_for_asr_eval(ref)
    h_str = normalize_for_asr_eval(hyp)
    if not r_str:
        return {"wer_norm": 0.0, "c_ter": 0.0, "n_der": 0.0, "c_tot": 0, "c_err": 0, "n_tot": 0, "n_err": 0}
    if not h_str:
        r_toks = r_str.split()
        c_tot = sum(1 for w in r_toks if is_clinical_term_token(w))
        n_tot = sum(1 for w in r_toks if is_numerical_or_dim_token(w))
        return {
            "wer_norm": 100.0,
            "c_ter": 100.0 if c_tot else 0.0,
            "n_der": 100.0 if n_tot else 0.0,
            "c_tot": c_tot, "c_err": c_tot,
            "n_tot": n_tot, "n_err": n_tot,
        }

    wer_val = float(jiwer.wer(r_str, h_str) * 100.0)
    r = r_str.split()
    h = h_str.split()
    n, m = len(r), len(h)

    D = np.zeros((n + 1, m + 1), dtype=np.int32)
    D[:, 0] = np.arange(n + 1)
    D[0, :] = np.arange(m + 1)
    for i in range(1, n + 1):
        rw = r[i - 1]
        for j in range(1, m + 1):
            cost = 0 if rw == h[j - 1] else 1
            D[i, j] = min(D[i - 1, j] + 1, D[i, j - 1] + 1, D[i - 1, j - 1] + cost)

    c_tot = c_err = n_tot = n_err = 0
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and D[i, j] == D[i - 1, j - 1] + (0 if r[i - 1] == h[j - 1] else 1):
            rw, hw = r[i - 1], h[j - 1]
            is_err = int(rw != hw)
            if is_clinical_term_token(rw):
                c_tot += 1
                c_err += is_err
            if is_numerical_or_dim_token(rw):
                n_tot += 1
                n_err += is_err
            i -= 1
            j -= 1
        elif i > 0 and D[i, j] == D[i - 1, j] + 1:
            rw = r[i - 1]
            if is_clinical_term_token(rw):
                c_tot += 1
                c_err += 1
            if is_numerical_or_dim_token(rw):
                n_tot += 1
                n_err += 1
            i -= 1
        else:
            j -= 1

    return {
        "wer_norm": round(wer_val, 4),
        "c_ter": round(100.0 * c_err / c_tot, 4) if c_tot > 0 else 0.0,
        "n_der": round(100.0 * n_err / n_tot, 4) if n_tot > 0 else 0.0,
        "c_tot": c_tot,
        "c_err": c_err,
        "n_tot": n_tot,
        "n_err": n_err,
    }


def evaluate_case_ie(
    hyp_text: str,
    gt_case: dict,
    avg_logprob: float | None = None,
    min_word_prob: float | None = None,
) -> dict:
    """
    Evaluates a single case using extractor_v3 on the 11 Active CAP fields and 6 Critical fields.
    """
    pred = extract_data_15_sections_v3(str(hyp_text))
    pm = mapped(pred)
    outcomes = {k: cmp(k, gt_case.get(k), pm.get(k)) for k in KEYS}

    active_correct = sum(1 for k in ACTIVE_KEYS if outcomes[k] in ("TP", "TN"))
    slot_acc_active11 = 100.0 * active_correct / len(ACTIVE_KEYS)

    crit_bad = [k for k in CRIT if outcomes[k] not in ("TP", "TN")]
    is_crit_err = int(len(crit_bad) > 0)
    crit_omissions = sum(1 for k in CRIT if outcomes[k] == "FN")
    crit_commissions = sum(1 for k in CRIT if outcomes[k] in ("FP", "WRONG"))
    unspoken_fp = sum(1 for k in INACT if outcomes[k] in ("FP", "WRONG"))

    flags = generate_safety_flags_v3(
        pred,
        cat_idx=gt_case.get("cat_idx"),
        avg_logprob=avg_logprob,
        min_word_prob=min_word_prob,
    )
    # Composite uncertainty score for continuous Risk-Coverage Curve
    risk_score = 0.0
    if flags.get("missing_side") or flags.get("missing_specimen_dims") or flags.get("unspecified_lesion_status"):
        risk_score += 2.0
    if flags.get("phonetic_benign_or_lesion_variant") or flags.get("ambiguous_margin_modifier") or flags.get("homophone_write_for_right"):
        risk_score += 1.5
    if flags.get("mass_missing_dims") or flags.get("mass_missing_deep_margin") or flags.get("missing_surgical_no"):
        risk_score += 0.5
    if avg_logprob is not None:
        risk_score += max(0.0, -float(avg_logprob))
    if min_word_prob is not None:
        risk_score += max(0.0, 1.0 - float(min_word_prob))

    return {
        "slot_acc_active11": round(slot_acc_active11, 4),
        "cer_case": is_crit_err,
        "crit_omissions": crit_omissions,
        "crit_commissions": crit_commissions,
        "unspoken_fp": unspoken_fp,
        "is_flagged": int(len(flags) > 0),
        "flag_reasons": ";".join(sorted(flags.keys())),
        "risk_score": round(risk_score, 4),
        "outcomes": outcomes,
    }


def compute_macro_f1_active11(outcomes_list: list[dict]) -> dict:
    """
    Computes per-field Precision, Recall, F1 and Macro-F1 across the 11 Active CAP Fields.
    """
    per_field = {}
    f1s, precs, recs = [], [], []
    for k in ACTIVE_KEYS:
        tp = sum(1 for o in outcomes_list if o[k] == "TP")
        fn = sum(1 for o in outcomes_list if o[k] == "FN")
        fp = sum(1 for o in outcomes_list if o[k] == "FP")
        wrong = sum(1 for o in outcomes_list if o[k] == "WRONG")
        # In slot filling, WRONG is both a false positive (wrong value filled) and false negative (true value missed)
        prec = 100.0 * tp / (tp + fp + wrong) if (tp + fp + wrong) > 0 else 100.0
        rec = 100.0 * tp / (tp + fn + wrong) if (tp + fn + wrong) > 0 else 100.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        per_field[k] = {"precision": round(prec, 2), "recall": round(rec, 2), "f1": round(f1, 2),
                        "tp": tp, "fn": fn, "fp": fp, "wrong": wrong}
        precs.append(prec)
        recs.append(rec)
        f1s.append(f1)
    return {
        "macro_precision": round(float(np.mean(precs)), 2),
        "macro_recall": round(float(np.mean(recs)), 2),
        "macro_f1": round(float(np.mean(f1s)), 2),
        "per_field": per_field,
    }
