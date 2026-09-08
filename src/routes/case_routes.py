import json
import uuid
import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response, jsonify, current_app
from flask_login import login_required, current_user
from configs.config import Config
from src.database.models import db, User, FormHistory, CaseRevision, SpecimenPhoto, get_thai_time
from src.stt.whisper_model import transcribe_audio
from src.nlp.extractor import extract_data_15_sections, generate_confidence_flags
from src.pdf.generator import process_pdf_15_sections
from src.utils.diff_tracker import calculate_form_diff

cases_bp = Blueprint("cases", __name__)

def synthesize_transcription_from_data(data: dict) -> str:
    """
    Synthesizes fluent clinical pathology dictation text from structured form data
    for historical cases that did not store raw speech transcripts.
    """
    if not data:
        return ""
    
    parts = []
    # 1. Specimen & Procedure
    side = data.get("s1_side", "").strip()
    proc = data.get("s2_proc", "").strip()
    if proc == "modified":
        proc_desc = "modified radical mastectomy specimen"
    elif proc == "simple":
        proc_desc = "simple mastectomy specimen"
    else:
        proc_desc = "mastectomy specimen"
        
    specimen_lead = "Received in formalin is a"
    if side:
        specimen_lead += f" {side}"
    specimen_lead += f" {proc_desc}"
    
    s3_dims = data.get("s3_dims") or []
    valid_s3 = [str(d) for d in s3_dims if str(d).strip()]
    if valid_s3:
        specimen_lead += f" measuring {' x '.join(valid_s3)} cm."
    else:
        specimen_lead += "."
        
    s4_dims = data.get("s4_dims") or []
    valid_s4 = [str(d) for d in s4_dims if str(d).strip()]
    if data.get("s4_check") or valid_s4:
        if valid_s4:
            specimen_lead += f" with axillary content measuring {' x '.join(valid_s4)} cm."
        else:
            specimen_lead += " with axillary content."
    parts.append(specimen_lead)
    
    # 2. Skin ellipse and scar
    s5_dims = data.get("s5_dims") or []
    valid_s5 = [str(d) for d in s5_dims if str(d).strip()]
    skin_details = []
    if valid_s5:
        skin_details.append(f"The skin ellipse measures {' x '.join(valid_s5)} cm")
    if data.get("s5_appears_normal"):
        skin_details.append("appears normal")
    if skin_details:
        parts.append(", ".join(skin_details) + ".")
        
    if data.get("s6_check") or data.get("s7_len") or data.get("s7_locs"):
        scar_text = "Shows an old surgical scar"
        if data.get("s7_len"):
            scar_text += f" {data.get('s7_len')} cm in length"
        locs = data.get("s7_locs") or []
        if locs:
            scar_text += f" at ({', '.join(locs)}) quadrant"
        parts.append(scar_text + ".")
        
    if data.get("s8_check") or data.get("s8_dims") or data.get("s8_locs"):
        s8_dims = data.get("s8_dims") or []
        valid_s8 = [str(d) for d in s8_dims if str(d).strip()]
        ulc_text = "Shows an ulceration"
        if valid_s8:
            ulc_text += f" measuring {' x '.join(valid_s8)} cm"
        s8_locs = data.get("s8_locs") or []
        if s8_locs:
            ulc_text += f" at ({', '.join(s8_locs)}) quadrant"
        parts.append(ulc_text + ".")
        
    if data.get("s9_val"):
        parts.append(f"The nipple {data.get('s9_val')}.")
        
    # 3. Tumor / Mass
    grammar = data.get("s10_grammar", "is a")
    masses = []
    if data.get("s10_infiltrative") or data.get("s10_inf_dims"):
        inf_dims = [str(d) for d in (data.get("s10_inf_dims") or []) if str(d).strip()]
        d_str = f" measuring {' x '.join(inf_dims)} cm" if inf_dims else ""
        masses.append(f"infiltrative firm yellow white mass{d_str}")
        
    if data.get("s10_well") or data.get("s10_well_dims"):
        well_dims = [str(d) for d in (data.get("s10_well_dims") or []) if str(d).strip()]
        d_str = f" measuring {' x '.join(well_dims)} cm" if well_dims else ""
        masses.append(f"well-defined firm white mass with slit like appearance{d_str}")
        
    if data.get("s10_prev1") or data.get("s10_prev1_dims"):
        p1_dims = [str(d) for d in (data.get("s10_prev1_dims") or []) if str(d).strip()]
        d_str = f" measuring {' x '.join(p1_dims)} cm" if p1_dims else ""
        masses.append(f"previous surgical cavity with adjacent fibrous tissue{d_str}")
        
    quad_vals = data.get("s10_5_quadrant_vals") or []
    loc_clause = f" located at ({' '.join(quad_vals)}) quadrant" if quad_vals else ""
    
    if masses:
        parts.append(f"There {grammar} {', and '.join(masses)}{loc_clause}.")
        
    # 4. Margins
    margin_items = []
    for m_key, m_name in [("s11_deep", "deep"), ("s11_superior", "superior"), ("s11_inferior", "inferior"),
                          ("s11_medial", "medial"), ("s11_lateral", "lateral"), ("s11_skin", "skin")]:
        val = data.get(m_key)
        if val:
            margin_items.append(f"{m_name} margin is {val} cm")
    if margin_items:
        parts.append("Resection margins: " + ", ".join(margin_items) + ".")
        
    # 5. Lymph nodes
    if data.get("s14_check") or data.get("s14_num") or data.get("s14_min") or data.get("s14_max"):
        ln_text = "Axillary lymph nodes identified"
        if data.get("s14_num"):
            ln_text += f", total {data.get('s14_num')} nodes found"
        if data.get("s14_min") or data.get("s14_max"):
            ln_text += f" ranging from {data.get('s14_min', '')} to {data.get('s14_max', '')} cm"
        parts.append(ln_text + ".")
        
    return " ".join(parts)


