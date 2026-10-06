import tkinter as tk
from tkinter import ttk
import threading
import webbrowser
import subprocess
import time
import sys
import os

# ดึงแอปพลิเคชันจาก app.py
from app import app

SERVER_PORT = int(os.environ.get("PORT", 5000))
SERVER_URL = f"http://127.0.0.1:{SERVER_PORT}"

def run_flask():
    """รัน Server Flask ใน Background Thread"""
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host="127.0.0.1", port=SERVER_PORT, debug=False, use_reloader=False)

def find_app_mode_browser():
    """ค้นหา Browser ในเครื่องเพื่อเปิดในโหมด Desktop App (ไม่มีแถบ URL / แท็บ)"""
    candidate_paths = [
        # Microsoft Edge (มีทุกเครื่องใน Windows 10/11)
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
        # Google Chrome
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for path in candidate_paths:
        if os.path.exists(path):
            return path
    return None

class PathologyLauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Pathology Voice Assistant - Controller")
        self.root.geometry("460x320")
        self.root.resizable(False, False)
        self.root.configure(bg="#181825")

        # จัดให้อยู่กึ่งกลางหน้าจอ
        self.center_window()

        # ส่วนหัวข้อโปรแกรม
        title_label = tk.Label(
            root, 
            text="🔬 Pathology Assistant", 
            font=("Segoe UI", 18, "bold"), 
            fg="#cdd6f4", 
            bg="#181825"
        )
        title_label.pack(pady=(35, 10))

        subtitle_label = tk.Label(
            root, 
            text="ระบบผู้ช่วยบันทึกผลพยาธิวิทยา (Desktop Application)", 
            font=("Segoe UI", 10), 
            fg="#a6adc8", 
            bg="#181825"
        )
        subtitle_label.pack(pady=(0, 15))

        # ป้ายสถานะ
        self.status_label = tk.Label(
            root, 
            text="⏳ กำลังเตรียมระบบ...", 
            font=("Segoe UI", 11), 
            fg="#fab387", 
            bg="#181825"
        )
        self.status_label.pack(pady=10)

        # ปุ่มเปิดหน้าต่างโปรแกรม (รอให้ระบบพร้อมแล้วจะกดได้)
        self.open_btn = tk.Button(
            root,
            text="🚀 เริ่มใช้งานโปรแกรม",
            font=("Segoe UI", 12, "bold"),
            bg="#89b4fa",
            fg="#11111b",
            activebackground="#b4befe",
            cursor="hand2",
            state=tk.DISABLED,
            command=self.open_app_window,
            relief=tk.FLAT,
            padx=25,
            pady=8
        )
        self.open_btn.pack(pady=15)

        # ปุ่มปิดโปรแกรมทั้งหมด
        exit_btn = tk.Button(
            root,
            text="ปิดโปรแกรมทั้งหมด",
            font=("Segoe UI", 9),
            bg="#313244",
            fg="#a6adc8",
            activebackground="#45475a",
            relief=tk.FLAT,
            command=self.on_closing
        )
        exit_btn.pack(pady=5)

        # เมื่อกดกากบาท [X] ที่มุมขวาบน
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # สตาร์ทเซิร์ฟเวอร์ใน Background Thread
        self.server_thread = threading.Thread(target=run_flask, daemon=True)
        self.server_thread.start()

        # หน่วงเวลา 2 วินาทีเพื่อให้เซิร์ฟเวอร์พร้อม แล้วปลดล็อคปุ่มให้กด
        self.root.after(2000, self.ready)

    def center_window(self):
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def ready(self):
        # เมื่อเซิร์ฟเวอร์พร้อม จะเปลี่ยนสถานะเป็นสีเขียว และปลดล็อคปุ่ม
        # (ไม่สั่งเปิดหน้าต่างอัตโนมัติแล้ว ให้รอผู้ใช้กดปุ่มเอง)
        self.status_label.config(text="🟢 ระบบพร้อมใช้งานแล้ว (Offline Mode)", fg="#a6e3a1")
        self.open_btn.config(state=tk.NORMAL)

    def open_app_window(self):
        """เปิดหน้าต่างโปรแกรมเฉพาะตอนที่ผู้ใช้กดปุ่มนี้"""
        browser_exe = find_app_mode_browser()
        if browser_exe:
            # ใช้พารามิเตอร์ --app= เพื่อเปิดเป็นหน้าต่างโปรแกรมเดี่ยวๆ (Native App Mode)
            subprocess.Popen([browser_exe, f"--app={SERVER_URL}", "--start-maximized"])
        else:
            webbrowser.open(SERVER_URL)

    def on_closing(self):
        """ปิดโปรแกรมและเคลียร์โปรเซสทั้งหมดออกจากระบบ"""
        self.root.destroy()
        os._exit(0)

if __name__ == "__main__":
    root = tk.Tk()
    app_launcher = PathologyLauncherApp(root)
    root.mainloop()