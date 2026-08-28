import re
from src.nlp.normalizer import normalize_text

try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
except ImportError:
    print("WARNING: spacy is not installed. NLP fallback will be disabled.")
    nlp = None
except OSError:
    print("WARNING: en_core_web_sm model not found. NLP fallback will be disabled.")
    nlp = None

def format_section_code(code):
    code = re.sub(r"([a-zA-Z])\s+(\d+)", r"\1\2", code)
    code = re.sub(r"\b(?:to|and)\b", "-", code, flags=re.IGNORECASE)
    code = re.sub(r"\s+", "", code)
    return code.upper()

def extract_data_15_sections(text):
    t = normalize_text(text)
    data = {"_low_confidence": []}

    # 1. Surgical Number 
    m = re.search(r"(?:surgical number|specimen|s-)?\s*(?:is\s+)?([sS]?\s*-?\s*\d{2}\s*-?\s*\d+)", t, re.IGNORECASE)
    if m: 
        raw_s = m.group(1).replace(" ", "").upper()
        if not raw_s.startswith("S-"):
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

    if "modified radical" in t: data["s2_proc"] = "modified"
    elif "simple mastectomy" in t: data["s2_proc"] = "simple"
    else:
        m = re.search(r"\b(quadrantectomy|lumpectomy|wide excision|excisional biopsy|re-excision|segmentectomy)\b(?:\s+specimen)?", t, re.IGNORECASE)
        if not m:
            m = re.search(r"procedure\s+is\s+([a-zA-Z\s]+)", t, re.IGNORECASE)
        if m: 
            data["s2_proc"] = "other"
            data["s2_other_text"] = m.group(1).strip()
     
    # 3. Specimen Overall Dimensions (Measuring X x Y x Z cm) - Extracted FIRST!
    m_specs = list(re.finditer(r"(?:mastectomy|specimen|overall size|specimen size|total specimen|measuring|dimensions are)[\s\S]{0,60}?([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", t, re.IGNORECASE))
    if m_specs:
        m = m_specs[0] 
        data["s3_dims"] = [m.group(1).rstrip('.'), m.group(2).rstrip('.'), m.group(3).rstrip('.')]
        t = t[:m.start()] + " [SPECIMEN_DIMS] " + t[m.end():]
    else:
        generic_matches = list(re.finditer(r"(?<!-)(?<!\d)([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", t, re.IGNORECASE))
        if generic_matches:
            m = generic_matches[0]
            data["s3_dims"] = [m.group(1).rstrip('.'), m.group(2).rstrip('.'), m.group(3).rstrip('.')]
            t = t[:m.start()] + " [SPECIMEN_DIMS] " + t[m.end():]

    # 4. Lesions / Mass / Cavity (Section 10) - Extracted SECOND!
    mass_count = 0
    mass_types = []

    # 4A. Previous Surgical Cavity with Residual Mass (s10_prev2)
    if "previous surgical cavity" in t and ("residual" in t or "residual mass" in t):
        data["s10_prev2"] = True
        mass_count += 1
        mass_types.append("residual mass")
        
        m_cavity = re.search(r"(?:previous surgical cavity|adjacent fibrous tissue)[\s\S]{0,50}?([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", t, re.IGNORECASE)
        if m_cavity:
            data["s10_prev2_cavity_dims"] = [m_cavity.group(1).rstrip('.'), m_cavity.group(2).rstrip('.'), m_cavity.group(3).rstrip('.')]
            t = t[:m_cavity.start()] + " [PREV2_CAVITY_DIMS] " + t[m_cavity.end():]
            
        m_res = re.search(r"(?:residual mass|residual)[\s\S]{0,50}?([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", t, re.IGNORECASE)
        if m_res:
            data["s10_prev2_mass_dims"] = [m_res.group(1).rstrip('.'), m_res.group(2).rstrip('.'), m_res.group(3).rstrip('.')]
            t = t[:m_res.start()] + " [PREV2_MASS_DIMS] " + t[m_res.end():]

    # 4B. Previous Surgical Cavity without Residual Mass (s10_prev1)
    elif "previous surgical cavity" in t:
        data["s10_prev1"] = True
        mass_count += 1
        mass_types.append("previous cavity")
        m_cavity = re.search(r"(?:previous surgical cavity|adjacent fibrous tissue)[\s\S]{0,50}?([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", t, re.IGNORECASE)
        if m_cavity:
            data["s10_prev1_dims"] = [m_cavity.group(1).rstrip('.'), m_cavity.group(2).rstrip('.'), m_cavity.group(3).rstrip('.')]
            t = t[:m_cavity.start()] + " [PREV1_DIMS] " + t[m_cavity.end():]

    # 4C. Well-defined firm white mass with slit-like appearance (s10_well)
    elif "well defined" in t or "well-defined" in t or "slit like" in t or "slit-like" in t:
        data["s10_well"] = True
        mass_count += 1
        mass_types.append("well-defined mass")
        m_well = re.search(r"(?:well-defined|well defined|slit like|slit-like)[\s\S]{0,50}?([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", t, re.IGNORECASE)
        if m_well:
            data["s10_well_dims"] = [m_well.group(1).rstrip('.'), m_well.group(2).rstrip('.'), m_well.group(3).rstrip('.')]
            t = t[:m_well.start()] + " [WELL_DIMS] " + t[m_well.end():]

    # 4D. Infiltrative Mass (s10_infiltrative)
    elif "no discrete mass" in t or "entirely fibrocystic" in t:
        data["s10_infiltrative"] = False
    elif "infiltrative" in t or "mass" in t or "lesion" in t or "tumor" in t:
        data["s10_infiltrative"] = True
        mass_count += 1
        mass_types.append("infiltrative")
        
        all_3d_dims = list(re.finditer(r"([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", t))
        mass_dim_match = None
        
        for m in reversed(all_3d_dims):
            start, end = m.start(), m.end()
            pre_context = t[max(0, start-40) : start].lower()
            post_context = t[end : min(len(t), end+50)].lower()
            
            if "without dimension" in post_context or "no dimension" in post_context or "without dimension" in pre_context:
                continue
                
            if any(kw in pre_context for kw in ["mastectomy", "specimen", "overall size"]):
                continue

            if any(kw in pre_context for kw in ["infiltrative", "mass", "lesion", "tumor"]) or \
               (any(kw in post_context for kw in ["infiltrative", "mass", "lesion", "tumor"]) and "measuring" not in pre_context):
                mass_dim_match = m
                break
        
        if mass_dim_match:
            data["s10_inf_dims"] = [mass_dim_match.group(1).rstrip('.'), mass_dim_match.group(2).rstrip('.'), mass_dim_match.group(3).rstrip('.')]
            t = t[:mass_dim_match.start()] + " [MASS_DIMS] " + t[mass_dim_match.end():]

    if mass_count == 1:
        data["s10_grammar"] = "is an" if (mass_types and mass_types[0] == "infiltrative") else "is a"
              
    # 5. Axillary Content & Skin
    if "axillary content" in t or "axillary fat" in t or "with axillary" in t:
        data["s4_check"] = True
        m = re.search(r"axillary.*?\s+([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", t)
        if m: data["s4_dims"] = [m.group(1).rstrip('.'), m.group(2).rstrip('.'), m.group(3).rstrip('.')]

    m = re.search(r"skin.*?\s+([\d.]+)\s*x\s*([\d.]+)", t)
    if m: data["s5_dims"] = [m.group(1).rstrip('.'), m.group(2).rstrip('.')]

    skin_idx = t.find("skin")
    skin_context = t[max(0, skin_idx):skin_idx+80] if skin_idx != -1 else ""
    if "appears normal" in skin_context or re.search(r"skin.*normal", skin_context): 
        data["s5_appears_normal"] = True

    # 6. Scars & Nipple
    if "scar" in t:
        data["s6_check"] = True 
        m = re.search(r"scar\s+([\d.]+)\s*cm", t)
        if m: data["s7_len"] = m.group(1).rstrip('.')
        
    ulcer_match = re.search(r"ulceration", t)
    if ulcer_match:
        data["s8_check"] = True
        m = re.search(r"ulceration\s+([\d.]+)\s*x\s*([\d.]+)", t)
        if m: data["s8_dims"] = [m.group(1).rstrip('.'), m.group(2).rstrip('.')]

    s9_vals = []
    if "everted" in t: s9_vals.append("everted")
    if "inverted" in t: s9_vals.append("inverted")
    if "retracted" in t: s9_vals.append("retracted")
    if s9_vals: data["s9_val"] = s9_vals

    # 7. Quadrants & Other Locations (Section 10.5)
    tumor_loc_matches = list(re.finditer(r"(?:(?:in|at)\s+(?:the\s+)?)?(upper|lower|central)\s*(inner|outer)?\s*quadrant", t))
    if tumor_loc_matches:
        loc_text = tumor_loc_matches[-1].group(0)
        locs = []
        if "central" in loc_text: locs.append("central")
        else:
            if "upper" in loc_text: locs.append("upper")
            if "lower" in loc_text: locs.append("lower")
            if "inner" in loc_text: locs.append("inner")
            if "outer" in loc_text: locs.append("outer")
        if locs:
            data["s10_5_quadrant_check"] = True
            data["s10_5_quadrant_vals"] = locs
    else:
        other_loc_m = re.search(r"(?:located\s+(?:in|at)|tumor\s+is\s+in|location\s+is)\s+(?:the\s+)?(axillary\s+tail(?:\s+of\s+spence)?|retroareolar|subareolar|chest\s+wall|deep\s+fascia|[a-zA-Z\s]+?(?:region|plane|tail))", t, re.IGNORECASE)
        if other_loc_m:
            data["s10_5_other_check"] = True
            data["s10_5_other"] = other_loc_m.group(1).strip()

    # 8. Margins (Section 11)
    margins = ["deep", "superior", "inferior", "medial", "lateral", "skin"]
    for m_name in margins:
        regex = rf"([\d.]+)\s*cm\s*(?:from|at)?\s*{m_name}\s*margin"
        m = re.search(regex, t, re.IGNORECASE)
        if not m: regex = rf"{m_name}\s*margin\s*(?:is)?\s*([\d.]+)\s*cm"
        m = re.search(regex, t, re.IGNORECASE)
        if not m: regex = rf"([\d.]+)\s*cm\s*from\s*{m_name}"
        m = re.search(regex, t, re.IGNORECASE)
        if m: data[f"s11_{m_name}"] = m.group(1).rstrip('.')

    # 8.4 Fat to Fibrous Ratio (Section 12)
    ratio_match = re.search(r"(?:fat to fibrous|fat to fiber|parenchyma|ratio).*?(\d+)\s*(?::|to)\s*(\d+)", t, re.IGNORECASE)
    if ratio_match:
        data["s12_check"] = True
        data["s12_val_left"] = ratio_match.group(1)
        data["s12_val_right"] = ratio_match.group(2)

    # 8.5 Remaining Breast Tissue (Section 13)
    if "unremarkable" in t:
        data["s13_unremarkable"] = True
        data["s13_type"] = "unremarkable"
    else:
        rem_match = re.search(r"(?:remaining|other|adjacent|uninvolved|surrounding)\s+(?:of\s+)?(?:the\s+)?(?:breast\s+)?(?:tissue|specimen|parenchyma)\s+(?:shows|is|contains|with)?\s*([a-zA-Z\s,]+?)(?:\.|\n|there\s+are|representative|$)", t, re.IGNORECASE)
        if rem_match:
            desc = rem_match.group(1).strip()
            if desc and "unremarkable" not in desc:
                data["s13_type"] = "other"
                data["s13_text"] = desc

    # 9. Lymph Nodes (Section 14)
    if ("lymph node" in t or "nodes" in t or "ต่อมน้ำเหลือง" in t or "ต่อม" in t) and "not found" not in t and "no lymph" not in t:
        data["s14_check"] = True
        num_matches = list(re.finditer(r"(\d+)\s+(?:lymph\s+)?node", t)) or list(re.finditer(r"จำนวน\s*(\d+)", t)) or list(re.finditer(r"(\d+)\s*ต่อม", t))
        if num_matches:
            data["s14_num"] = num_matches[-1].group(1) 

        range_m = re.search(r"ranging\s+from\s+([\d.]+)\s*(?:cm\s*)?(?:to|-)\s*([\d.]+)\s*cm", t, re.IGNORECASE)
        if range_m:
            data["s14_min"] = range_m.group(1).rstrip('.')
            data["s14_max"] = range_m.group(2).rstrip('.')
        else:
            node_idx = t.rfind("node")
            if node_idx != -1:
                node_context = t[node_idx:]
                sizes = re.findall(r"\b(\d+(?:\.\d+)?)\b", node_context)
                if len(sizes) >= 2:
                    sizes_float = [float(s) for s in sizes]
                    data["s14_min"] = str(min(sizes_float))
                    data["s14_max"] = str(max(sizes_float))
    elif "not found" in t or "no lymph" in t:
        data["s14_check"] = False

    # 10. Sections Mapping
    section_map = {
        "= nipple": ["nipple"], 
        "= mass": ["mass"], 
        "= old biopsy cavity with fibrosis": ["fibrosis", "biopsy cavity", "old biopsy"], 
        "= deep resected margin": ["deep resected", "deep margin", "the resected"], 
        "= nearest resected margin": ["nearest resected", "nearest margin", "inferior resected", "superior resected"], 
        "= sampling upper inner quadrant": ["upper inner", "superior inner", "superior medial"], 
        "= sampling upper outer quadrant": ["upper outer", "superior outer", "superior lateral"], 
        "= sampling lower inner quadrant": ["lower inner", "inferior inner", "inferior medial"], 
        "= sampling lower outer quadrant": ["lower outer", "inferior outer", "inferior lateral"], 
        "= sampling central region": ["central"], 
        "= axillary lymph nodes": ["axillary"]
    }
    data["sections"] = {}
    
    for anchor, keywords in section_map.items():
        found = False
        for kw in keywords:
            pattern1 = rf"((?:[a-zA-Z]\s?-?\s?\d+(?:[-\s]?\d+)*(?:\s*(?:to|and|-|,)\s*)*)+)(?:\s*(?:=|equals?|is|-|old|sampling|submitted as|with))*\s*{kw}"
            pattern2 = rf"{kw}(?:\s*(?:=|equals?|is|-|old|sampling|submitted as|with))*\s*((?:[a-zA-Z]\s?-?\s?\d+(?:[-\s]?\d+)*(?:\s*(?:to|and|-|,)\s*)*)+)"
            
            for pat in [pattern1, pattern2]:
                m = re.search(pat, t)
                if m:
                    raw_code = m.group(1)
                    clean_code = re.sub(r"\b(old|is|sampling|with)\b", "", raw_code, flags=re.IGNORECASE).strip()
                    clean_code = clean_code.rstrip(".,")
                    formatted_code = format_section_code(clean_code)
                    
                    extra = ""
                    if "nearest" in anchor:
                        kw_end_idx = m.end()
                        following_text = t[kw_end_idx:kw_end_idx+40]
                        extra_m = re.search(r"(?:margin\s+)?(?:with\s+|,?\s*)(inferior|superior|medial|lateral|deep|anterior|posterior|skin)", following_text, re.IGNORECASE)
                        if extra_m:
                            extra = extra_m.group(1).strip()
                    
                    data["sections"][anchor] = {
                        "code": formatted_code,
                        "extra": extra
                    }
                    found = True
                    break
        if found: continue

    if nlp is not None:
        data = enhance_extraction_with_nlp(t, data)

    return data