@cases_bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        transcription = None
        audio_fn = request.form.get('audio_filename')
        photo_data = request.form.get('photo_data') or ""
        photos_json = request.form.get('photos_json') or ""
        audio_clips_json = request.form.get('audio_clips_json') or ""

        photos = []
        if photos_json:
            try:
                photos = json.loads(photos_json)
                if not isinstance(photos, list):
                    photos = []
            except Exception:
                photos = []
        if not photos and photo_data:
            photos = [photo_data]

        audio_clips = []
        if audio_clips_json:
            try:
                audio_clips = json.loads(audio_clips_json)
                if not isinstance(audio_clips, list):
                    audio_clips = []
            except Exception:
                audio_clips = []
        if not audio_clips and audio_fn:
            audio_url = audio_fn if (audio_fn.startswith("http://") or audio_fn.startswith("https://")) else url_for('get_upload', filename=audio_fn)
            audio_clips = [{"filename": audio_fn, "url": audio_url, "label": "Clip 1", "timestamp": ""}]
        
        if request.form.get('transcription_text'):
            transcription = request.form.get('transcription_text')

        audio_file = request.files.get('audio_file')
        if audio_file and audio_file.filename != '':
            from werkzeug.utils import secure_filename
            orig_filename = secure_filename(audio_file.filename)
            filename = f"{uuid.uuid4().hex}_{orig_filename}"
            audio_path = Config.UPLOAD_DIR / filename 
            audio_file.save(audio_path)
            audio_fn = filename
            transcription = transcribe_audio(audio_path)

            # Upload to Supabase Storage if configured
            if Config.SUPABASE_URL and Config.SUPABASE_KEY:
                from src.storage.supabase_client import upload_audio_to_supabase
                public_url = upload_audio_to_supabase(audio_path, filename, Config.SUPABASE_URL, Config.SUPABASE_KEY)
                if public_url:
                    print(f"[App] Audio uploaded to Supabase Storage: {public_url}")
                    audio_fn = public_url

            from src.nlp.normalizer import normalize_text
            transcription = normalize_text(transcription)

            audio_url = audio_fn if (audio_fn.startswith("http://") or audio_fn.startswith("https://")) else url_for('get_upload', filename=audio_fn)
            audio_clips.append({"filename": audio_fn, "url": audio_url, "label": f"Clip {len(audio_clips)+1}", "timestamp": ""})

        data = {}
        flags = {}
        if transcription and "Error during transcription" not in transcription:
             data = extract_data_15_sections(transcription)
             flags = generate_confidence_flags(data) 
        
        if photos:
            data["photos"] = photos
            photo_data = photos[0]
            data["photo_data"] = photo_data
        if audio_clips:
            data["audio_clips"] = audio_clips
            audio_fn = audio_clips[-1].get("filename", "")
            data["audio_filename"] = audio_fn

        return render_template('index.html', 
                               transcription=transcription, 
                               data=data, 
                               flags=flags, 
                               audio_filename=audio_fn, 
                               audio_clips=audio_clips,
                               audio_clips_json=json.dumps(audio_clips, ensure_ascii=False),
                               photo_data=photo_data, 
                               photos=photos, 
                               photos_json=json.dumps(photos, ensure_ascii=False),
                               is_new_case=False)

    is_new = request.args.get("new") in ["1", "true", "True"] or request.args.get("new_case") in ["1", "true", "True"]
    return render_template("index.html", 
                           is_new_case=is_new, 
                           photo_data="", 
                           photos=[], 
                           photos_json="[]", 
                           audio_filename="", 
                           audio_clips=[], 
                           audio_clips_json="[]")


