import fitz  # PyMuPDF
from pdf2docx import Converter
import datetime

RED = (1, 0, 0)
BLUE = (0, 0, 1)

def draw_tick(page, anchor_text, offset_x=-15, offset_y=5, search_instance=0):
    hits = page.search_for(anchor_text)
    if not hits: 
        hits = page.search_for(anchor_text.replace("(", "( ")) 
    if not hits or len(hits) <= search_instance: return
    
    rect = hits[search_instance]
    start_pt = fitz.Point(rect.x0 + offset_x + 2, rect.y1 - offset_y)
    shape = page.new_shape()
    bottom_pt = fitz.Point(start_pt.x + 3, start_pt.y + 4)
    end_pt = fitz.Point(start_pt.x + 8, start_pt.y - 6)
    shape.draw_line(start_pt, bottom_pt)
    shape.draw_line(bottom_pt, end_pt)
    shape.finish(color=RED, width=1.5) 
    shape.commit()

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

def convert_to_docx(pdf_file, docx_file):
    cv = Converter(pdf_file)
    cv.convert(docx_file, start=0, end=None)
    cv.close()

def process_pdf_15_sections(template_path, output_path, data):
    doc = fitz.open(template_path)
    page = doc[0]

    if data.get("s0_surgical_no"): write_text(page, "Surgical Number S", data["s0_surgical_no"].replace("S-", ""), offset_x=90)
    
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

    if data.get("s2_proc") == "modified": draw_tick(page, "modified radical mastectomy")
    elif data.get("s2_proc") == "simple": draw_tick(page, "simple mastectomy")
    elif data.get("s2_proc") == "other":
        hits = page.search_for("simple mastectomy specimen")
        if hits:
            anchor = hits[0]
            clip_right = fitz.Rect(anchor.x1, anchor.y0 - 5, page.rect.width, anchor.y1 + 5)
            box_hits = page.search_for("☐", clip=clip_right)
            if box_hits:
                box_rect = box_hits[0]
                center = fitz.Point((box_rect.x0 + box_rect.x1)/2, (box_rect.y0 + box_rect.y1)/2)
                shape = page.new_shape()
                shape.draw_line(fitz.Point(center.x - 4, center.y - 2), fitz.Point(center.x, center.y + 4))
                shape.draw_line(fitz.Point(center.x, center.y + 4), fitz.Point(center.x + 5, center.y - 6))
                shape.finish(color=RED, width=1.5)
                shape.commit()
            else: draw_tick(page, "simple mastectomy", offset_x=220)
        else: draw_tick(page, "simple mastectomy", offset_x=220)
        if data.get("s2_other_text"): write_text(page, "simple mastectomy", data["s2_other_text"], offset_x=240)
        
    if data.get("s3_dims"): write_spaced_dims(page, "Measuring", data["s3_dims"], start_offset=15, gap=40)
    if data.get("s4_check"):
        draw_tick(page, "with axillary content")
        if data.get("s4_dims"): write_spaced_dims(page, "with axillary content", data["s4_dims"], start_offset=15, gap=40)
    if data.get("s5_dims"): write_spaced_dims(page, "The skin ellipse", data["s5_dims"], start_offset=20, gap=40)
    
    if data.get("s5_appears_normal"):
        hits = page.search_for("appears normal")
        if hits:
            anchor = hits[0]
            clip_left = fitz.Rect(anchor.x0 - 50, anchor.y0 - 5, anchor.x0, anchor.y1 + 5)
            box_hits = page.search_for("☐", clip=clip_left)
            if box_hits:
                box_rect = box_hits[-1]
                center = fitz.Point((box_rect.x0 + box_rect.x1)/2, (box_rect.y0 + box_rect.y1)/2)
                shape = page.new_shape()
                shape.draw_line(fitz.Point(center.x - 4, center.y - 2), fitz.Point(center.x, center.y + 4))
                shape.draw_line(fitz.Point(center.x, center.y + 4), fitz.Point(center.x + 5, center.y - 6))
                shape.finish(color=RED, width=1.5)
                shape.commit()
            else: draw_tick(page, "appears normal", offset_x=-20)
        else: draw_tick(page, "appears normal", offset_x=-20)

    if data.get("s6_check"):
        draw_tick(page, "shows an old surgical scar")
        if data.get("s7_len"): write_text(page, "cm in length", data["s7_len"], offset_x=15, align_left=True)

    if data.get("s8_check"):
        draw_tick(page, "shows an ulceration")
        if data.get("s8_dims"): write_spaced_dims(page, "shows an ulceration", data["s8_dims"], start_offset=25, gap=55)
    
    if data.get("s9_val"):
        vals = data["s9_val"]
        if isinstance(vals, str): vals = [vals]
        if "everted" in vals: draw_tick(page, "is everted", offset_x=-15)
        if "inverted" in vals: draw_tick(page, "shows inverted", offset_x=-20)
        if "ulceration" in vals:
            n_hits = page.search_for("The nipple")
            target_rect = None
            if n_hits:
                row_y = n_hits[0].y0
                u_hits = page.search_for("ulceration")
                for h in u_hits:
                    if h.y0 >= row_y - 5 and h.y0 < row_y + 40:
                        target_rect = h
                        break
            if target_rect:
                 clip_left = fitz.Rect(target_rect.x0 - 80, target_rect.y0 - 5, target_rect.x0, target_rect.y1 + 5)
                 box_hits = page.search_for("☐", clip=clip_left)
                 if box_hits:
                     b = box_hits[-1]
                     center = fitz.Point((b.x0 + b.x1)/2, (b.y0 + b.y1)/2)
                     shape = page.new_shape()
                     shape.draw_line(fitz.Point(center.x-4, center.y-2), fitz.Point(center.x, center.y+4))
                     shape.draw_line(fitz.Point(center.x, center.y+4), fitz.Point(center.x+5, center.y-6))
                     shape.finish(color=RED, width=1.5)
                     shape.commit()
                 else: draw_tick(page, "shows ulceration", search_instance=-1)
            else: draw_tick(page, "shows ulceration", search_instance=-1)

    if data.get("s10_infiltrative"):
        draw_tick(page, "infiltrative")
        if data.get("s10_inf_dims"): write_spaced_dims(page, "yellow white mass", data["s10_inf_dims"], start_offset=30, gap=45)
    if data.get("s10_well"):
        draw_tick(page, "well")
        if data.get("s10_well_dims"): write_spaced_dims(page, "slit like appearance", data["s10_well_dims"], start_offset=30, gap=42)
    if data.get("s10_prev1"):
        draw_tick(page, "previous surgical cavity", search_instance=0)
        if data.get("s10_prev1_dims"): write_spaced_dims(page, "adjacent fibrous tissue", data["s10_prev1_dims"], start_offset=35, instance=0, gap=45)
    if data.get("s10_prev2"):
        draw_tick(page, "previous surgical cavity", search_instance=1)
        if data.get("s10_prev2_cavity_dims"): write_spaced_dims(page, "adjacent fibrous tissue", data["s10_prev2_cavity_dims"], start_offset=25, instance=1, gap=45, y_offset=-3)
        if data.get("s10_prev2_mass_dims"): write_spaced_dims(page, "residual mass", data["s10_prev2_mass_dims"], start_offset=30, gap=45, y_offset=-3, instance=-1)
    if data.get("s10_5_nipple"): draw_tick(page, "beneath the nipple")
    if data.get("s10_5_scar"): draw_tick(page, "beneath the scar")
    if data.get("s10_5_central"): draw_tick(page, "in the central portion")
    
    # Quadrant
    if data.get("s10_5_quadrant_check"):
        q_hits = page.search_for("upper/lower/inner/outer")
        if not q_hits: q_hits = page.search_for("upper / lower")
        if not q_hits: q_hits = page.search_for("upper")
        if q_hits:
            target = q_hits[-1]
            cx = target.x0 - 45
            cy = (target.y0 + target.y1) / 2
            shape = page.new_shape()
            shape.draw_line(fitz.Point(cx - 4, cy - 2), fitz.Point(cx, cy + 4))
            shape.draw_line(fitz.Point(cx, cy + 4), fitz.Point(cx + 5, cy - 6))
            shape.finish(color=RED, width=1.5)
            shape.commit()
            
            if data.get("s10_5_quadrant_vals"):
                line_clip = fitz.Rect(0, target.y0 - 5, page.rect.width, target.y1 + 5)
                for q in data["s10_5_quadrant_vals"]:
                    for word in q.split():
                         word_hits = page.search_for(word, clip=line_clip)
                         if word_hits:
                             w = word_hits[0]
                             shape = page.new_shape()
                             shape.draw_oval(fitz.Rect(w.x0 - 2, w.y0 - 2, w.x1 + 2, w.y1 + 2))
                             shape.finish(color=RED, width=1.5)
                             shape.commit()

    if data.get("s10_5_other"):
        anchor_hits = page.search_for("in (")
        if anchor_hits:
            anchor = anchor_hits[0]
            line_rect = fitz.Rect(anchor.x1, anchor.y0 - 5, page.rect.width, anchor.y1 + 5)
            q_hits = page.search_for("quadrant", clip=line_rect)
            if q_hits:
                q_rect = q_hits[0]
                right_clip = fitz.Rect(q_rect.x1, q_rect.y0 - 5, page.rect.width, q_rect.y1 + 5)
                box_hits = page.search_for("☐", clip=right_clip)
                target_box = box_hits[0] if box_hits else fitz.Rect(q_rect.x1 + 35, q_rect.y0, q_rect.x1 + 45, q_rect.y1)
                if target_box:
                    center = fitz.Point((target_box.x0 + target_box.x1)/2, (target_box.y0 + target_box.y1)/2)
                    shape = page.new_shape()
                    shape.draw_line(fitz.Point(center.x - 4, center.y - 2), fitz.Point(center.x, center.y + 4))
                    shape.draw_line(fitz.Point(center.x, center.y + 4), fitz.Point(center.x + 5, center.y - 6))
                    shape.finish(color=RED, width=1.5)
                    shape.commit()
                    page.insert_text(fitz.Point(target_box.x1 + 5, target_box.y1 - 2), str(data["s10_5_other"]), fontsize=10, fontname="helv", color=BLUE)

    margin_anchors = {
        "s11_deep": "cm. from deep margin", "s11_superior": "cm. from superior margin",
        "s11_inferior": "cm. from inferior margin", "s11_medial": "cm. from medial margin",
        "s11_lateral": "cm. from lateral margin", "s11_skin": "cm. from skin"
    }
    for key, anchor in margin_anchors.items():
        val = data.get(key)
        if val: write_text(page, anchor, val, align_left=True, offset_x=10)

    if data.get("s11_margin_right"):
        write_text(page, "nearest resected margin", data.get("s11_margin_right"), align_left=True, offset_x=10)

    # Uninvolved Breast
    if data.get("s12_check"):
        draw_tick(page, "The uninvolved breast")
        hits = page.search_for("ratio of approximately")
        if hits:
            rect = hits[0]
            colon_x = rect.x1 + 30
            if data.get("s12_val_left"): page.insert_text(fitz.Point(colon_x - 15, rect.y1 - 3), str(data["s12_val_left"]), fontsize=10, fontname="helv", color=BLUE)
            if data.get("s12_val_right"): page.insert_text(fitz.Point(colon_x + 10, rect.y1 - 3), str(data["s12_val_right"]), fontsize=10, fontname="helv", color=BLUE)

    # Unremarkable
    if data.get("s13_unremarkable") or data.get("s13_type") == "unremarkable": 
        hits = page.search_for("unremarkable")
        if hits:
            anchor = hits[-1]
            left_clip = fitz.Rect(0, anchor.y0 - 5, anchor.x0, anchor.y1 + 5)
            box_hits = page.search_for("☐", clip=left_clip)
            if box_hits:
                b = box_hits[-1]
                cx = (b.x0 + b.x1) / 2
                cy = (b.y0 + b.y1) / 2
            else:
                cx = anchor.x0 - 185
                cy = (anchor.y0 + anchor.y1) / 2
            shape = page.new_shape()
            shape.draw_line(fitz.Point(cx - 4, cy - 2), fitz.Point(cx, cy + 4))
            shape.draw_line(fitz.Point(cx, cy + 4), fitz.Point(cx + 5, cy - 6))
            shape.finish(color=RED, width=1.5)
            shape.commit()

    if data.get("s14_check"):
        draw_tick(page, "There are multiple lymph nodes", offset_x=-15)
        if data.get("s14_min"): write_text(page, "ranging from", data["s14_min"], offset_x=15)
        if data.get("s14_max"): write_text(page, "cm . to", data["s14_max"], offset_x=15)

    for anchor, item in data.get("sections", {}).items():
        if isinstance(item, dict):
            write_text(page, anchor, item["code"], align_left=True, offset_x=10)
            if item["extra"]:
                hits = page.search_for(anchor)
                if hits:
                    rect = hits[0]
                    page.insert_text(fitz.Point(rect.x1 + 40, rect.y1 - 3), f", {item['extra']}", fontsize=10, fontname="helv", color=BLUE)
        else: write_text(page, anchor, item, align_left=True, offset_x=10)

    if data.get("footer_prosecutor"): write_text(page, "Prosecutor", data["footer_prosecutor"], offset_x=-170)
    if data.get("footer_date"): write_text(page, "Date", data["footer_date"], offset_x=20)
    else: write_text(page, "Date", datetime.datetime.now().strftime("%d/%m/%Y %H:%M"), offset_x=20)

    doc.save(output_path)
    doc.close()
