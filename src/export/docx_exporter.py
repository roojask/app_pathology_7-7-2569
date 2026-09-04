import docx
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from io import BytesIO
import datetime
from pathlib import Path
from typing import Dict, Any, List

from configs.config import Config


def normalize_report_dict(source: Any) -> Dict[str, Any]:
    """
    Normalizes form data whether it originates from Flask request.form,
    a python dictionary, or JSON loaded from PostgreSQL FormHistory.
    """
    if source is None:
        source = {}

    def get_val(k: str, default: str = "") -> str:
        v = source.get(k)
        if v is None:
            return default
        return str(v).strip()

    def get_bool(k: str) -> bool:
        v = source.get(k)
        return v in [True, "true", "True", "1", 1, "on"]

    def get_list(k: str) -> List[str]:
        if hasattr(source, "getlist"):
            vals = source.getlist(k)
            if vals:
                return [str(x).strip() for x in vals if str(x).strip()]
        val = source.get(k)
        if isinstance(val, list):
            return [str(x).strip() for x in val if str(x).strip()]
        if val:
            return [str(val).strip()]
        return []

    def get_dims(k: str, count: int = 3) -> List[str]:
        if k in source and isinstance(source[k], list):
            return [str(x).strip() for x in source[k] if str(x).strip()]
        dims = []
        for i in range(count):
            d = source.get(f"{k}_{i}")
            if d is not None and str(d).strip():
                dims.append(str(d).strip())
        return dims

    data = {
        "s0_surgical_no": get_val("s0_surgical_no"),
        "s1_side": get_val("s1_side"),
        "s2_proc": get_val("s2_proc"),
        "s2_other_text": get_val("s2_other_text"),
        "s3_dims": get_dims("s3_dims", 3),
        "s4_check": get_bool("s4_check"),
        "s4_dims": get_dims("s4_dims", 3),
        "s5_dims": get_dims("s5_dims", 2),
        "s5_appears_normal": get_bool("s5_appears_normal"),
        "s6_check": get_bool("s6_check"),
        "s7_len": get_val("s7_len"),
        "s7_locs": get_list("s7_locs"),
        "s8_check": get_bool("s8_check"),
        "s8_dims": get_dims("s8_dims", 2),
        "s8_locs": get_list("s8_locs"),
        "s9_val": get_list("s9_val"),
        "s9_ulcer_text": get_val("s9_ulcer_text"),
        "s10_grammar": get_val("s10_grammar", "is a"),
        "s10_infiltrative": get_bool("s10_infiltrative"),
        "s10_inf_dims": get_dims("s10_inf_dims", 3),
        "s10_well": get_bool("s10_well"),
        "s10_well_dims": get_dims("s10_well_dims", 3),
        "s10_prev1": get_bool("s10_prev1"),
        "s10_prev1_dims": get_dims("s10_prev1_dims", 3),
        "s10_prev2": get_bool("s10_prev2"),
        "s10_prev2_cavity_dims": get_dims("s10_prev2_cavity_dims", 3),
        "s10_prev2_mass_dims": get_dims("s10_prev2_mass_dims", 3),
        "s10_5_nipple": get_bool("s10_5_nipple"),
        "s10_5_scar": get_bool("s10_5_scar"),
        "s10_5_central": get_bool("s10_5_central"),
        "s10_5_quadrant_check": get_bool("s10_5_quadrant_check"),
        "s10_5_quadrant_vals": get_list("s10_5_quadrant_vals"),
        "s10_5_other_check": get_bool("s10_5_other_check"),
        "s10_5_other": get_val("s10_5_other"),
        "s11_deep": get_val("s11_deep"),
        "s11_superior": get_val("s11_superior"),
        "s11_inferior": get_val("s11_inferior"),
        "s11_medial": get_val("s11_medial"),
        "s11_lateral": get_val("s11_lateral"),
        "s11_skin": get_val("s11_skin"),
        "s12_check": get_bool("s12_check"),
        "s12_val_left": get_val("s12_val_left"),
        "s12_val_right": get_val("s12_val_right"),
        "s13_unremarkable": get_bool("s13_unremarkable") or get_val("s13_type") == "unremarkable",
        "s13_type": get_val("s13_type"),
        "s13_text": get_val("s13_text"),
        "s14_check": get_bool("s14_check"),
        "s14_min": get_val("s14_min"),
        "s14_max": get_val("s14_max"),
        "footer_prosecutor": get_val("footer_prosecutor"),
        "footer_date": get_val("footer_date"),
    }

    # Handle sections mapping
    raw_sections = source.get("sections")
    sections_dict = {}
    section_keys = [
        ("sec_nipple", "= nipple"),
        ("sec_mass", "= mass"),
        ("sec_old_biopsy", "= old biopsy cavity with fibrosis"),
        ("sec_deep_margin", "= deep resected margin"),
        ("sec_nearest_margin", "= nearest resected margin"),
        ("sec_upper_inner", "= sampling upper inner quadrant"),
        ("sec_upper_outer", "= sampling upper outer quadrant"),
        ("sec_lower_inner", "= sampling lower inner quadrant"),
        ("sec_lower_outer", "= sampling lower outer quadrant"),
        ("sec_central", "= sampling central region"),
        ("sec_axillary", "= axillary lymph nodes")
    ]

    for form_k, label in section_keys:
        if isinstance(raw_sections, dict) and label in raw_sections:
            item = raw_sections[label]
            if isinstance(item, dict):
                sections_dict[label] = {
                    "code": str(item.get("code", "")).strip(),
                    "extra": str(item.get("extra", "")).strip()
                }
            else:
                sections_dict[label] = {"code": str(item).strip(), "extra": ""}
        else:
            code = get_val(form_k)
            extra = ""
            if "nearest" in label or "deep" in label:
                extra_k = form_k.replace("sec_", "sec_extra_")
                extra = get_val(extra_k)
            sections_dict[label] = {"code": code, "extra": extra}

    data["sections"] = sections_dict
    return data