@cases_bp.route("/dashboard")
@login_required
def dashboard():
    is_admin = current_user.check_is_admin
    recent_cases = FormHistory.query.filter_by(is_deleted=False).order_by(FormHistory.timestamp.desc()).limit(6).all() if is_admin else FormHistory.query.filter_by(user_id=current_user.id, is_deleted=False).order_by(FormHistory.timestamp.desc()).limit(6).all()
    total_count = FormHistory.query.filter_by(is_deleted=False).count() if is_admin else FormHistory.query.filter_by(user_id=current_user.id, is_deleted=False).count()
    
    flywheel_stats = None
    try:
        from src.flywheel.collector import get_flywheel_stats
        flywheel_stats = get_flywheel_stats()
    except Exception as e:
        print(f"Error fetching flywheel stats: {e}")

    return render_template(
        "dashboard.html",
        recent_cases=recent_cases,
        total_count=total_count,
        user=current_user,
        flywheel_stats=flywheel_stats,
        active_tab="dashboard"
    )


@cases_bp.route("/history")
@login_required
def history():
    is_admin = current_user.check_is_admin
    all_histories = FormHistory.query.filter_by(is_deleted=False).order_by(FormHistory.id.desc()).all()
    user_histories = all_histories if is_admin else FormHistory.query.filter_by(user_id=current_user.id, is_deleted=False).order_by(FormHistory.id.desc()).all()
    all_users = User.query.all() if is_admin else []
        
    db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    return render_template(
        "history.html", 
        histories=user_histories, 
        all_histories=all_histories, 
        all_users=all_users, 
        is_admin=is_admin,
        db_uri=db_uri
    )


@cases_bp.route("/history/load/<int:history_id>")
@login_required
def load_history(history_id):
    history_record = FormHistory.query.get_or_404(history_id)
    
    if history_record.user_id != current_user.id and not current_user.check_is_admin:
        flash("Unauthorized access to other user's history.", "danger")
        return redirect(url_for('history'))
        
    try:
        data = json.loads(history_record.form_data)
    except Exception as e:
        print(f"Error loading JSON data: {e}")
        flash("Error loading form data.", "danger")
        return redirect(url_for('history'))
        
    flags = generate_confidence_flags(data)
    
    transcription = data.get("transcription") or data.get("transcription_text") or ""
    if not transcription or not transcription.strip():
        transcription = synthesize_transcription_from_data(data)
        try:
            data["transcription"] = transcription
            history_record.form_data = json.dumps(data)
            db.session.commit()
        except Exception as update_err:
            db.session.rollback()
            print(f"[load_history update_err] {update_err}")

    photos = history_record.photo_list
    audio_clips = history_record.audio_clip_list
    audio_fn = audio_clips[-1]["filename"] if audio_clips else (history_record.audio_filename or data.get("audio_filename") or "")
    photo_data = photos[0] if photos else (getattr(history_record, 'photo_data', None) or data.get("photo_data") or "")

    pdf_filename = f"case_{history_id}.pdf"
    pdf_path = Config.OUTPUT_DIR / pdf_filename
    if not pdf_path.exists() and Config.PDF_TEMPLATE_PATH.exists():
        try:
            process_pdf_15_sections(Config.PDF_TEMPLATE_PATH, pdf_path, data)
        except Exception as pe:
            print(f"[load_history PDF Error] {pe}")
            pdf_filename = None

    docx_filename = f"case_{history_id}.docx"
    docx_path = Config.OUTPUT_DIR / docx_filename
    if not docx_path.exists():
        try:
            from src.export.docx_exporter import generate_docx_document
            docx_buf = generate_docx_document(data)
            with open(docx_path, "wb") as f:
                f.write(docx_buf.getvalue())
        except Exception as de:
            print(f"[load_history DOCX Error] {de}")
            docx_filename = None
            
    rev = CaseRevision.query.filter_by(history_id=history_id).order_by(CaseRevision.revision_number.desc()).first()
    revision_number = rev.revision_number if rev else 1

    return render_template(
        "index.html",
        data=data,
        flags=flags,
        transcription=transcription,
        audio_filename=audio_fn,
        audio_clips=audio_clips,
        audio_clips_json=json.dumps(audio_clips, ensure_ascii=False),
        photo_data=photo_data,
        photos=photos,
        photos_json=json.dumps(photos, ensure_ascii=False),
        pdf_filename=pdf_filename,
        docx_filename=docx_filename,
        loaded_history_id=history_id,
        loaded_surgical_no=history_record.surgical_number,
        revision_number=revision_number,
        is_new_case=False
    )


