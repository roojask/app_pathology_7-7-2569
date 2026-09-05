import datetime
from datetime import timezone, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

THAILAND_TZ = timezone(timedelta(hours=7))

def get_thai_time():
    return datetime.datetime.now(THAILAND_TZ).replace(tzinfo=None)

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(150), nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    histories = db.relationship('FormHistory', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def check_is_admin(self):
        if getattr(self, 'is_admin', False):
            return True
        if self.username and self.username.lower() in ['admin', 'administrator', 'root']:
            return True
        return False

class FormHistory(db.Model):
    __tablename__ = 'form_history'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    surgical_number = db.Column(db.String(100), nullable=True)
    form_data = db.Column(db.Text, nullable=False) # Store JSON string of data dict
    audio_filename = db.Column(db.String(200), nullable=True) # Unique audio filename
    photo_data = db.Column(db.Text, nullable=True) # Base64 JPEG stored directly in DB
    timestamp = db.Column(db.DateTime, default=get_thai_time)

    @property
    def latest_revision_number(self):
        if self.revisions:
            return self.revisions[-1].revision_number
        return 1

    @property
    def has_photo(self):
        if self.photo_data and len(self.photo_data.strip()) > 20:
            return True
        try:
            import json
            d = json.loads(self.form_data)
            return bool(d.get("photo_data"))
        except Exception:
            return False

    @property
    def photo_url(self):
        if self.has_photo:
            return f"/api/case/{self.id}/photo"
        return None


class CaseRevision(db.Model):
    __tablename__ = 'case_revision'
    id = db.Column(db.Integer, primary_key=True)
    history_id = db.Column(db.Integer, db.ForeignKey('form_history.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    revision_number = db.Column(db.Integer, default=1)
    action = db.Column(db.String(50), default="update") # 'create', 'update'
    changes_summary = db.Column(db.Text, nullable=True) # JSON list of changed fields
    full_snapshot = db.Column(db.Text, nullable=True) # JSON snapshot of form_data
    comment = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, default=get_thai_time)

    case = db.relationship('FormHistory', backref=db.backref('revisions', lazy=True, order_by='CaseRevision.revision_number.asc()'))
    author = db.relationship('User', backref=db.backref('case_revisions', lazy=True))

    @property
    def revision_label(self):
        return f"v{self.revision_number}"



class AudioTask(db.Model):
    __tablename__ = 'audio_task'
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    file_path = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending, processing, completed, failed
    result_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=get_thai_time)
    updated_at = db.Column(db.DateTime, default=get_thai_time, onupdate=get_thai_time)


