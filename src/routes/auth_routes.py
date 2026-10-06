from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required
from src.database.models import db, User

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/register", methods=["GET", "POST"])
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

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # รับชื่อผู้ตรวจ และระดับความซับซ้อนของเคส
        username = request.form.get("username", "").strip()
        case_level = request.form.get("case_level", "Level 1")

        if not username:
            flash("กรุณากรอกชื่อผู้ตรวจ / ผู้บันทึก", "danger")
            return render_template("login.html")

        # ค้นหาผู้ใช้จากชื่อ หากยังไม่มีให้สร้างใหม่อัตโนมัติทันที (ไม่ต้องมีรหัสผ่าน)
        user = User.query.filter((User.username == username) | (User.name == username)).first()
        if not user:
            safe_email = f"{username.lower().replace(' ', '_')}@pathology.local"
            user = User(username=username, name=username, email=safe_email)
            user.set_password("patho1234")  # ตั้งรหัสผ่านเริ่มต้นไว้เบื้องหลังอัตโนมัติ
            db.session.add(user)
            db.session.commit()

        # บันทึกระดับความซับซ้อนของเคสลงใน session เพื่อนำไปใช้งาน
        session['case_level'] = case_level
        session['active_doctor_name'] = username

        # ล็อกอินเข้าใช้งานทันที
        login_user(user, remember=True)
        return redirect(url_for('dashboard'))
    else:
        # Clear any stale non-auth flash messages from session
        if '_flashes' in session:
            session['_flashes'] = [(cat, msg) for cat, msg in session['_flashes'] if 'History' not in msg]
            
    return render_template("login.html")

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('login'))

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
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