@cases_bp.route("/generate", methods=["GET", "POST"])
def generate_pdf():
    if request.method == "GET":
        return redirect(url_for("index"))

    form_data = request.form
    data = {}
    
    for field in ["s0_surgical_no", "s1_side", "s2_proc", "s2_other_text", "s7_len", 
                  "s9_ulcer_text", "s10_grammar", "s10_5_other",
                  "s11_deep", "s11_superior", "s11_inferior", "s11_medial", "s11_lateral", "s11_skin", "s11_margin_right",
                  "s12_val_left", "s12_val_right", "s13_type", "s13_text", "s14_min", "s14_max", "s14_num",
                  "footer_prosecutor", "footer_date"]:
        if form_data.get(field):
            data[field] = form_data.get(field)

    for key in ["s7_locs", "s8_locs", "s10_5_quadrant_vals", "s9_val"]:
        vals = request.form.getlist(key)
        if not vals and request.form.get(key): 
            vals = [request.form.get(key)]
        if vals: data[key] = vals

    for dim_key in ["s3_dims", "s4_dims", "s5_dims", "s8_dims", 
                    "s10_inf_dims", "s10_well_dims", "s10_prev1_dims", 
                    "s10_prev2_cavity_dims", "s10_prev2_mass_dims"]:
        dims = []
        d0 = form_data.get(f"{dim_key}_0")
        d1 = form_data.get(f"{dim_key}_1")
        d2 = form_data.get(f"{dim_key}_2")
        if d0: dims.append(d0)
        if d1: dims.append(d1)
        if d2: dims.append(d2)
        if dims: data[dim_key] = dims

    for chk in ["s4_check", "s5_appears_normal", "s6_check", "s7_check", "s8_check", 
                "s10_infiltrative", "s10_well", "s10_prev1", "s10_prev2",
                "s10_5_nipple", "s10_5_scar", "s10_5_central", "s10_5_other_check",
                "s12_check", "s14_check", "s13_unremarkable"]:
        if form_data.get(chk):
            data[chk] = True

    if data.get("s10_5_other") or form_data.get("s10_5_other"):
        data["s10_5_other_check"] = True

    if data.get("s13_type") == "unremarkable" or form_data.get("s13_type") == "unremarkable":
        data["s13_unremarkable"] = True

    if data.get("s10_5_quadrant_vals"):
        data["s10_5_quadrant_check"] = True

    data["sections"] = {}
    section_map = {
        "= nipple": "sec_nipple",
        "= mass": "sec_mass",
        "= old biopsy cavity with fibrosis": "sec_old_biopsy",
        "= deep resected margin": "sec_deep_margin",
        "= nearest resected margin": "sec_nearest_margin",
        "= sampling upper inner quadrant": "sec_upper_inner",
        "= sampling upper outer quadrant": "sec_upper_outer",
        "= sampling lower inner quadrant": "sec_lower_inner",
        "= sampling lower outer quadrant": "sec_lower_outer",
        "= anterior/superior margin": "sec_ant_sup",
        "= inferior margin": "sec_inf",
        "= medial margin": "sec_med",
        "= lateral margin": "sec_lat",
        "= skin": "sec_skin",
        "= random fibrous tissue": "sec_random_fibrous",
        "= lymph nodes": "sec_ln"
    }
    for label, key in section_map.items():
        v1 = form_data.get(f"{key}_1")
        v2 = form_data.get(f"{key}_2")
        if v1 or v2:
            data["sections"][label] = [v1 or "", v2 or ""]

    photo_cleared = request.form.get("photo_cleared") == "1"
    audio_cleared = request.form.get("audio_cleared") == "1"

    s_no = form_data.get("s0_surgical_no", "").strip() or "Case"
    clean_sno = s_no
    for pfx in ["Surgical Number:", "Surgical Number", "S-", "S -", "S ", "s-", "s "]:
        if clean_sno.startswith(pfx):
            clean_sno = clean_sno[len(pfx):].strip()

    pdf_filename = f"pathology_breast_gross_S-{clean_sno}.pdf" if clean_sno else "pathology_breast_gross_Case.pdf"
    docx_filename = f"pathology_breast_gross_S-{clean_sno}.docx" if clean_sno else "pathology_breast_gross_Case.docx"
    pdf_path = Config.OUTPUT_DIR / pdf_filename
    docx_path = Config.OUTPUT_DIR / docx_filename

    if Config.PDF_TEMPLATE_PATH.exists():
        process_pdf_15_sections(Config.PDF_TEMPLATE_PATH, pdf_path, data)

    from src.export.docx_exporter import generate_docx_document
    docx_buf = generate_docx_document(data)
    with open(docx_path, "wb") as f:
        f.write(docx_buf.getvalue())

    flags = generate_confidence_flags(data)

    photos_json = form_data.get("photos_json")
    photos = []
    if photos_json:
        try:
            photos = json.loads(photos_json)
            if not isinstance(photos, list):
                photos = []
        except Exception:
            photos = []

    photo_raw = form_data.get("photo_data")
    if not photos and photo_raw:
        photos = [photo_raw]

    audio_clips_json = form_data.get("audio_clips_json")
    audio_clips = []
    if audio_clips_json:
        try:
            audio_clips = json.loads(audio_clips_json)
            if not isinstance(audio_clips, list):
                audio_clips = []
        except Exception:
            audio_clips = []

    audio_fn = form_data.get("audio_filename")
    if not audio_clips and audio_fn:
        audio_url = audio_fn if (audio_fn.startswith("http://") or audio_fn.startswith("https://")) else url_for('get_upload', filename=audio_fn)
        audio_clips = [{"filename": audio_fn, "url": audio_url, "label": "Clip 1", "timestamp": ""}]

    history_record = None
    diff_list = []
    current_revision = 1

    try:
        user_id = current_user.id if current_user.is_authenticated else 1
        loaded_hist_id = form_data.get("loaded_history_id")

        if photo_cleared:
            photo_raw = ""
            data.pop("photo_data", None)
            data.pop("photos", None)
        elif photos:
            photo_raw = photos[0]
            data["photo_data"] = photo_raw
            data["photos"] = photos
        elif photo_raw:
            data["photo_data"] = photo_raw
            data["photos"] = [photo_raw]

        if audio_cleared:
            audio_fn = ""
            data.pop("audio_filename", None)
            data.pop("audio_clips", None)
        elif audio_clips:
            audio_fn = audio_clips[-1].get("filename", "")
            data["audio_filename"] = audio_fn
            data["audio_clips"] = audio_clips
        elif audio_fn:
            data["audio_filename"] = audio_fn
            audio_url = audio_fn if (audio_fn.startswith("http://") or audio_fn.startswith("https://")) else url_for('get_upload', filename=audio_fn)
            data["audio_clips"] = [{"filename": audio_fn, "url": audio_url, "label": "Clip 1", "timestamp": ""}]

        data["transcription"] = form_data.get("transcription") or form_data.get("transcription_text") or ""

        if loaded_hist_id and str(loaded_hist_id).strip().isdigit():
            history_record = FormHistory.query.get(int(loaded_hist_id))

        if history_record:
            old_data = {}
            try:
                old_data = json.loads(history_record.form_data)
            except Exception:
                old_data = {}

            diff_list = calculate_form_diff(old_data, data)

            rev_count = CaseRevision.query.filter_by(history_id=history_record.id).count()
            if rev_count == 0:
                v1 = CaseRevision(
                    history_id=history_record.id,
                    user_id=history_record.user_id,
                    revision_number=1,
                    action="create",
                    changes_summary="[]",
                    full_snapshot=history_record.form_data,
                    comment="สร้างเอกสารฉบับแรก (Initial Report)",
                    timestamp=history_record.timestamp
                )
                db.session.add(v1)
                db.session.commit()
                rev_count = 1

            if photo_cleared:
                history_record.photo_data = None
                SpecimenPhoto.query.filter_by(history_id=history_record.id).delete()
            elif photos or photo_raw:
                target_photos = photos if photos else ([photo_raw] if photo_raw else [])
                history_record.photo_data = target_photos[0] if target_photos else None
                SpecimenPhoto.query.filter_by(history_id=history_record.id).delete()
                for idx, p_str in enumerate(target_photos):
                    if p_str and len(str(p_str).strip()) > 20:
                        db.session.add(SpecimenPhoto(
                            history_id=history_record.id,
                            photo_data=str(p_str).strip(),
                            photo_index=idx
                        ))

            if audio_cleared:
                history_record.audio_filename = None
            elif audio_clips:
                history_record.audio_filename = audio_clips[-1].get("filename", "")
            elif audio_fn:
                history_record.audio_filename = audio_fn

            if diff_list:
                current_revision = rev_count + 1
                history_record.surgical_number = s_no
                history_record.form_data = json.dumps(data)
                history_record.timestamp = get_thai_time()

                new_rev = CaseRevision(
                    history_id=history_record.id,
                    user_id=user_id,
                    revision_number=current_revision,
                    action="update",
                    changes_summary=json.dumps(diff_list, ensure_ascii=False),
                    full_snapshot=json.dumps(data, ensure_ascii=False),
                    comment=f"แก้ไขข้อมูล {len(diff_list)} จุด",
                    timestamp=get_thai_time()
                )
                db.session.add(new_rev)
                db.session.commit()
            else:
                current_revision = rev_count
                history_record.form_data = json.dumps(data)
                db.session.commit()

            try:
                import shutil
                shutil.copy(pdf_path, Config.OUTPUT_DIR / f"case_{history_record.id}.pdf")
                shutil.copy(docx_path, Config.OUTPUT_DIR / f"case_{history_record.id}.docx")
                from scripts.sync_databases import shadow_sync_case_to_sqlite
                shadow_sync_case_to_sqlite(
                    case_id=history_record.id,
                    user_id=user_id,
                    surgical_number=s_no,
                    form_data=data,
                    audio_filename=history_record.audio_filename,
                    photo_data=history_record.photo_data,
                    timestamp=history_record.timestamp,
                    is_deleted=history_record.is_deleted,
                    deleted_at=history_record.deleted_at,
                    photos=history_record.photo_list
                )
            except Exception as fe:
                print(f"[REVISION FILE COPY / SHADOW SYNC NOTE] {fe}")

        else:
            history_record = FormHistory(
                user_id=user_id,
                surgical_number=s_no,
                form_data=json.dumps(data),
                audio_filename=(audio_clips[-1].get("filename") if audio_clips else audio_fn) if not audio_cleared else None,
                photo_data=(photos[0] if photos else photo_raw) if not photo_cleared else None,
                timestamp=get_thai_time()
            )
            db.session.add(history_record)
            db.session.commit()

            if not photo_cleared and (photos or photo_raw):
                target_photos = photos if photos else ([photo_raw] if photo_raw else [])
                for idx, p_str in enumerate(target_photos):
                    if p_str and len(str(p_str).strip()) > 20:
                        db.session.add(SpecimenPhoto(
                            history_id=history_record.id,
                            photo_data=str(p_str).strip(),
                            photo_index=idx
                        ))
                db.session.commit()

            v1 = CaseRevision(
                history_id=history_record.id,
                user_id=user_id,
                revision_number=1,
                action="create",
                changes_summary="[]",
                full_snapshot=json.dumps(data, ensure_ascii=False),
                comment="สร้างเอกสารฉบับแรก (Initial Report)",
                timestamp=get_thai_time()
            )
            db.session.add(v1)
            db.session.commit()
            current_revision = 1

            try:
                import shutil
                shutil.copy(pdf_path, Config.OUTPUT_DIR / f"case_{history_record.id}.pdf")
                shutil.copy(docx_path, Config.OUTPUT_DIR / f"case_{history_record.id}.docx")
                from scripts.sync_databases import shadow_sync_case_to_sqlite
                shadow_sync_case_to_sqlite(
                    case_id=history_record.id,
                    user_id=user_id,
                    surgical_number=s_no,
                    form_data=data,
                    audio_filename=history_record.audio_filename,
                    photo_data=history_record.photo_data,
                    timestamp=history_record.timestamp,
                    is_deleted=history_record.is_deleted,
                    deleted_at=history_record.deleted_at,
                    photos=history_record.photo_list
                )
            except Exception as fe:
                print(f"[NEW CASE FILE COPY / SHADOW SYNC NOTE] {fe}")

        if history_record:
            try:
                from src.flywheel.collector import capture_audio_training_pair
                initial_stt = form_data.get("transcription") or form_data.get("transcription_text") or ""
                capture_audio_training_pair(
                    app=current_app._get_current_object(),
                    history_id=history_record.id,
                    surgical_number=s_no,
                    audio_clips=audio_clips or ([{"filename": audio_fn}] if audio_fn else []),
                    form_data=data,
                    initial_stt_text=initial_stt
                )
            except Exception as fwe:
                print(f"[Flywheel Trigger Note] {fwe}")

    except Exception as e:
        db.session.rollback()
        print(f"[DB ERROR] Could not save history/revision: {e}")

    photo_to_render = (history_record.photo_data if history_record and history_record.photo_data else photo_raw) if not photo_cleared else ""
    photos_to_render = (history_record.photo_list if history_record else photos) if not photo_cleared else []
    audio_to_render = (history_record.audio_filename if history_record and history_record.audio_filename else audio_fn) if not audio_cleared else ""
    audio_clips_to_render = (history_record.audio_clip_list if history_record else audio_clips) if not audio_cleared else []
    return render_template("index.html", 
                           pdf_filename=pdf_filename, 
                           docx_filename=docx_filename,
                           transcription=form_data.get("transcription"),
                           audio_filename=audio_to_render,
                           audio_clips=audio_clips_to_render,
                           audio_clips_json=json.dumps(audio_clips_to_render, ensure_ascii=False),
                           photo_data=photo_to_render,
                           photos=photos_to_render,
                           photos_json=json.dumps(photos_to_render, ensure_ascii=False),
                           data=data, flags=flags,
                           is_new_case=False,
                           loaded_history_id=history_record.id if history_record else None,
                           loaded_surgical_no=history_record.surgical_number if history_record else None,
                           diff_list=diff_list,
                           revision_number=current_revision)


