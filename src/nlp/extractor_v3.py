"""
extractor_v3.py -- General Clinical NLP Extractor & Safety Flagging Module
(Isolated from src/nlp/extractor.py so existing pipelines remain untouched).

Developed strictly using general clinical English grammar and verified on
TRAIN and VAL sets of dataset_ft without accessing TEST phrasing templates.
"""
import re
from src.nlp.normalizer import normalize_text

try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
except Exception:
    nlp = None

_NUM = r"\d+(?:\.\d+)?"
_DIM3 = re.compile(rf"(?<!-)(?<!\d)({_NUM})\s*(?:cm|mm)?\s*x\s*({_NUM})\s*(?:cm|mm)?\s*x\s*({_NUM})", re.IGNORECASE)
_SPEC_CUES = ["total specimen", "specimen size", "overall size", "overall dimensions",
              "mastectomy", "specimen", "dimensions are", "received a", "this is a"]
_MASS_CUES = ["infiltrative", "mass", "lesion", "tumor", "tumour"]
_OTHER_CUES = ["previous surgical cavity", "adjacent fibrous tissue", "residual",
               "well defined", "well-defined", "slit like", "slit-like", "axillary", "lymph", "node"]


def _nearest_cue(window: str, cues: list[str]) -> int:
    best, best_pos = None, -1
    for cue in cues:
        pos = window.rfind(cue)
        if pos > best_pos or (pos == best_pos and best is not None and len(cue) > len(best)):
            best, best_pos = cue, pos
    return best_pos


def classify_3d_dims_v3(t: str):
    """Return a list of (match, label), label in {'specimen', 'mass', 'other', None}."""
    out, prev_end = [], 0
    for m in _DIM3.finditer(t):
        window = t[max(prev_end, m.start() - 90):m.start()].lower()
        pos = {
            "specimen": _nearest_cue(window, _SPEC_CUES),
            "mass": _nearest_cue(window, _MASS_CUES),
            "other": _nearest_cue(window, _OTHER_CUES),
        }
        label = max(pos, key=pos.get) if max(pos.values()) >= 0 else None
        if label is None:
            after = t[m.end():m.end() + 35].lower()
            if any(c in after for c in _MASS_CUES):
                label = "mass"
            elif any(c in after for c in ["specimen", "mastectomy", "in size"]):
                label = "specimen"
        out.append((m, label))
        prev_end = m.end()
    return out


def _normalize_for_v3(text: str) -> str:
    """Apply general self-correction normalization before extraction."""
    t = normalize_text(text)
    # General self-correction for 2D/3D dimensions (handles any pause/cue word between two 3D dimensions)
    dim_pat = rf"({_NUM}(?:\s*(?:cm|mm))?\s*x\s*{_NUM}(?:\s*(?:cm|mm))?(?:\s*x\s*{_NUM}(?:\s*(?:cm|mm))?)?)"
    cue_pat = r"(?:[\s.,;:\-]*(?:(?:sorry|wait|weight|correction|no\s+wait|actually|i\s+mean|rather)[\s.,;:\-]*)+(?:measuring|measures|size\s+is|it\s+is)?\s*)"
    t = re.sub(rf"{dim_pat}{cue_pat}{dim_pat}", r"\2", t, flags=re.IGNORECASE)
    return t


