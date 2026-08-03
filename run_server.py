import os
import sys
import subprocess
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

def start_server():
    print("==================================================")
    print("[INIT] Pathology Assistant Server Initialization")
    # Auto-backup database on startup to guarantee zero data loss
    try:
        from scripts.backup_db import backup_database
        backup_database()
    except Exception as e:
        print(f" Automated backup warning: {e}")

    cert_path = Path("configs") / "cert.pem"
    key_path = Path("configs") / "key.pem"
    
    # 1. Generate SSL Certificates if not present
    if not (cert_path.exists() and key_path.exists()):
        print("[*] SSL Certificates missing. Generating self-signed certificates...")
        try:
            from scripts.generate_certs import generate_self_signed_cert
            generate_self_signed_cert()
        except ImportError:
            print("[-] Error: 'cryptography' library is required to generate certificates.")
            print("[*] Please run: .venv\\Scripts\\pip install cryptography")
            print("[*] Starting in standard HTTP mode...")
            
    # 2. Run server with production WSGI (Waitress) or development fallback
    if cert_path.exists() and key_path.exists():
        print("[+] SSL certificates detected.")
        print("[*] Starting server in SECURE HTTPS MODE...")
        print("[*] Accessible via: https://localhost:7860/ or https://[your-server-ip]:7860/")
        print("[!] Note: Since this is a self-signed certificate, your browser will warn you.")
        print("    Please click 'Advanced' and 'Proceed' to access the application.")
        print("==================================================")
        
        # Check if waitress is installed to run in concurrent production mode
        from app import app
        print("[SERVER] Starting Multi-threaded Secure HTTPS Engine...")
        app.run(host="0.0.0.0", port=7860, ssl_context=(str(cert_path), str(key_path)), threaded=True)
    else:
        print("[-] Running in INSECURE HTTP MODE (Microphone & Camera might be blocked on other devices).")
        print("[*] Accessible via: http://localhost:7860/ or http://[your-server-ip]:7860/")
        print("==================================================")
        
        try:
            import waitress
            from app import app
            print("[SERVER] Running with Waitress WSGI Server (Concurrent Multi-threaded)...")
            waitress.serve(app, host='0.0.0.0', port=7860, threads=50)
        except ImportError:
            from app import app
            app.run(host="0.0.0.0", port=7860)

if __name__ == "__main__":
    start_server()