@cases_bp.route("/api/case/<int:history_id>/revisions")
@login_required
def get_case_revisions(history_id):
    history_record = FormHistory.query.get_or_404(history_id)
    revisions = CaseRevision.query.filter_by(history_id=history_id).order_by(CaseRevision.revision_number.desc()).all()

    if not revisions:
        v1 = CaseRevision(
            history_id=history_record.id,
            user_id=history_record.user_id,
            revision_number=1,
            action="create",
            changes_summary="[]",
            full_snapshot=history_record.form_data,
            comment="สร้างเอกสารฉบับแรก (Initial Report)",
            timestamp=history_record.timestamp
        )
        db.session.add(v1)
        db.session.commit()
        revisions = [v1]

    result = []
    for r in revisions:
        author = User.query.get(r.user_id) if r.user_id else None
        author_name = author.name or author.username if author else "Staff"
        changes = []
        try:
            changes = json.loads(r.changes_summary)
        except Exception:
            changes = []
        result.append({
            "revision_number": r.revision_number,
            "action": r.action,
            "author": author_name,
            "timestamp": r.timestamp.strftime("%d/%m/%Y %H:%M:%S") if r.timestamp else "-",
            "comment": r.comment or "",
            "changes_count": len(changes),
            "changes": changes
        })

    return jsonify({
        "status": "success",
        "case_id": history_id,
        "surgical_number": history_record.surgical_number or "-",
        "total_revisions": len(result),
        "revisions": result
    })


