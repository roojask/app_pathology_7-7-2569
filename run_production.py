import os
import sys
from pathlib import Path
from waitress import serve
from app import app
from configs.config import Config

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    threads = int(os.environ.get("THREADS", 8))
    
    print("=" * 68)
    print("  PATHO VOICE ASSISTANT - PRODUCTION WSGI SERVER (Waitress)")
    print(f"  [+] Host: 0.0.0.0 | Port: {port}")
    print(f"  [+] Multi-threading Worker Threads: {threads}")
    print(f"  [+] Database Engine: PostgreSQL 18 (pathology_db)")
    print(f"  [+] Security: Production WSGI (Non-Docker High-Performance)")
    print(f"  [+] Status: READY FOR HOSPITAL / LAB NETWORK DEPLOYMENT")
    print("=" * 68)
    
    serve(app, host="0.0.0.0", port=port, threads=threads)
