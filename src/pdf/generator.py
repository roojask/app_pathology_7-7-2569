import fitz  # PyMuPDF
import datetime
import io
import hashlib
import qrcode

RED = (1, 0, 0)
BLUE = (0, 0, 1)

def generate_verification_qr_pixmap(surgical_no, timestamp_str):
    """สร้าง QR Code รับรองความถูกต้องของรายงานทางการแพทย์และป้องกันการปลอมแปลง"""
    payload = f"PATHOLOGY_VERIFIED|CASE:{surgical_no}|TIME:{timestamp_str}|SYS:PathoVoice_v1.0"
    doc_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()[:12].upper()
    qr_data = f"https://10.198.200.79:7860/verify?case={surgical_no}&hash={doc_hash}"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=3,
        border=1
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    
    return fitz.Pixmap(img_byte_arr.getvalue()), doc_hash

def draw_standard_tick_at(page, cx, cy):
    shape = page.new_shape()
    p1 = fitz.Point(cx - 2.5, cy + 0.5)
    p2 = fitz.Point(cx - 0.5, cy + 3.0)
    p3 = fitz.Point(cx + 4.0, cy - 3.5)
    shape.draw_line(p1, p2)
    shape.draw_line(p2, p3)
    shape.finish(color=RED, width=1.25, lineJoin=1, lineCap=1)
    shape.commit()

def draw_tick(page, anchor_text, offset_x=-15, offset_y=5, search_instance=0):
    hits = page.search_for(anchor_text)
    if not hits: 
        hits = page.search_for(anchor_text.replace("(", "( ")) 
    if not hits or len(hits) <= search_instance: return
    
    rect = hits[search_instance]
    clip_box = fitz.Rect(rect.x0 - 50, rect.y0 - 5, rect.x0 + 5, rect.y1 + 5)
    box_hits = page.search_for("☐", clip=clip_box)
    if box_hits:
        b = box_hits[-1]
        cx = (b.x0 + b.x1) / 2
        cy = (b.y0 + b.y1) / 2
    else:
        cx = rect.x0 + offset_x + 5
        cy = (rect.y0 + rect.y1) / 2
        
    draw_standard_tick_at(page, cx, cy)

def write_text(page, anchor_text, text, offset_x=5, offset_y=-3, align_left=False):
    hits = page.search_for(anchor_text)
    if not hits: return
    rect = hits[0]
    x = rect.x1 + offset_x
    if align_left:
        width = len(str(text)) * 6
        x = rect.x0 - width - offset_x
    y = rect.y1 + offset_y
    page.insert_text(fitz.Point(x, y), str(text), fontsize=10, fontname="helv", color=BLUE)

def write_spaced_dims(page, anchor_text, dims_list, start_offset=45, gap=40, instance=0, y_offset=-3):
    if not dims_list: return
    hits = page.search_for(anchor_text)
    if not hits or len(hits) <= instance: return
    rect = hits[instance]
    current_x = rect.x1 + start_offset
    y = rect.y1 + y_offset
    for val in dims_list:
        page.insert_text(fitz.Point(current_x, y), str(val), fontsize=10, fontname="helv", color=BLUE)
        current_x += gap

def write_exact_slot_dims(page, slot_centers, y, dims_list):
    if not dims_list: return
    for i, val in enumerate(dims_list):
        if i >= len(slot_centers): break
        s_val = str(val).strip()
        width = len(s_val) * 5.8
        cx = slot_centers[i]
        x = cx - (width / 2)
        page.insert_text(fitz.Point(x, y), s_val, fontsize=10, fontname="helv", color=BLUE)