@cases_bp.route("/api/case/<int:history_id>/photo")
@login_required
def get_case_photo(history_id):
    history_record = FormHistory.query.get_or_404(history_id)
    if not current_user.check_is_admin and history_record.user_id != current_user.id:
        return "Unauthorized", 403

    index = request.args.get("index", 0, type=int)
    photos = history_record.photo_list
    photo_str = ""
    if photos and 0 <= index < len(photos):
        photo_str = photos[index]
    elif not photos and history_record.photo_data:
        photo_str = history_record.photo_data
    elif not photos:
        try:
            d = json.loads(history_record.form_data)
            photo_str = d.get("photo_data", "")
        except Exception:
            pass

    if not photo_str:
        return "No photo found for this case", 404

    import base64
    mime_type = "image/jpeg"
    if "," in photo_str:
        header, b64_body = photo_str.split(",", 1)
        if "image/png" in header:
            mime_type = "image/png"
        elif "image/webp" in header:
            mime_type = "image/webp"
    else:
        b64_body = photo_str

    try:
        img_bytes = base64.b64decode(b64_body)
    except Exception as e:
        return f"Invalid photo data: {e}", 400

    resp = make_response(img_bytes)
    resp.headers["Content-Type"] = mime_type
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@cases_bp.route("/api/case/<int:history_id>/delete", methods=["POST"])
@login_required
def api_delete_case(history_id):
    history_record = FormHistory.query.get_or_404(history_id)
    if not current_user.check_is_admin and history_record.user_id != current_user.id:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    history_record.soft_delete()

    rev_num = history_record.latest_revision_number + 1
    rev = CaseRevision(
        history_id=history_record.id,
        user_id=current_user.id,
        revision_number=rev_num,
        action="delete",
        changes_summary=json.dumps([{"field": "is_deleted", "old": False, "new": True}], ensure_ascii=False),
        full_snapshot=history_record.form_data,
        comment=f"ลบเคส (Soft Delete โดย {current_user.name or current_user.username})",
        timestamp=get_thai_time()
    )
    db.session.add(rev)
    db.session.commit()

    try:
        from scripts.sync_databases import shadow_sync_case_to_sqlite
        shadow_sync_case_to_sqlite(
            case_id=history_record.id,
            user_id=history_record.user_id,
            surgical_number=history_record.surgical_number,
            form_data=history_record.form_data,
            audio_filename=history_record.audio_filename,
            photo_data=history_record.photo_data,
            timestamp=history_record.timestamp,
            is_deleted=True,
            deleted_at=history_record.deleted_at,
            photos=history_record.photo_list
        )
    except Exception as se:
        print(f"[SHADOW SYNC DELETE NOTE] {se}")

    return jsonify({"success": True, "message": f"Case #{history_id} marked as deleted (soft delete).", "case_id": history_id})


@cases_bp.route("/api/case/<int:history_id>/restore", methods=["POST"])
@login_required
def api_restore_case(history_id):
    history_record = FormHistory.query.get_or_404(history_id)
    if not current_user.check_is_admin and history_record.user_id != current_user.id:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    history_record.restore()

    rev_num = history_record.latest_revision_number + 1
    rev = CaseRevision(
        history_id=history_record.id,
        user_id=current_user.id,
        revision_number=rev_num,
        action="restore",
        changes_summary=json.dumps([{"field": "is_deleted", "old": True, "new": False}], ensure_ascii=False),
        full_snapshot=history_record.form_data,
        comment=f"กู้คืนเคส (Restore โดย {current_user.name or current_user.username})",
        timestamp=get_thai_time()
    )
    db.session.add(rev)
    db.session.commit()

    try:
        from scripts.sync_databases import shadow_sync_case_to_sqlite
        shadow_sync_case_to_sqlite(
            case_id=history_record.id,
            user_id=history_record.user_id,
            surgical_number=history_record.surgical_number,
            form_data=history_record.form_data,
            audio_filename=history_record.audio_filename,
            photo_data=history_record.photo_data,
            timestamp=history_record.timestamp,
            is_deleted=False,
            deleted_at=None,
            photos=history_record.photo_list
        )
    except Exception as se:
        print(f"[SHADOW SYNC RESTORE NOTE] {se}")

    return jsonify({"success": True, "message": f"Case #{history_id} restored successfully.", "case_id": history_id})