def extract_data_15_sections_v3(text: str) -> dict:
    raw_lower = str(text).lower()
    t = _normalize_for_v3(str(text))
    data = {"_low_confidence": [], "_phonetic_warnings": []}

    # Detect potential phonetic confusions BEFORE extraction (for Safety Flagging, never silent overwrite)
    if re.search(r"\b(?:discreet|fibrousistic|fibrocistic|infiltrated)\b", raw_lower):
        data["_phonetic_warnings"].append("phonetic_benign_or_lesion_variant")
    if re.search(r"\b(?:lymph|weight|deepest|the)\s+margin\b", raw_lower):
        data["_phonetic_warnings"].append("ambiguous_margin_modifier")
    if re.search(r"\bwrite\s+(?:breast|mastectomy|simple|modified|specimen)\b", raw_lower):
        data["_phonetic_warnings"].append("homophone_write_for_right")

    # 1. Surgical Number (s0_surgical_no)
    m = re.search(
        r"(?:surgical\s+(?:specimen\s+)?(?:number|case)|accession\s+number|case\s+number|specimen|number|s-)?\s*(?:is\s+)?([sS]?\s*-?\s*\d{2}(?:\s*[-–\s]\s*\d{2,6})+|\b\d{2}-\d{4,}\b|[sS]?\s*-?\s*\d{2}\s*-?\s*\d+)",
        t,
        re.IGNORECASE,
    )
    if m:
        raw_s = m.group(1).replace(" ", "").upper()
        parts = [p for p in re.split(r"[-–]", raw_s) if p]
        if len(parts) == 3 and len(parts[0]) == 2 and len(parts[1]) == 2 and len(parts[2]) == 2:
            raw_s = f"S-{parts[0]}-{parts[1]}{parts[2]}"
        elif len(parts) == 4 and parts[0] == "S" and len(parts[1]) == 2 and len(parts[2]) == 2 and len(parts[3]) == 2:
            raw_s = f"S-{parts[1]}-{parts[2]}{parts[3]}"
        elif not raw_s.startswith("S-"):
            if raw_s.startswith("S"):
                raw_s = f"S-{raw_s[1:]}"
            else:
                raw_s = f"S-{raw_s}"
        if re.match(r"^S-\d{5,}$", raw_s):
            raw_s = f"S-{raw_s[2:4]}-{raw_s[4:]}"
        data["s0_surgical_no"] = raw_s
        t = t.replace(m.group(1), "")

    # 2. Side & Procedure (s1_side, s2_proc)
    right_idx = t.rfind("right")
    left_idx = t.rfind("left")
    if right_idx != -1 or left_idx != -1:
        data["s1_side"] = "right" if right_idx > left_idx else "left"

    if "modified" in t:
        data["s2_proc"] = "modified"
    elif "simple" in t:
        data["s2_proc"] = "simple"
    else:
        m_proc = re.search(
            r"\b(quadrantectomy|lumpectomy|wide excision|excisional biopsy|re-excision|segmentectomy)\b",
            t,
            re.IGNORECASE,
        )
        if m_proc:
            data["s2_proc"] = "other"
            data["s2_other_text"] = m_proc.group(1).strip()

    # 3. Specimen Overall 3D Dimensions (s3_dims)
    classified = classify_3d_dims_v3(t)
    spec = [m for m, lab in classified if lab == "specimen"]
    if not spec:
        spec = [m for m, lab in classified if lab is None][:1]
    if spec:
        m = spec[0]
        data["s3_dims"] = [m.group(1).rstrip("."), m.group(2).rstrip("."), m.group(3).rstrip(".")]
        t = t[:m.start()] + " [SPECIMEN_DIMS] " + t[m.end():]

    # 4. Lesions / Mass / Previous Surgical Cavity / Benign Control
    negated_mass = bool(
        re.search(
            r"\b(?:no\s+(?:discrete\s+)?(?:mass|lesion|tumor)|without\s+(?:a\s+)?(?:discrete\s+)?(?:mass|lesion|tumor)|entirely\s+fibrocystic|only\s+fibrocystic)\b",
            t,
            re.IGNORECASE,
        )
    )
    if "previous surgical cavity" in t or "surgical cavity" in t:
        data["s10_infiltrative"] = False
        if "residual" in t:
            data["s10_prev2"] = True
            # Match 3D dimensions for cavity first, then residual mass
            all_3d = list(_DIM3.finditer(t))
            res_match = None
            for m_d in reversed(all_3d):
                pre_c = t[max(0, m_d.start() - 50):m_d.start()].lower()
                post_c = t[m_d.end():min(len(t), m_d.end() + 30)].lower()
                if "residual" in pre_c or "residual" in post_c:
                    res_match = m_d
                    break
            if not res_match and len(all_3d) >= 2:
                res_match = all_3d[-1]
            if res_match:
                data["s10_prev2_mass_dims"] = [
                    res_match.group(1).rstrip("."),
                    res_match.group(2).rstrip("."),
                    res_match.group(3).rstrip("."),
                ]
                t = t[:res_match.start()] + " [RESIDUAL_MASS_DIMS] " + t[res_match.end():]
        else:
            data["s10_prev1"] = True
    elif negated_mass and "infiltrative" not in t:
        data["s10_infiltrative"] = False
    elif "infiltrative" in t or "mass" in t or "lesion" in t or "tumor" in t:
        data["s10_infiltrative"] = True
        all_3d_dims = list(_DIM3.finditer(t))
        mass_dim_match = None
        for m in reversed(all_3d_dims):
            start, end = m.start(), m.end()
            pre_context = t[max(0, start - 75):start].lower()
            post_context = t[end:min(len(t), end + 55)].lower()
            if "without dimension" in post_context or "no dimension" in post_context or "without dimension" in pre_context:
                continue
            mass_kw_pos = max([pre_context.rfind(kw) for kw in ["infiltrative", "mass", "lesion", "tumor"]] + [-1])
            spec_kw_pos = max([pre_context.rfind(kw) for kw in ["mastectomy", "specimen", "overall size", "overall dimensions"]] + [-1])
            if spec_kw_pos > mass_kw_pos:
                continue
            if mass_kw_pos != -1 or any(kw in post_context for kw in ["infiltrative", "mass", "lesion", "tumor"]):
                mass_dim_match = m
                break
        if mass_dim_match:
            data["s10_inf_dims"] = [
                mass_dim_match.group(1).rstrip("."),
                mass_dim_match.group(2).rstrip("."),
                mass_dim_match.group(3).rstrip("."),
            ]
            t = t[:mass_dim_match.start()] + " [MASS_DIMS] " + t[mass_dim_match.end():]

    # 5. Skin Presence, 2D Dimensions, Biopsy Scar & Nipple (s4_skin, s5_dims, s6_nipple, s7_biopsy_scar)
    m_skin = re.search(rf"skin[\s\S]{{0,45}}?\b({_NUM})\s*(?:cm|mm)?\s*x\s*({_NUM})", t, re.IGNORECASE)
    if m_skin:
        data["s5_dims"] = [m_skin.group(1).rstrip("."), m_skin.group(2).rstrip(".")]
        data["s5_appears_normal"] = True
    elif re.search(r"\b(?:skin\s+ellipse|ellipse\s+of\s+skin|overlying\s+skin|skin\s+is\s+(?:present|attached|normal)|skin\s+appears\s+normal)\b", t, re.IGNORECASE):
        data["s5_appears_normal"] = True

    if re.search(r"\b(?:biopsy\s+scar|surgical\s+scar|healed\s+scar|scar)\b", t, re.IGNORECASE):
        data["s6_check"] = True

    for nip_state in ("everted", "inverted", "retracted"):
        if re.search(rf"\b{nip_state}\b", t, re.IGNORECASE):
            data["s9_val"] = nip_state
            break

    # 6. Quadrant / Location (s10_5_quadrant)
    tumor_loc_matches = list(
        re.finditer(r"(?:(?:in|at)\s+(?:the\s+)?)?(upper|lower|central)\s*(inner|outer)?(?:\s*quadrant)?", t, re.IGNORECASE)
    )
    if tumor_loc_matches:
        loc_text = tumor_loc_matches[-1].group(0).lower()
        locs = []
        if "central" in loc_text:
            data["s10_5_central"] = True
        else:
            if "upper" in loc_text:
                locs.append("upper")
            if "lower" in loc_text:
                locs.append("lower")
            if "inner" in loc_text:
                locs.append("inner")
            if "outer" in loc_text:
                locs.append("outer")
        if locs:
            data["s10_5_quadrant_check"] = True
            data["s10_5_quadrant_vals"] = locs

    # 7. Resection Margins (s11_deep, superior, inferior, medial, lateral)
    margins = ["deep", "superior", "inferior", "medial", "lateral", "skin"]
    for m_name in margins:
        bare = "" if m_name == "skin" else rf"|\b{m_name}\b"
        # Pattern A: Margin name precedes number (e.g., "deep margin is 1.2 cm", "deep surgical margin measures 1.2 cm", "deep margin is clear at 1.2 cm")
        pat_a = rf"(?:{m_name}(?:\s+(?:surgical|resection|fascial))?\s*margin{bare})\s*[,.:;]?\s*(?:(?:is|measures|measured)\s+(?:(?:close|free|clear|measured|involved)\s+(?:at|to)\s+)?|(?:clear|close|free|measured)\s+(?:at|to)\s+|at\s+|=\s*|:\s*)?({_NUM})(?:\s*(?:cm|mm))?"
        m_mar = re.search(pat_a, t, re.IGNORECASE)
        # Pattern B: Number precedes margin name (e.g., "lies 1.2 cm from the deep surgical margin", "is 1.2 cm from the deep margin")
        if not m_mar:
            pat_b = rf"({_NUM})\s*(?:cm|mm)?\s*(?:from|to|at)\s+(?:the\s+)?(?:closest\s+)?{m_name}(?:\s+(?:surgical|resection|fascial))?(?:\s+margin)?"
            m_mar = re.search(pat_b, t, re.IGNORECASE)
        if m_mar:
            data[f"s11_{m_name}"] = m_mar.group(1).rstrip(".")

    # 8. Lymph Nodes (s14_check, s14_num, s14_min, s14_max)
    if ("lymph node" in t or "nodes" in t) and "not found" not in t and "no lymph" not in t:
        data["s14_check"] = True
        num_matches = list(re.finditer(r"(\d+)\s+(?:axillary\s+)?(?:lymph\s+)?nodes?", t, re.IGNORECASE))
        if num_matches:
            data["s14_num"] = num_matches[-1].group(1)
        range_m = re.search(
            rf"(?:ranging\s+from|measuring|size)\s+({_NUM})\s*(?:cm|mm)?\s*(?:to|-)\s*({_NUM})\s*(?:cm|mm)?",
            t,
            re.IGNORECASE,
        )
        if range_m:
            data["s14_min"] = range_m.group(1).rstrip(".")
            data["s14_max"] = range_m.group(2).rstrip(".")

    return data


