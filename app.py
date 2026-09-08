import os
import datetime
import ipaddress
from flask import Flask
from flask_login import LoginManager

# --- Modular Imports ---
from configs.config import Config
from src.database.models import db, User
from src.routes import register_blueprints

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

# Register modular blueprints with backward-compatible endpoint aliases
register_blueprints(app)

with app.app_context():
    db.create_all()


if __name__ == "__main__":
    if Config.USE_HTTPS and Config.SSL_CERT_PATH.exists() and Config.SSL_KEY_PATH.exists():
        print(" Starting production SSL/HTTPS server at https://0.0.0.0:7860")
        app.run(
            host="0.0.0.0", 
            port=7860, 
            ssl_context=(str(Config.SSL_CERT_PATH), str(Config.SSL_KEY_PATH)),
            threaded=True
        )
    else:
        try:
            from waitress import serve
            print(" Starting production multi-threaded WSGI server using Waitress at http://0.0.0.0:7860")
            serve(app, host="0.0.0.0", port=7860, threads=12)
        except ImportError:
            print(" Waitress not installed. Starting multi-threaded Flask server at http://0.0.0.0:7860")
            app.run(host="0.0.0.0", port=7860, threaded=True)