def enhance_extraction_with_nlp(text, data):
    doc = nlp(text)
    if "s3_dims" not in data and "measuring" in text:
        dims = []
        for token in doc:
            if token.like_num or re.match(r'^(?=.*\d)[\d.]+$', token.text):
                dims.append(token.text)
                if len(dims) == 3: break
        if len(dims) == 3: data["s3_dims"] = dims
                
    margins_to_check = {
        "deep": "s11_deep", "superior": "s11_superior", "inferior": "s11_inferior", 
        "medial": "s11_medial", "lateral": "s11_lateral", "skin": "s11_skin"
    }
    for margin_word, key in margins_to_check.items():
        if key not in data:
            for token in doc:
                if margin_word in token.text.lower():
                    window_start = max(0, token.i - 5)
                    window_tokens = doc[window_start:token.i]
                    for w in window_tokens:
                        if w.like_num or re.match(r'^(?=.*\d)[\d.]+$', w.text):
                            data[key] = w.text
    return data

def generate_confidence_flags(extracted_data):
    flags = {}
    if not extracted_data.get("s0_surgical_no") or extracted_data.get("s0_surgical_no").strip() == "":
        flags["s0_surgical_no"] = True
    s3_dims = extracted_data.get("s3_dims", [])
    if not s3_dims or len(s3_dims) < 3 or not any(char.isdigit() for char in str(s3_dims)):
        flags["s3_dims"] = True
    has_mass = extracted_data.get("s10_infiltrative") or extracted_data.get("s10_well")
    if has_mass:
        inf_dims = extracted_data.get("s10_inf_dims", [])
        well_dims = extracted_data.get("s10_well_dims", [])
        if extracted_data.get("s10_infiltrative") and (not inf_dims or len(inf_dims) < 3):
            flags["mass_dimensions"] = True
        if extracted_data.get("s10_well") and (not well_dims or len(well_dims) < 3):
            flags["mass_dimensions"] = True
    return flags
