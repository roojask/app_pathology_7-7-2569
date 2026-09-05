# -*- coding: utf-8 -*-
"""
Diff Tracker Utility for Breast Gross Pathology Forms
Compares two revision snapshots of form_data and generates human-readable diff logs.
"""

FIELD_LABELS = {
    "s0_surgical_no": "รหัสสิ่งส่งตรวจ (Surgical Number)",
    "s1_side": "ข้างสิ่งส่งตรวจ (Laterality)",
    "s2_proc": "หัตถการผ่าตัด (Procedure)",
    "s2_other_text": "หัตถการอื่นๆ (Other Procedure)",
    "s3_dims": "ขนาดชิ้นเนื้อเต้านม (Specimen Dimensions)",
    "s4_check": "ชิ้นเนื้อรักแร้ (Axillary Content)",
    "s4_dims": "ขนาดชิ้นเนื้อรักแร้ (Axillary Dimensions)",
    "s5_check": "กล้ามเนื้ออก (Pectoralis Muscle)",
    "s5_dims": "ขนาดกล้ามเนื้ออก (Pectoralis Dimensions)",
    "s7_check": "แผลผ่าตัดเดิม (Previous Surgical Scar)",
    "s7_len": "ความยาวแผลผ่าตัดเดิม (Scar Length)",
    "s7_locs": "ตำแหน่งแผลผ่าตัด (Scar Locations)",
    "s8_dims": "ขนาดผิวหนังที่ตัดมา (Skin Ellipse Dimensions)",
    "s8_locs": "ตำแหน่งผิวหนัง (Skin Quadrants)",
    "s9_val": "ลักษณะหัวนม (Nipple Appearance)",
    "s9_ulcer_text": "รายละเอียดแผลหัวนม (Nipple Ulceration)",
    "s10_infiltrative": "พบก้อนมะเร็งชนิด Infiltrative Mass",
    "s10_inf_dims": "ขนาดก้อน Infiltrative Mass",
    "s10_well": "พบก้อนเนื้อชนิด Well-defined Mass",
    "s10_well_dims": "ขนาดก้อน Well-defined Mass",
    "s10_poorly": "พบรอยโรค Poorly Circumscribed",
    "s10_prev1": "Previous Surgical Cavity w/ Fibrous",
    "s10_prev1_dims": "ขนาด Previous Cavity",
    "s10_prev2": "Previous Cavity w/ Residual Mass",
    "s10_prev2_cavity_dims": "ขนาด Cavity ของ Previous Cavity 2",
    "s10_prev2_mass_dims": "ขนาด Residual Mass",
    "s10_grammar": "การบรรยายลักษณะก้อน (Tumor Morphology)",
    "s10_5_quadrant_vals": "ตำแหน่งก้อนในเต้านม (Tumor Quadrants)",
    "s10_5_other": "ตำแหน่งก้อนอื่นๆ (Other Tumor Location)",
    "s11_deep": "ระยะขอบ Deep Margin",
    "s11_superior": "ระยะขอบ Superior Margin",
    "s11_inferior": "ระยะขอบ Inferior Margin",
    "s11_medial": "ระยะขอบ Medial Margin",
    "s11_lateral": "ระยะขอบ Lateral Margin",
    "s11_skin": "ระยะขอบ Skin Margin",
    "s11_margin_right": "ระยะห่างขอบเขตมะเร็ง (Margin Distance)",
    "s12_val_left": "ระยะ Deep Fascia Margin",
    "s12_val_right": "ระยะ Pectoralis Muscle Margin",
    "s13_type": "ลักษณะเนื้อเยื่อปกติที่เหลือ (Non-neoplastic Tissue)",
    "s13_text": "รายละเอียดเนื้อเยื่อปกติเพิ่มเติม",
    "s14_check": "การตรวจต่อมน้ำเหลือง (Lymph Nodes)",
    "s14_num": "จำนวนต่อมน้ำเหลืองที่พบ (Lymph Nodes Count)",
    "s14_min": "ขนาดต่อมน้ำเหลืองเล็กสุด (Min Node Size)",
    "s14_max": "ขนาดต่อมน้ำเหลืองใหญ่สุด (Max Node Size)",
    "footer_prosecutor": "ผู้ตรวจชิ้นเนื้อ (Prosecutor)",
    "footer_date": "วันที่ตรวจ (Date of Examination)"
}

IGNORE_KEYS = {
    "_low_confidence",
    "audio_filename",
    "transcription",
    "transcription_text",
    "loaded_history_id",
    "is_new_case",
    "photo_data"
}

def format_val(key: str, val):
    if val is None or val == "":
        return "-"
    
    if isinstance(val, list):
        if not val:
            return "-"
        # Check if it's a 3D dimension array (e.g. ['10', '8', '3'])
        if "dims" in key:
            clean_dims = [str(x).strip() for x in val if str(x).strip()]
            if clean_dims:
                return " x ".join(clean_dims) + " cm"
            return "-"
        return ", ".join(str(x) for x in val)

    if isinstance(val, bool):
        return "เลือก (Checked)" if val else "ไม่ได้เลือก (Unchecked)"

    val_str = str(val).strip()
    if not val_str:
        return "-"
    return val_str


def calculate_form_diff(old_data: dict, new_data: dict) -> list:
    """
    Compares old_data and new_data dictionaries.
    Returns a list of changed items:
    [
        {
            "field": "s3_dims",
            "label": "ขนาดชิ้นเนื้อเต้านม (Specimen Dimensions)",
            "old": "10 x 8 x 3 cm",
            "new": "12 x 8 x 3 cm"
        },
        ...
    ]
    """
    old_data = old_data or {}
    new_data = new_data or {}

    diffs = []
    all_keys = set(old_data.keys()).union(set(new_data.keys()))

    for key in sorted(all_keys):
        if key in IGNORE_KEYS:
            continue
        if key.startswith("_"):
            continue

        old_raw = old_data.get(key)
        new_raw = new_data.get(key)

        # Standardize for comparison
        old_formatted = format_val(key, old_raw)
        new_formatted = format_val(key, new_raw)

        if old_formatted != new_formatted:
            label = FIELD_LABELS.get(key, key)
            diffs.append({
                "field": key,
                "label": label,
                "old": old_formatted,
                "new": new_formatted
            })

    # Track specimen photo changes cleanly without embedding huge base64 strings in diff text
    old_has_photo = bool(old_data.get("photo_data"))
    new_has_photo = bool(new_data.get("photo_data"))
    if old_has_photo != new_has_photo or (old_has_photo and new_has_photo and old_data.get("photo_data") != new_data.get("photo_data")):
        diffs.append({
            "field": "photo_data",
            "label": "ภาพถ่ายชิ้นเนื้อ (Specimen Photo)",
            "old": "มีภาพบันทึกไว้" if old_has_photo else "ไม่มีภาพ",
            "new": "บันทึกภาพใหม่" if new_has_photo else "ลบภาพออก"
        })

    return diffs
