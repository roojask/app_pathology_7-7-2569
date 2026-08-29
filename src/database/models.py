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
    timestamp = db.Column(db.DateTime, default=get_thai_time)


class AudioTask(db.Model):
    __tablename__ = 'audio_task'
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    file_path = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending, processing, completed, failed
    result_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=get_thai_time)
    updated_at = db.Column(db.DateTime, default=get_thai_time, onupdate=get_thai_time)