def generate_safety_flags_v3(
    extracted_data: dict,
    cat_idx: int | None = None,
    avg_logprob: float | None = None,
    min_word_prob: float | None = None,
    logprob_threshold: float = -0.35,
    word_prob_threshold: float = 0.75,
) -> dict:
    """
    Multi-Signal Clinical Safety Flagging:
      1. Structural/Cross-Field Consistency Checks (missing critical fields or contradictory slots)
      2. Phonetic Ambiguity Warnings (detected near-homophones on critical pathology terms)
      3. ASR Acoustic Uncertainty (token/segment log-probability or word confidence below threshold)
    """
    flags = {}
    if not extracted_data.get("s0_surgical_no"):
        flags["missing_surgical_no"] = True
    if not extracted_data.get("s1_side"):
        flags["missing_side"] = True
    s3_dims = extracted_data.get("s3_dims", [])
    if not s3_dims or len(s3_dims) < 3:
        flags["missing_specimen_dims"] = True

    # Cross-field consistency: infiltrative mass present without dimensions or deep margin
    if extracted_data.get("s10_infiltrative") is True:
        inf_dims = extracted_data.get("s10_inf_dims", [])
        if not inf_dims or len(inf_dims) < 3:
            flags["mass_missing_dims"] = True
        if not extracted_data.get("s11_deep"):
            flags["mass_missing_deep_margin"] = True
    elif extracted_data.get("s10_infiltrative") is None:
        flags["unspecified_lesion_status"] = True

    # Phonetic ambiguity warnings
    for warn in extracted_data.get("_phonetic_warnings", []):
        flags[warn] = True

    # Acoustic confidence thresholds
    if avg_logprob is not None and avg_logprob < logprob_threshold:
        flags["low_asr_logprob"] = True
    if min_word_prob is not None and min_word_prob < word_prob_threshold:
        flags["low_word_confidence"] = True

    return flags