def populate_template_doc(doc: docx.Document, data: Dict[str, Any]):
    """
    Populates data into Breast_Gross_Template.docx matching the official pathology form layout.
    """
    p = doc.paragraphs
    FONT_NAME = "Arial"
    BODY_SIZE = Pt(9)

    # Helper to add standard body run
    def add_run(para, text, bold=False, size=BODY_SIZE):
        r = para.add_run(text)
        r.font.name = FONT_NAME
        r.font.size = size
        r.bold = bold
        return r

    # 0. Header: Surgical Number S.............................................
    s_val = data.get("s0_surgical_no", "").strip()
    for pfx in ["Surgical Number:", "Surgical Number", "S-", "S -", "S ", "s-", "s "]:
        if s_val.startswith(pfx):
            s_val = s_val[len(pfx):].strip()
    p[0].text = ""
    if s_val:
        add_run(p[0], "Surgical Number S", bold=True, size=Pt(10))
        add_run(p[0], f". {s_val}  ", bold=True, size=Pt(10.5))
    else:
        add_run(p[0], "Surgical Number S.............................................  ", bold=True, size=Pt(10))
    p[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT

    # 1. Document Title: Breast gross 1
    p[1].text = ""
    add_run(p[1], "Breast gross 1", bold=True, size=Pt(15))
    p[1].alignment = WD_ALIGN_PARAGRAPH.CENTER

    # 2. Side and Procedure (Modified)
    side = data.get("s1_side", "").lower().strip()
    if side == "right":
        side_str = "( ☑ right / ☐ left )"
    elif side == "left":
        side_str = "( ☐ right / ☑ left )"
    else:
        side_str = "( right / left )"
    mod_chk = "☑" if data.get("s2_proc") == "modified" else "☐"

    p[2].text = ""
    add_run(p[2], "Received in formalin  is  a  ", bold=True)
    add_run(p[2], f"{side_str}\t{mod_chk}    modified radical mastectomy specimen")

    # 3. Simple mastectomy and Other text
    simp_chk = "☑" if data.get("s2_proc") == "simple" else "☐"
    oth_chk = "☑" if (data.get("s2_proc") == "other" or data.get("s2_other_text")) else "☐"
    oth_txt = data.get("s2_other_text", "").strip()

    p[3].text = ""
    add_run(p[3], f"          {simp_chk} simple mastectomy specimen       \t{oth_chk}    ")
    if oth_txt:
        add_run(p[3], oth_txt, bold=True)
    else:
        add_run(p[3], "…………………………………………………………………………………………….")

    # 4. Specimen Dimensions and Axillary content
    s3_dims = data.get("s3_dims", [])
    s4_dims = data.get("s4_dims", [])
    has_ax = data.get("s4_check") or bool(s4_dims)
    ax_chk = "☑" if has_ax else "☐"

    p[4].text = ""
    add_run(p[4], "            Measuring  ", bold=True)
    if s3_dims:
        d0 = s3_dims[0] if len(s3_dims) > 0 else "............."
        d1 = s3_dims[1] if len(s3_dims) > 1 else "............."
        d2 = s3_dims[2] if len(s3_dims) > 2 else "............."
        add_run(p[4], f" {d0} x {d1} x {d2} cm.", bold=True)
    else:
        add_run(p[4], "............. x ............. x ............. cm.")

    add_run(p[4], f"    {ax_chk}    with axillary content , ")
    if s4_dims:
        ad0 = s4_dims[0] if len(s4_dims) > 0 else "............."
        ad1 = s4_dims[1] if len(s4_dims) > 1 else "............."
        ad2 = s4_dims[2] if len(s4_dims) > 2 else "............."
        add_run(p[4], f" {ad0} x {ad1} x {ad2} cm.", bold=True)
    else:
        add_run(p[4], "............. x ............. x ............. cm.")

    # 5. Skin ellipse and appears normal
    s5_dims = data.get("s5_dims", [])
    app_norm = "☑" if data.get("s5_appears_normal") else "☐"

    p[5].text = ""
    add_run(p[5], "The skin ellipse ,    ", bold=True)
    if s5_dims:
        sd0 = s5_dims[0] if len(s5_dims) > 0 else "............."
        sd1 = s5_dims[1] if len(s5_dims) > 1 else "............."
        add_run(p[5], f" {sd0} x {sd1} cm.", bold=True)
    else:
        add_run(p[5], "............. x ............. cm.")
    add_run(p[5], f"  and    {app_norm}  appears normal…………………………………………………………………….")

    # 6. Surgical Scar
    has_scar = data.get("s6_check") or bool(data.get("s7_len")) or bool(data.get("s7_locs"))
    scar_chk = "☑" if has_scar else "☐"
    s_len = data.get("s7_len", "").strip()
    s_locs = [l.lower() for l in data.get("s7_locs", [])]
    formatted_sl = []
    for opt in ["areola", "upper", "lower", "inner", "outer"]:
        if opt in s_locs:
            formatted_sl.append(f"☑ {opt}")
        else:
            formatted_sl.append(opt)
    sl_joined = " / ".join(formatted_sl)

    p[6].text = ""
    add_run(p[6], f"{scar_chk} shows an old surgical scar ")
    if s_len:
        add_run(p[6], f" {s_len} ", bold=True)
    else:
        add_run(p[6], ".................")
    add_run(p[6], f" cm in length at ( {sl_joined} )  ( quadrant ).")

    # 7. Ulceration
    has_ulc = data.get("s8_check") or bool(data.get("s8_dims")) or bool(data.get("s8_locs"))
    ulc_chk = "☑" if has_ulc else "☐"
    u_dims = data.get("s8_dims", [])
    u_locs = [l.lower() for l in data.get("s8_locs", [])]
    formatted_ul = []
    for opt in ["areola", "upper", "lower", "inner", "outer"]:
        if opt in u_locs:
            formatted_ul.append(f"☑ {opt}")
        else:
            formatted_ul.append(opt)
    ul_joined = " / ".join(formatted_ul)

    p[7].text = ""
    add_run(p[7], f"{ulc_chk} shows an ulceration ")
    if u_dims:
        ud0 = u_dims[0] if len(u_dims) > 0 else "................"
        ud1 = u_dims[1] if len(u_dims) > 1 else "................"
        add_run(p[7], f" {ud0} x {ud1} ", bold=True)
    else:
        add_run(p[7], "................ x ................ ")
    add_run(p[7], f"cm .   at ( {ul_joined} ) ( quadrant ).")

    # 8. Nipple
    n_vals = data.get("s9_val", [])
    if isinstance(n_vals, str):
        n_vals = [n_vals]
    ev_chk = "☑" if "everted" in n_vals else "☐"
    inv_chk = "☑" if "inverted" in n_vals else "☐"
    has_ulc_nip = "ulceration" in n_vals or bool(data.get("s9_ulcer_text"))
    ulc_nip_chk = "☑" if has_ulc_nip else "☐"
    u_txt = data.get("s9_ulcer_text", "").strip()

    p[8].text = ""
    add_run(p[8], "The nipple    ", bold=True)
    add_run(p[8], f"{ev_chk}  is everted .  {inv_chk}  shows inverted .   {ulc_nip_chk}   shows ulceration ")
    if u_txt:
        add_run(p[8], u_txt, bold=True)
    else:
        add_run(p[8], "....................................")

    # 9. Grammar / Quantifier
    grammar_val = data.get("s10_grammar", "").strip().lower()
    formatted_g = []
    for opt in ["is a", "is an", "are two", "are multiple"]:
        if opt == grammar_val:
            formatted_g.append(f"☑ {opt}")
        else:
            formatted_g.append(opt)
    g_joined = " / ".join(formatted_g)

    p[9].text = ""
    add_run(p[9], "There  ( ", bold=True)
    add_run(p[9], f"{g_joined} ) …………………………………………………………………………………………………")

    # 10. Infiltrative Mass
    is_inf = data.get("s10_infiltrative")
    chk_inf = "☑" if is_inf else "☐"
    inf_dims = data.get("s10_inf_dims", [])

    p[10].text = ""
    add_run(p[10], f"{chk_inf} infiltrative  firm  yellow  white  mass ,    ")
    if inf_dims:
        d0 = inf_dims[0] if len(inf_dims) > 0 else "…………."
        d1 = inf_dims[1] if len(inf_dims) > 1 else "…………."
        d2 = inf_dims[2] if len(inf_dims) > 2 else "…………."
        add_run(p[10], f" {d0} x {d1} x {d2} cm.", bold=True)
    else:
        add_run(p[10], "…………. x …………. x …………. cm.")

    # 11. Well-defined Mass
    is_well = data.get("s10_well")
    chk_well = "☑" if is_well else "☐"
    well_dims = data.get("s10_well_dims", [])

    p[11].text = ""
    add_run(p[11], f"{chk_well} well – defined  firm  white  mass  with  slit  like  appearance ,    ")
    if well_dims:
        d0 = well_dims[0] if len(well_dims) > 0 else "…………."
        d1 = well_dims[1] if len(well_dims) > 1 else "…………."
        d2 = well_dims[2] if len(well_dims) > 2 else "…………."
        add_run(p[11], f" {d0} x {d1} x {d2} cm.", bold=True)
    else:
        add_run(p[11], "…………. x …………. x …………. cm.")

    # 12. Previous surgical cavity
    is_prev1 = data.get("s10_prev1")
    chk_prev1 = "☑" if is_prev1 else "☐"
    prev1_dims = data.get("s10_prev1_dims", [])

    p[12].text = ""
    add_run(p[12], f"{chk_prev1} previous  surgical  cavity  with  adjacent  fibrous  tissue ,    ")
    if prev1_dims:
        d0 = prev1_dims[0] if len(prev1_dims) > 0 else "…………."
        d1 = prev1_dims[1] if len(prev1_dims) > 1 else "…………."
        d2 = prev1_dims[2] if len(prev1_dims) > 2 else "…………."
        add_run(p[12], f" {d0} x {d1} x {d2} cm.", bold=True)
    else:
        add_run(p[12], "…………. x …………. x …………. cm.")

    # 13. Previous cavity with residual mass
    is_prev2 = data.get("s10_prev2")
    chk_prev2 = "☑" if is_prev2 else "☐"
    c_dims = data.get("s10_prev2_cavity_dims", [])
    m_dims = data.get("s10_prev2_mass_dims", [])

    p[13].text = ""
    add_run(p[13], f"{chk_prev2} previous  surgical  cavity  with  adjacent  fibrous  tissue ,    ")
    if c_dims:
        cd0 = c_dims[0] if len(c_dims) > 0 else "…………."
        cd1 = c_dims[1] if len(c_dims) > 1 else "…………."
        cd2 = c_dims[2] if len(c_dims) > 2 else "…………."
        add_run(p[13], f" {cd0} x {cd1} x {cd2} cm. ", bold=True)
    else:
        add_run(p[13], "…………. x …………. x …………. cm. ")
    add_run(p[13], "  and   a   firm   yellow   white residual mass ,   ")
    if m_dims:
        md0 = m_dims[0] if len(m_dims) > 0 else "…………."
        md1 = m_dims[1] if len(m_dims) > 1 else "…………."
        md2 = m_dims[2] if len(m_dims) > 2 else "…………."
        add_run(p[13], f" {md0} x {md1} x {md2} cm.", bold=True)
    else:
        add_run(p[13], "…………. x …………. x …………. cm.")

    # 14. Tumor location checkboxes
    nip_chk = "☑" if data.get("s10_5_nipple") else "☐"
    scar_chk = "☑" if data.get("s10_5_scar") else "☐"
    cent_chk = "☑" if data.get("s10_5_central") else "☐"

    p[14].text = ""
    add_run(p[14], "located    ", bold=True)
    add_run(p[14], f"{nip_chk}   beneath the nipple .   {scar_chk} beneath the scar .   {cent_chk} in the central portion ( subareola ) .")

    # 15. Tumor location quadrant / other
    q_chk = "☑" if (data.get("s10_5_quadrant_check") or bool(data.get("s10_5_quadrant_vals"))) else "☐"
    q_vals = [q.lower() for q in data.get("s10_5_quadrant_vals", [])]
    formatted_q = []
    for opt in ["upper", "lower", "inner", "outer"]:
        if opt in q_vals:
            formatted_q.append(f"☑ {opt}")
        else:
            formatted_q.append(opt)
    q_joined = " / ".join(formatted_q)

    other_chk = "☑" if (data.get("s10_5_other_check") or bool(data.get("s10_5_other"))) else "☐"
    other_txt = data.get("s10_5_other", "").strip()

    p[15].text = ""
    add_run(p[15], f"           {q_chk}   in ( {q_joined} )  quadrant .       {other_chk}    ")
    if other_txt:
        add_run(p[15], other_txt, bold=True)
    else:
        add_run(p[15], "……………………………………………………………………")

    # 16. Header: Tumor is located
    p[16].text = ""
    add_run(p[16], " Tumor is located   ", bold=True)

    # Table 0: Resection Margins (3 rows x 2 cols)
    t = doc.tables[0]

    def format_margin_cell(cell, prefix, val, suffix):
        cell.paragraphs[0].text = ""
        p_cell = cell.paragraphs[0]
        if val:
            if prefix:
                add_run(p_cell, prefix)
            add_run(p_cell, f" {val} ", bold=True)
            if suffix:
                add_run(p_cell, suffix)
        else:
            full_txt = f"{prefix}.................................... {suffix}".strip()
            add_run(p_cell, full_txt)

    format_margin_cell(t.rows[0].cells[0], "", data.get("s11_deep"), "cm. from deep margin ,")
    format_margin_cell(t.rows[0].cells[1], "", data.get("s11_superior"), "cm. from superior margin ,")
    format_margin_cell(t.rows[1].cells[0], "", data.get("s11_inferior"), "cm. from inferior margin ,")
    format_margin_cell(t.rows[1].cells[1], "", data.get("s11_medial"), "cm. from medial margin ,")
    format_margin_cell(t.rows[2].cells[0], "", data.get("s11_lateral"), "cm. from lateral margin ,")
    format_margin_cell(t.rows[2].cells[1], "and ", data.get("s11_skin"), "cm. from skin .")

    # 17. Uninvolved breast parenchyma ratio
    v_left = data.get("s12_val_left", "").strip()
    v_right = data.get("s12_val_right", "").strip()
    chk_par = "☑" if (data.get("s12_check") or bool(v_left) or bool(v_right)) else "☐"

    p[17].text = ""
    add_run(p[17], f"{chk_par}  The uninvolved breast parenchyma has a fat to fibrous tissue ratio of approximately  ")
    if v_left or v_right:
        add_run(p[17], f" {v_left} ", bold=True)
        add_run(p[17], " : ")
        add_run(p[17], f" {v_right} .", bold=True)
    else:
        add_run(p[17], "             :             .")

    # 18. Remaining breast tissue
    p[18].text = ""
    add_run(p[18], "The remaining of breast tissue   ", bold=True)
    if data.get("s13_unremarkable"):
        add_run(p[18], "☑  is unremarkable .  ☐ .....................................................................................................................")
    elif data.get("s13_text"):
        add_run(p[18], "☐  is unremarkable .  ☑ ")
        add_run(p[18], f" {data['s13_text']}", bold=True)
    else:
        add_run(p[18], "☑  is unremarkable .  ☐ .....................................................................................................................")

    # 19. Lymph nodes
    has_ln = data.get("s14_check") or bool(data.get("s14_min")) or bool(data.get("s14_max"))
    chk_ln = "☑" if has_ln else "☐"
    min_ln = data.get("s14_min", "").strip()
    max_ln = data.get("s14_max", "").strip()

    p[19].text = ""
    add_run(p[19], f"{chk_ln}  There are multiple lymph nodes ranging from ")
    if min_ln:
        add_run(p[19], f" {min_ln} ", bold=True)
        add_run(p[19], "cm . to ")
    else:
        add_run(p[19], ".................................... cm . to ")
    if max_ln:
        add_run(p[19], f" {max_ln} ", bold=True)
        add_run(p[19], "cm . in diameter.")
    else:
        add_run(p[19], ".................................... cm . in diameter.")

    # 20. Header: Representative sections
    p[20].text = ""
    add_run(p[20], "Representative sections are submitted as", bold=True)

    # 21-26. Representative sections rows (2-column layout with tab stop at 3.8 inches)
    def format_sec_para(para, code1, label1, code2, label2):
        para.text = ""
        para.paragraph_format.tab_stops.add_tab_stop(Inches(3.8), WD_TAB_ALIGNMENT.LEFT)
        if code1:
            add_run(para, f"    {code1}", bold=True)
        else:
            add_run(para, "....................................")
        add_run(para, f" = {label1}\t")
        if code2:
            add_run(para, f" {code2}", bold=True)
        else:
            add_run(para, "....................................")
        add_run(para, f" = {label2}")

    sec = data.get("sections", {})

    def get_sec(lbl):
        it = sec.get(lbl, {})
        if isinstance(it, dict):
            return it.get("code", ""), it.get("extra", "")
        return str(it), ""

    c_nip, _ = get_sec("= nipple")
    c_mass, _ = get_sec("= mass")
    format_sec_para(p[21], c_nip, "nipple", c_mass, "mass")

    c_cav, _ = get_sec("= old biopsy cavity with fibrosis")
    c_dp, _ = get_sec("= deep resected margin")
    format_sec_para(p[22], c_cav, "old biopsy cavity with fibrosis", c_dp, "deep resected margin")

    c_nr, extra_nr = get_sec("= nearest resected margin")
    p[23].text = ""
    if c_nr:
        add_run(p[23], f"    {c_nr}", bold=True)
    else:
        add_run(p[23], "....................................")
    add_run(p[23], " = nearest resected margin  ,  ")
    if extra_nr:
        add_run(p[23], extra_nr, bold=True)
    else:
        add_run(p[23], ".......................................................")

    c_ui, _ = get_sec("= sampling upper inner quadrant")
    c_uo, _ = get_sec("= sampling upper outer quadrant")
    format_sec_para(p[24], c_ui, "sampling upper inner quadrant", c_uo, "sampling upper outer quadrant")

    c_li, _ = get_sec("= sampling lower inner quadrant")
    c_lo, _ = get_sec("= sampling lower outer quadrant")
    format_sec_para(p[25], c_li, "sampling lower inner quadrant", c_lo, "sampling lower outer quadrant")

    c_cen, _ = get_sec("= sampling central region")
    c_ax, _ = get_sec("= axillary lymph nodes")
    format_sec_para(p[26], c_cen, "sampling central region", c_ax, "axillary lymph nodes")

    # 28. Prosecutor Footer
    prosecutor = data.get("footer_prosecutor", "").strip()
    p[28].text = ""
    if prosecutor:
        add_run(p[28], f"{prosecutor} ", bold=True)
    else:
        add_run(p[28], ".................................................")
    add_run(p[28], "Prosecutor")
    p[28].alignment = WD_ALIGN_PARAGRAPH.RIGHT

    # 29. Date Footer
    date_val = data.get("footer_date", "").strip() or datetime.datetime.now().strftime("%d/%m/%Y")
    p[29].text = ""
    add_run(p[29], "Date ")
    add_run(p[29], date_val, bold=True)
    p[29].alignment = WD_ALIGN_PARAGRAPH.RIGHT

    # 31. Approved in conference
    p[31].text = ""
    add_run(p[31], "Approved in conference        2/10/2014", size=Pt(8))
    p[31].alignment = WD_ALIGN_PARAGRAPH.CENTER


def generate_docx_document(source_data: Any) -> BytesIO:
    """
    Generates a Microsoft Word (.docx) document matching the hospital's official
    Breast Gross examination paper template layout.
    """
    data = normalize_report_dict(source_data)

    template_path = Config.ASSETS_DIR / "Breast_Gross_Template.docx"
    if not template_path.exists():
        fallback = Path(__file__).resolve().parent.parent.parent / "data" / "assets" / "Breast_Gross_Template.docx"
        if fallback.exists():
            template_path = fallback

    if template_path.exists():
        doc = docx.Document(template_path)
        populate_template_doc(doc, data)
    else:
        # Fallback: create basic document if template file is completely missing
        doc = docx.Document()
        p = doc.add_paragraph(f"Surgical Number: {data.get('s0_surgical_no', 'Unknown')}")
        p.runs[0].bold = True
        doc.add_heading("Breast gross 1", level=1)
        for k, v in data.items():
            if v:
                doc.add_paragraph(f"{k}: {v}")

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf

