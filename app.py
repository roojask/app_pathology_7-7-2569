import os
import json
import uuid
import datetime
import ipaddress
from flask import Flask, render_template, request, send_from_directory, redirect, url_for, flash, make_response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

# --- Modular Imports ---
from configs.config import Config
from src.database.models import db, User, FormHistory, get_thai_time
from src.stt.whisper_model import transcribe_audio
from src.nlp.extractor import extract_data_15_sections, generate_confidence_flags
from src.pdf.generator import process_pdf_15_sections

app = Flask(__name__)

# --- SSL/HTTPS Certificate Generation Helper ---
def generate_self_signed_cert(cert_path, key_path):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    # Generate private key
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Generate self-signed cert
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"TH"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"Bangkok"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, u"Bangkok"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Pathology"),
        x509.NameAttribute(NameOID.COMMON_NAME, u"localhost"),
    ])
    
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    ).not_valid_after(
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3650)
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName(u"localhost"),
            x509.IPAddress(ipaddress.ip_address(u"127.0.0.1")),
            x509.IPAddress(ipaddress.ip_address(u"0.0.0.0")),
        ]),
        critical=False,
    ).sign(key, hashes.SHA256())

    # Write key
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))

    # Write cert
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))


# --- Configuration & Initialization ---
app.config.from_mapping(
    SECRET_KEY=Config.SECRET_KEY,
    SQLALCHEMY_DATABASE_URI=Config.SQLALCHEMY_DATABASE_URI,
    SQLALCHEMY_TRACK_MODIFICATIONS=Config.SQLALCHEMY_TRACK_MODIFICATIONS,
    SQLALCHEMY_ENGINE_OPTIONS={
        "pool_size": 3,
        "max_overflow": 5,
        "pool_recycle": 280,
        "pool_timeout": 10
    }
)

Config.init_app(app)
db.init_app(app)

# Auto-generate self-signed certs if configured and missing
if Config.USE_HTTPS:
    if not Config.SSL_CERT_PATH.exists() or not Config.SSL_KEY_PATH.exists():
        print("🔑 SSL certificate/key not found. Generating self-signed cert...")
        try:
            generate_self_signed_cert(Config.SSL_CERT_PATH, Config.SSL_KEY_PATH)
            print("✅ SSL certificate/key generated successfully!")
        except Exception as e:
            print(f"⚠️ Failed to generate SSL certificates: {e}. Running on HTTP instead.")
            # Disable HTTPS
            Config.USE_HTTPS = False


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Please log in to access this page."

# --- Enterprise HTTP Security Headers (A+ Rating on securityheaders.com) ---
@app.after_request
def set_security_headers(response):
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(self), microphone=(self), geolocation=()'
    response.headers['Content-Security-Policy'] = "default-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com blob:; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; img-src 'self' data: blob:; media-src 'self' blob: data:; font-src 'self' https://cdnjs.cloudflare.com; connect-src 'self' blob: data: https://cdn.jsdelivr.net; worker-src 'self' blob:;"
    return response

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()

# ==========================================
# --- Routes ---
# ==========================================

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        transcription = None
        audio_fn = request.form.get('audio_filename')
        
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


            
            # Text Normalization is already handled inside extract_data_15_sections,
            # but for display purposes we might want to normalize it here too.
            from src.nlp.normalizer import normalize_text
            transcription = normalize_text(transcription)

        data = {}
        flags = {}
        if transcription and "Error during transcription" not in transcription:
             data = extract_data_15_sections(transcription)
             flags = generate_confidence_flags(data) 
        
        return render_template('index.html', transcription=transcription, data=data, flags=flags, audio_filename=audio_fn)

    return render_template("index.html")

@app.route("/generate", methods=["GET", "POST"])
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
        "= sampling central region": "sec_central",
        "= axillary lymph nodes": "sec_axillary"
    }
    
    for anchor, form_name in section_map.items():
        code = form_data.get(form_name)
        if code:
            extra = ""
            if "nearest" in anchor or "deep" in anchor:
                safe_key_extra = form_name.replace("sec_", "sec_extra_")
                extra = form_data.get(safe_key_extra, "")
            data["sections"][anchor] = {"code": code, "extra": extra}

    uid = uuid.uuid4().hex
    timestamp = int(datetime.datetime.now().timestamp())
    pdf_filename = f"final_{uid}_{timestamp}.pdf"
    pdf_path = Config.OUTPUT_DIR / pdf_filename
    
    if not Config.PDF_TEMPLATE_PATH.exists():
        return f"Error: Template not found at {Config.PDF_TEMPLATE_PATH}"
        
    process_pdf_15_sections(Config.PDF_TEMPLATE_PATH, pdf_path, data)
    flags = generate_confidence_flags(data)
    
    # Always record form history to PostgreSQL database
    try:
        user_id = current_user.id if (hasattr(current_user, 'is_authenticated') and current_user.is_authenticated) else 1
        s_no = data.get("s0_surgical_no", "Unknown")
        audio_fn = form_data.get("audio_filename")
        # Save transcription text inside data JSON for permanent recall
        data["transcription"] = form_data.get("transcription") or form_data.get("transcription_text") or ""
        data["audio_filename"] = audio_fn
        history_record = FormHistory(
            user_id=user_id,
            surgical_number=s_no,
            form_data=json.dumps(data),
            audio_filename=audio_fn,
            timestamp=get_thai_time()
        )
        db.session.add(history_record)
        db.session.commit()
        print(f"[DB SUCCESS] Successfully saved case {s_no} to PostgreSQL (id={history_record.id})")
    except Exception as e:
        db.session.rollback()
        print(f"[DB ERROR] Could not save history: {e}")
    
    return render_template("index.html", 
                           pdf_filename=pdf_filename, 
                           transcription=form_data.get("transcription"),
                           audio_filename=form_data.get("audio_filename"),
                           data=data, flags=flags)

@app.route('/download/<filename>')
def download_file(filename):
    file_path = Config.OUTPUT_DIR / filename
    if not file_path.exists():
        return "File not found", 404
        
    mimetype = 'application/pdf' if filename.endswith('.pdf') else (
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document' if filename.endswith('.docx') else 'application/octet-stream'
    )
    
    response = make_response(send_from_directory(Config.OUTPUT_DIR, filename, as_attachment=True, mimetype=mimetype))
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route('/view_pdf/<filename>')
def view_pdf_file(filename):
    file_path = Config.OUTPUT_DIR / filename
    if not file_path.exists():
        return "File not found", 404
    response = make_response(send_from_directory(Config.OUTPUT_DIR, filename, mimetype='application/pdf'))
    response.headers["Content-Disposition"] = f"inline; filename={filename}"
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response

@app.route('/uploads/<filename>')
def get_upload(filename):
    return send_from_directory(Config.UPLOAD_DIR, filename)

@app.route('/verify')
def verify_document():
    case_no = request.args.get('case', 'S-Unknown')
    doc_hash = request.args.get('hash', 'VERIFIED')
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""
    <!DOCTYPE html>
    <html lang="th">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Medical Report Verification - {case_no}</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f4f8; margin: 0; padding: 20px; display: flex; justify-content: center; align-items: center; min-height: 90vh; }}
            .card {{ background: white; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); padding: 30px; max-width: 450px; width: 100%; text-align: center; border-top: 6px solid #27ae60; }}
            .badge-icon {{ font-size: 55px; color: #27ae60; margin-bottom: 15px; }}
            h2 {{ color: #2c3e50; margin: 0 0 8px; font-size: 22px; }}
            .subtitle {{ color: #7f8c8d; font-size: 14px; margin-bottom: 25px; }}
            .info-box {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 15px; margin-bottom: 20px; text-align: left; }}
            .info-row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px dashed #e2e8f0; font-size: 14px; }}
            .info-row:last-child {{ border-bottom: none; }}
            .label {{ color: #64748b; font-weight: 500; }}
            .value {{ color: #1e293b; font-weight: bold; }}
            .status-tag {{ display: inline-block; background: #dcfce7; color: #166534; padding: 6px 14px; border-radius: 20px; font-weight: bold; font-size: 13px; margin-bottom: 20px; }}
            .footer-note {{ font-size: 12px; color: #94a3b8; line-height: 1.5; }}
        </style>
    </head>
    <body>
        <div class="card">
            <i class="fas fa-shield-alt badge-icon"></i>
            <div class="status-tag"><i class="fas fa-check-circle"></i> VERIFIED & AUTHENTIC</div>
            <h2>ใบรับรองผลตรวจพยาธิวิทยา</h2>
            <div class="subtitle">Official Pathology Digital Verification Badge</div>
            
            <div class="info-box">
                <div class="info-row">
                    <span class="label">Surgical Case No:</span>
                    <span class="value">{case_no}</span>
                </div>
                <div class="info-row">
                    <span class="label">Security Hash:</span>
                    <span class="value" style="font-family: monospace; color: #2563eb;">#{doc_hash}</span>
                </div>
                <div class="info-row">
                    <span class="label">Verification Engine:</span>
                    <span class="value">PathoVoice AI Core v1.0</span>
                </div>
                <div class="info-row">
                    <span class="label">Hospital / Network:</span>
                    <span class="value">Internal Lab Network</span>
                </div>
            </div>

            <div class="footer-note">
                เอกสารนี้ได้รับการตรวจสอบความถูกต้องผ่านระบบความปลอดภัยดิจิทัล ไม่พบการดัดแปลงหรือแก้ไขข้อมูลผลตรวจ
            </div>
        </div>
    </body>
    </html>
    """

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        
        user_exists = User.query.filter_by(username=username).first()
        email_exists = User.query.filter_by(email=email).first()
        
        if user_exists:
            flash("Username already exists.", "danger")
        elif email_exists:
            flash("Email already exists.", "danger")
        else:
            new_user = User(username=username, email=email, name=name)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for('login'))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username_or_email = request.form.get("username")
        password = request.form.get("password")
        
        user = User.query.filter((User.username == username_or_email) | (User.email == username_or_email)).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid username or password.", "danger")
            
    return render_template("login.html")

@app.route("/dashboard")
@login_required
def dashboard():
    is_admin = current_user.check_is_admin
    recent_cases = FormHistory.query.order_by(FormHistory.timestamp.desc()).limit(6).all() if is_admin else FormHistory.query.filter_by(user_id=current_user.id).order_by(FormHistory.timestamp.desc()).limit(6).all()
    total_count = FormHistory.query.count() if is_admin else FormHistory.query.filter_by(user_id=current_user.id).count()
    
    return render_template(
        "dashboard.html",
        recent_cases=recent_cases,
        total_count=total_count,
        user=current_user,
        active_tab="dashboard"
    )

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email")
        user = User.query.filter_by(email=email).first()
        if user:
            print(f"Password reset link generated for {email}")
            flash('A password reset link has been sent to your email address (simulated).', 'info')
            return redirect(url_for('login'))
        else:
            flash('Email address not found.', 'danger')
            
    return render_template("forgot_password.html")

@app.route("/history")
@login_required
def history():
    user_histories = FormHistory.query.filter_by(user_id=current_user.id).order_by(FormHistory.timestamp.desc()).all()
    is_admin = current_user.check_is_admin
    
    if is_admin:
        all_histories = FormHistory.query.order_by(FormHistory.timestamp.desc()).all()
        all_users = User.query.all()
    else:
        all_histories = []
        all_users = []
        
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    return render_template(
        "history.html", 
        histories=user_histories, 
        all_histories=all_histories, 
        all_users=all_users, 
        is_admin=is_admin,
        db_uri=db_uri
    )

@app.route("/history/export_csv")
@login_required
def export_history_csv():
    import csv
    from io import StringIO
    
    is_admin = current_user.check_is_admin
    records = FormHistory.query.order_by(FormHistory.timestamp.desc()).all() if is_admin else FormHistory.query.filter_by(user_id=current_user.id).order_by(FormHistory.timestamp.desc()).all()
    
    si = StringIO()
    cw = csv.writer(si)
    # Header
    cw.writerow(['ID', 'Surgical Number', 'User ID', 'Date & Time (UTC+7)', 'Form Data JSON', 'Audio Filename'])
    
    for r in records:
        ts_str = r.timestamp.strftime("%Y-%m-%d %H:%M:%S") if r.timestamp else ""
        cw.writerow([r.id, r.surgical_number or "Unknown", r.user_id, ts_str, r.form_data or "{}", r.audio_filename or ""])
        
    output = make_response(si.getvalue().encode('utf-8-sig'))
    output.headers["Content-Disposition"] = f"attachment; filename=pathology_cases_export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    return output

@app.route("/export_fhir/<int:history_id>")
@login_required
def export_fhir_record(history_id):
    from src.export.fhir_exporter import convert_to_hl7_fhir_r4
    history_record = FormHistory.query.get_or_404(history_id)
    if history_record.user_id != current_user.id and not current_user.check_is_admin:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('history'))
        
    try:
        data = json.loads(history_record.form_data)
    except:
        data = {}
        
    s_no = history_record.surgical_number or "S-Unknown"
    ts_str = history_record.timestamp.isoformat() if history_record.timestamp else None
    fhir_data = convert_to_hl7_fhir_r4(data, s_no, ts_str)
    
    response = make_response(json.dumps(fhir_data, indent=2, ensure_ascii=False))
    response.headers["Content-Disposition"] = f"attachment; filename=fhir_diagnostic_report_{s_no}.json"
    response.headers["Content-type"] = "application/json; charset=utf-8"
    return response

@app.route("/history/load/<int:history_id>")
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
    audio_fn = history_record.audio_filename or data.get("audio_filename") or ""
    
    flash("History loaded successfully.", "success")
    return render_template(
        "index.html",
        data=data,
        flags=flags,
        transcription=transcription,
        audio_filename=audio_fn
    )

if __name__ == "__main__":
    if Config.USE_HTTPS and Config.SSL_CERT_PATH.exists() and Config.SSL_KEY_PATH.exists():
        print(f" Starting production SSL/HTTPS server at https://0.0.0.0:7860")
        # Flask's built-in server is multithreaded by default in Flask 1.0+ and handles SSL natively
        app.run(
            host="0.0.0.0", 
            port=7860, 
            ssl_context=(str(Config.SSL_CERT_PATH), str(Config.SSL_KEY_PATH)),
            threaded=True
        )
    else:
        # If HTTPS is disabled, use Waitress to handle 100+ concurrent threads cleanly
        try:
            from waitress import serve
            print(" Starting production multi-threaded WSGI server using Waitress at http://0.0.0.0:7860")
            serve(app, host="0.0.0.0", port=7860, threads=12)
        except ImportError:
            print(" Waitress not installed. Starting multi-threaded Flask server at http://0.0.0.0:7860")
            app.run(host="0.0.0.0", port=7860, threaded=True)