def process_pdf_15_sections(template_path, output_path, data):
    doc = fitz.open(template_path)
    page = doc[0]

    # --- Digital Verification QR Code Stamp ---
    s_no = data.get("s0_surgical_no", "S-Unknown")
    time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        qr_pixmap, doc_hash = generate_verification_qr_pixmap(s_no, time_str)
        qr_rect = fitz.Rect(535, 18, 580, 63)
        page.insert_image(qr_rect, pixmap=qr_pixmap)
        page.insert_text(fitz.Point(535, 68), f"#{doc_hash}", fontsize=5.5, fontname="helv", color=(0.4, 0.4, 0.4))
    except Exception as qr_err:
        print(f"[PDF QR Note] {qr_err}")

    if data.get("s0_surgical_no"):
        s_val = str(data["s0_surgical_no"]).replace("S-", "").replace("S", "").strip()
        width = len(s_val) * 6.0
        page.insert_text(fitz.Point(485 - (width / 2), 50.5), s_val, fontsize=10, fontname="helv", color=BLUE)
    
    # Side
    if data.get("s1_side"):
        ctx_hits = page.search_for("Received in formalin")
        if ctx_hits:
            search_rect = fitz.Rect(0, ctx_hits[0].y0 - 2, page.rect.width, ctx_hits[0].y1 + 10)
            hits = page.search_for(data["s1_side"], clip=search_rect)
            if hits:
                rect = hits[0]
                shape = page.new_shape()
                shape.draw_oval(fitz.Rect(rect.x0 - 2, rect.y0 - 1, rect.x1 + 2, rect.y1 + 1))
                shape.finish(color=RED, width=1.5)
                shape.commit()

    if data.get("s2_proc") == "modified": draw_standard_tick_at(page, 226.4, 94.7)
    elif data.get("s2_proc") == "simple": draw_standard_tick_at(page, 71.5, 114.8)
    elif data.get("s2_proc") == "other" or data.get("s2_other_text"):
        draw_standard_tick_at(page, 226.4, 114.8)
        if data.get("s2_other_text"):
            page.insert_text(fitz.Point(236.0, 118.0), str(data["s2_other_text"]), fontsize=9, fontname="helv", color=BLUE)
        
    if data.get("s3_dims"): write_exact_slot_dims(page, [138.9, 179.3, 219.8], 137.5, data["s3_dims"])
    if data.get("s4_check"):
        draw_standard_tick_at(page, 267.0, 134.7)
        if data.get("s4_dims"): write_exact_slot_dims(page, [383.0, 423.5, 464.0], 137.5, data["s4_dims"])
    if data.get("s5_dims"): write_exact_slot_dims(page, [140.9, 181.3], 157.4, data["s5_dims"])
    
    if data.get("s5_appears_normal"):
        draw_standard_tick_at(page, 248.5, 154.6)

    if data.get("s6_check") or data.get("s7_len") or data.get("s7_locs"):
        draw_standard_tick_at(page, 46.4, 175.7)
        if data.get("s7_len"): write_text(page, "cm in length", data["s7_len"], offset_x=15, align_left=True)
        if data.get("s7_locs"):
            locs = data["s7_locs"]
            if isinstance(locs, str): locs = [locs]
            loc_rect = fitz.Rect(260, 166, 430, 186)
            for loc in locs:
                for word in loc.strip().lower().split():
                    hits = page.search_for(word, clip=loc_rect)
                    if hits:
                        rect = hits[0]
                        shape = page.new_shape()
                        shape.draw_oval(fitz.Rect(rect.x0 - 2.5, rect.y0 - 1.5, rect.x1 + 2.5, rect.y1 + 1.5))
                        shape.finish(color=RED, width=1.5)
                        shape.commit()

    if data.get("s8_check") or data.get("s8_dims") or data.get("s8_locs"):
        draw_standard_tick_at(page, 46.4, 197.0)
        if data.get("s8_dims"): write_exact_slot_dims(page, [154.8, 202.8], 199.8, data["s8_dims"])
        if data.get("s8_locs"):
            locs = data["s8_locs"]
            if isinstance(locs, str): locs = [locs]
            loc_rect = fitz.Rect(260, 188, 420, 208)
            for loc in locs:
                for word in loc.strip().lower().split():
                    hits = page.search_for(word, clip=loc_rect)
                    if hits:
                        rect = hits[0]
                        shape = page.new_shape()
                        shape.draw_oval(fitz.Rect(rect.x0 - 2.5, rect.y0 - 1.5, rect.x1 + 2.5, rect.y1 + 1.5))
                        shape.finish(color=RED, width=1.5)
                        shape.commit()
    
    if data.get("s9_val"):
        vals = data["s9_val"]
        if isinstance(vals, str): vals = [vals]
        if "everted" in vals: draw_standard_tick_at(page, 101.5, 217.5)
        if "inverted" in vals: draw_standard_tick_at(page, 163.1, 217.5)
        if "ulceration" in vals: draw_standard_tick_at(page, 248.5, 217.5)

    # Grammar / Quantifier: ( is a / is an / are two / are multiple )
    if data.get("s10_grammar"):
        val = str(data["s10_grammar"]).strip().lower()
        there_hits = page.search_for("There")
        if there_hits:
            row_rect = fitz.Rect(0, there_hits[0].y0 - 2, page.rect.width, there_hits[0].y1 + 10)
            hits = page.search_for(val, clip=row_rect)
            if hits:
                rect = hits[0]
                shape = page.new_shape()
                shape.draw_oval(fitz.Rect(rect.x0 - 2, rect.y0 - 1, rect.x1 + 2, rect.y1 + 1))
                shape.finish(color=RED, width=1.5)
                shape.commit()

    if data.get("s10_infiltrative"):
        draw_standard_tick_at(page, 82.4, 255.2)
        if data.get("s10_inf_dims"): write_exact_slot_dims(page, [263.7, 310.0, 356.5], 258.0, data["s10_inf_dims"])
    if data.get("s10_well"):
        draw_standard_tick_at(page, 82.4, 275.1)
        if data.get("s10_well_dims"): write_exact_slot_dims(page, [358.7, 405.2, 451.5], 277.9, data["s10_well_dims"])
    if data.get("s10_prev1"):
        draw_standard_tick_at(page, 82.4, 295.2)
        if data.get("s10_prev1_dims"): write_exact_slot_dims(page, [341.6, 388.1, 434.5], 297.9, data["s10_prev1_dims"])
    if data.get("s10_prev2"):
        draw_standard_tick_at(page, 82.4, 315.1)
        if data.get("s10_prev2_cavity_dims"): write_exact_slot_dims(page, [341.6, 388.1, 434.5], 317.9, data["s10_prev2_cavity_dims"])
        if data.get("s10_prev2_mass_dims"): write_exact_slot_dims(page, [189.4, 235.8, 282.2], 334.4, data["s10_prev2_mass_dims"])
    if data.get("s10_5_nipple"): draw_standard_tick_at(page, 124.0, 361.4)
    if data.get("s10_5_scar"): draw_standard_tick_at(page, 225.8, 361.4)
    if data.get("s10_5_central"): draw_standard_tick_at(page, 315.6, 361.4)
    
    # Quadrant
    if data.get("s10_5_quadrant_check") or data.get("s10_5_quadrant_vals"):
        draw_standard_tick_at(page, 110.0, 382.8)
        
        if data.get("s10_5_quadrant_vals"):
            line_clip = fitz.Rect(120, 370, 260, 395)
            q_list = data["s10_5_quadrant_vals"]
            if isinstance(q_list, str): q_list = [q_list]
            for q in q_list:
                for word in q.split():
                     word_hits = page.search_for(word, clip=line_clip)
                     if word_hits:
                         w = word_hits[0]
                         shape = page.new_shape()
                         shape.draw_oval(fitz.Rect(w.x0 - 2.5, w.y0 - 1.5, w.x1 + 2.5, w.y1 + 1.5))
                         shape.finish(color=RED, width=1.5)
                         shape.commit()

    if data.get("s10_5_other") or data.get("s10_5_other_check"):
        draw_standard_tick_at(page, 315.3, 382.8)
        if data.get("s10_5_other"):
            page.insert_text(fitz.Point(325.0, 386.0), str(data["s10_5_other"]), fontsize=9, fontname="helv", color=BLUE)

    margin_slots = {
        "s11_deep": (111.2, 423.0),
        "s11_superior": (365.3, 425.2),
        "s11_inferior": (111.2, 445.0),
        "s11_medial": (365.3, 445.0),
        "s11_lateral": (111.2, 463.0),
        "s11_skin": (374.0, 463.0)
    }
    for key, (cx, y) in margin_slots.items():
        val = data.get(key)
        if val:
            s_val = str(val).strip()
            width = len(s_val) * 5.8
            x = cx - (width / 2)
            page.insert_text(fitz.Point(x, y), s_val, fontsize=10, fontname="helv", color=BLUE)

    # Uninvolved Breast
    if data.get("s12_check"):
        draw_standard_tick_at(page, 46.4, 489.5)
        hits = page.search_for("ratio of approximately")
        if hits:
            rect = hits[0]
            colon_x = rect.x1 + 30
            if data.get("s12_val_left"): page.insert_text(fitz.Point(colon_x - 15, rect.y1 - 3), str(data["s12_val_left"]), fontsize=10, fontname="helv", color=BLUE)
            if data.get("s12_val_right"): page.insert_text(fitz.Point(colon_x + 10, rect.y1 - 3), str(data["s12_val_right"]), fontsize=10, fontname="helv", color=BLUE)

    # Unremarkable vs Other for Section 13
    if data.get("s13_unremarkable") or data.get("s13_type") == "unremarkable": 
        draw_standard_tick_at(page, 183.7, 509.5)
    elif data.get("s13_type") == "other" or data.get("s13_text"):
        draw_standard_tick_at(page, 270.4, 509.5)
        if data.get("s13_text"):
            page.insert_text(fitz.Point(280.0, 513.0), str(data["s13_text"]), fontsize=8.5, fontname="helv", color=BLUE)

    if data.get("s14_check"):
        draw_standard_tick_at(page, 46.4, 529.4)
        if data.get("s14_min"): write_text(page, "ranging from", data["s14_min"], offset_x=15)
        if data.get("s14_max"): write_text(page, "cm . to", data["s14_max"], offset_x=15)

    for anchor, item in data.get("sections", {}).items():
        if isinstance(item, dict):
            write_text(page, anchor, item["code"], align_left=True, offset_x=10)
            if item.get("extra"):
                hits = page.search_for(anchor)
                if hits:
                    rect = hits[0]
                    extra_txt = str(item['extra']).strip()
                    if not extra_txt.lower().startswith("with"):
                        extra_txt = f", {extra_txt}"
                    page.insert_text(fitz.Point(rect.x1 + 10, rect.y1 - 3), extra_txt, fontsize=9, fontname="helv", color=BLUE)
        else: write_text(page, anchor, item, align_left=True, offset_x=10)

    if data.get("footer_prosecutor"): write_text(page, "Prosecutor", data["footer_prosecutor"], offset_x=-170)
    if data.get("footer_date"): write_text(page, "Date", data["footer_date"], offset_x=20)
    else: write_text(page, "Date", datetime.datetime.now().strftime("%d/%m/%Y %H:%M"), offset_x=20)

    doc.save(output_path)
    doc.close()
