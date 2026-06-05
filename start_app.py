"""
Archer Harvest — Desktop Launcher
Elegant dark-themed app window with embedded terminal console,
server lifecycle management, and browser auto-launch.
"""

import os
import sys
import math
import queue
import time
import datetime
import threading
import webbrowser
from pathlib import Path
from tkinter import Canvas

if getattr(sys, 'frozen', False):
    PROJECT_DIR = Path(sys._MEIPASS)
else:
    PROJECT_DIR = Path(__file__).parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

# Enable High-DPI awareness on Windows before UI loads
if os.name == 'nt':
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

import customtkinter as ctk

ctk.set_appearance_mode("dark")

# ── Window constants ──
WIN_W = 500
WIN_H = 540
EXPANDED_W = 1000
CANVAS_H = 220

# ── Palette ──
NEON_CYAN = "#00E8D4"
NEON_VIOLET = "#A855F7"
MUTED_TEXT = "#8B9BB4"
PANEL_BG = "#101820"
PANEL_BORDER = "#1a2e40"
INPUT_BG = "#0b121c"
BG_DARK = "#020208"


# ═══════════════════════════════════════════════════
# Thread-Safe Console Log Queue
# ═══════════════════════════════════════════════════
class LogQueue:
    def __init__(self):
        self.queue = queue.Queue()
        self._at_line_start = True

    def write(self, text):
        if not text:
            return
        parts = text.split('\n')
        processed = []
        for i, part in enumerate(parts):
            if i > 0:
                processed.append('\n')
                self._at_line_start = True
            if part:
                if self._at_line_start:
                    ts = datetime.datetime.now().strftime("%H:%M:%S")
                    processed.append(f"[{ts}] ")
                    self._at_line_start = False
                processed.append(part)
        self.queue.put("".join(processed))

    def flush(self):
        pass


class StreamRedirector:
    def __init__(self, original, log_q):
        self.original = original
        self.log_q = log_q

    @property
    def encoding(self):
        return getattr(self.original, 'encoding', 'utf-8')

    def write(self, text):
        if self.original:
            try:
                self.original.write(text)
            except Exception:
                pass
        self.log_q.write(text)

    def flush(self):
        if self.original:
            try:
                self.original.flush()
            except Exception:
                pass

    def reconfigure(self, *args, **kwargs):
        if self.original and hasattr(self.original, 'reconfigure'):
            try:
                self.original.reconfigure(*args, **kwargs)
            except Exception:
                pass


# ═══════════════════════════════════════════════════
# Embedded Terminal Widget
# ═══════════════════════════════════════════════════
class EmbeddedTerminal(ctk.CTkFrame):
    """Glassmorphic dark terminal panel with syntax-colored log output."""
    def __init__(self, parent, log_q, **kwargs):
        kwargs.setdefault("fg_color", "#161622")
        kwargs.setdefault("border_color", "#202030")
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("corner_radius", 14)
        super().__init__(parent, **kwargs)
        self.pack_propagate(False)
        self.log_q = log_q

        # Title bar
        title_bar = ctk.CTkFrame(self, fg_color="#0f0f18", height=28, corner_radius=0)
        title_bar.pack(fill="x", side="top")

        dots = ctk.CTkFrame(title_bar, fg_color="transparent")
        dots.pack(side="left", padx=10, pady=8)
        for c in ["#ff5f56", "#ffbd2e", "#27c93f"]:
            d = ctk.CTkFrame(dots, fg_color=c, width=10, height=10, corner_radius=5)
            d.pack(side="left", padx=3)

        ctk.CTkLabel(
            title_bar, text="server-logs",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color="#6b6b8b"
        ).pack(side="left", padx=(14, 0))

        # Accent line
        ctk.CTkFrame(self, fg_color=NEON_CYAN, height=1).pack(fill="x", side="top")

        # Text area
        self.text = ctk.CTkTextbox(
            self, fg_color="#161622", text_color="#cfcff0",
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="word", border_width=0
        )
        self.text.pack(expand=True, fill="both", padx=12, pady=(8, 12))

        tw = self.text._textbox
        tw.tag_config("success", foreground="#00ffcc")
        tw.tag_config("error", foreground="#ff4d79")
        tw.tag_config("warning", foreground="#fbbf24")
        tw.tag_config("info", foreground="#818cf8")

        # Initial boot text
        self.text.configure(state="normal")
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.text.insert("end", f"[{ts}] archer-harvest:~ $ ./start_server.sh\n")
        self.text.insert("end", f"[{ts}] SERVER LOGS INITIATED\n")
        self.text.insert("end", f"[{ts}] {'=' * 42}\n\n")
        self._colorize("1.0", "end")
        self.text.configure(state="disabled")
        self._poll()

    def _colorize(self, start, end):
        try:
            content = self.text.get(start, end)
            lines = content.split('\n')
            start_line = int(start.split('.')[0])
            for i, line in enumerate(lines):
                ln = start_line + i
                if any(k in line for k in ["SUCCESS", "start_server.sh", "INITIATED"]):
                    self.text.tag_add("success", f"{ln}.0", f"{ln}.end")
                elif any(k in line for k in ["ERROR", "CRITICAL", "Exception", "Traceback"]):
                    self.text.tag_add("error", f"{ln}.0", f"{ln}.end")
                elif any(k in line for k in ["WARNING", "UserWarning"]):
                    self.text.tag_add("warning", f"{ln}.0", f"{ln}.end")
                elif any(k in line for k in ["INFO", "GET /", "POST /", "Application startup"]):
                    self.text.tag_add("info", f"{ln}.0", f"{ln}.end")
        except Exception:
            pass

    def _poll(self):
        added = False
        while True:
            try:
                msg = self.log_q.queue.get_nowait()
                self.text.configure(state="normal")
                s_idx = self.text.index("end-1c")
                self.text.insert("end", msg)
                e_idx = self.text.index("end-1c")
                self._colorize(s_idx, e_idx)
                self.text.configure(state="disabled")
                added = True
            except queue.Empty:
                break
        if added:
            self.text.see("end")
        self.after(50, self._poll)


# ═══════════════════════════════════════════════════
# Main Launcher Window
# ═══════════════════════════════════════════════════
class ArcherHarvestLauncher(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.server_running = False
        self.server_thread = None
        self.anim_frame = 0
        self.log_q = LogQueue()
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        self._expanding = False
        self._expanded = False
        self.terminal = None

        self.title("Archer Harvest")
        self.geometry(f"{WIN_W}x{WIN_H}")
        try:
            import ctypes
            myappid = 'archer.harvest.app.1.0'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            # Use iconbitmap with high-quality multi-size ICO.
            # Coupled with DPI awareness (set in main), this ensures crisp taskbar icons.
            self.iconbitmap(str(PROJECT_DIR / "Logo" / "Archer_Harvest_256X256.ico"))
        except Exception as e:
            pass
        self.resizable(False, False)
        self.configure(fg_color=BG_DARK)

        # Center on screen
        self.update_idletasks()
        sx = (self.winfo_screenwidth() - WIN_W) // 2
        sy = (self.winfo_screenheight() - WIN_H) // 2
        self.geometry(f"{WIN_W}x{WIN_H}+{sx}+{sy}")

        scaling = self._get_window_scaling()
        from launcher_visuals import LauncherVisualEngine, PlasmaSeparator
        self.visual_engine = LauncherVisualEngine(WIN_W, CANVAS_H, scaling)

        # Animated background canvas
        self.bg_canvas = Canvas(self, highlightthickness=0, bg=BG_DARK)
        self.bg_canvas.place(x=0, y=0, relwidth=1.0, height=int(CANVAS_H * scaling))

        # Branding overlay on canvas
        self._draw_branding(scaling)

        # Plasma separator
        self.plasma = PlasmaSeparator(self, width=WIN_W, height=3, scaling=scaling)
        self.plasma.place(x=0, y=int((CANVAS_H - 2) * scaling))

        # Control card
        self._build_controls()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._animate()

    def _draw_branding(self, scaling):
        """Draw the app title and subtitle on the canvas after first render."""
        def _overlay():
            cx = int(WIN_W * scaling) // 2
            cy = int(CANVAS_H * scaling) // 2
            self.bg_canvas.create_text(
                cx, cy - 18, text="Archer Harvest",
                font=("Segoe UI", 22, "bold"), fill="#ffffff",
                tags="brand"
            )
            self.bg_canvas.create_text(
                cx, cy + 14, text="Market Data Downloader",
                font=("Segoe UI", 10), fill=NEON_CYAN,
                tags="brand"
            )
            # Decorative pulse-line icon
            lx = cx - 130
            ly = cy - 14
            self.bg_canvas.create_line(
                lx, ly, lx + 12, ly - 10, lx + 20, ly + 8, lx + 30, ly - 16,
                fill=NEON_CYAN, width=2, smooth=True, tags="brand"
            )
        self.after(100, _overlay)

    def _build_controls(self):
        card = ctk.CTkFrame(
            self, fg_color=PANEL_BG, corner_radius=24,
            border_width=2, border_color=PANEL_BORDER,
            width=476, height=290
        )
        card.place(x=12, y=230)
        card.pack_propagate(False)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(expand=True, fill="both", padx=16, pady=14)

        # ── Status Bar ──
        self.status_card = ctk.CTkFrame(
            inner, fg_color="#172330", corner_radius=12,
            border_width=1.5, border_color="#1e2e45", height=42
        )
        self.status_card.pack(fill="x", pady=(0, 12))
        self.status_card.pack_propagate(False)

        status_inner = ctk.CTkFrame(self.status_card, fg_color="transparent")
        status_inner.pack(fill="both", expand=True, padx=12, pady=4)

        self.status_dot = ctk.CTkLabel(
            status_inner, text="((●))",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#6B7280"
        )
        self.status_dot.pack(side="left", padx=(0, 8))

        self.status_text = ctk.CTkLabel(
            status_inner, text="Ready to launch",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=12),
            text_color=MUTED_TEXT
        )
        self.status_text.pack(side="left")

        self.progress = ctk.CTkProgressBar(
            self.status_card, height=4,
            progress_color=NEON_CYAN, fg_color=INPUT_BG
        )
        self.progress.set(0)
        self.progress.pack(side="bottom", fill="x", padx=12, pady=(0, 4))

        # ── Server URL display ──
        url_frame = ctk.CTkFrame(inner, fg_color="transparent")
        url_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            url_frame, text="SERVER ADDRESS",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=9),
            text_color=MUTED_TEXT
        ).pack(anchor="w", padx=2)

        self.url_entry = ctk.CTkEntry(
            url_frame,
            font=ctk.CTkFont(family="Consolas", size=12),
            height=32, fg_color="#172330", border_color=PANEL_BORDER,
            text_color=NEON_CYAN, corner_radius=8
        )
        self.url_entry.insert(0, "http://127.0.0.1:8000")
        self.url_entry.configure(state="readonly")
        self.url_entry.pack(fill="x", pady=(2, 0))

        # ── Info row ──
        info_frame = ctk.CTkFrame(inner, fg_color="transparent")
        info_frame.pack(fill="x", pady=(0, 12))
        info_frame.columnconfigure(0, weight=1)
        info_frame.columnconfigure(1, weight=1)
        info_frame.columnconfigure(2, weight=1)

        for col, (label, val_id) in enumerate([
            ("API", "api_status"), ("ENGINE", "engine_status"), ("UPTIME", "uptime_val")
        ]):
            cell = ctk.CTkFrame(info_frame, fg_color="#172330", corner_radius=8, height=44)
            cell.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 4, 0))
            cell.pack_propagate(False)
            ctk.CTkLabel(
                cell, text=label,
                font=ctk.CTkFont(family="Segoe UI Semibold", size=8),
                text_color="#555"
            ).pack(anchor="w", padx=8, pady=(4, 0))
            lbl = ctk.CTkLabel(
                cell, text="—",
                font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
                text_color=MUTED_TEXT
            )
            lbl.pack(anchor="w", padx=8)
            setattr(self, f"_{val_id}", lbl)

        # ── Action buttons ──
        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.pack(fill="x")
        btn_frame.columnconfigure(0, weight=6)
        btn_frame.columnconfigure(1, weight=3)
        btn_frame.columnconfigure(2, weight=2)

        self.launch_btn = ctk.CTkButton(
            btn_frame, text="⚡  Start Server",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=40, corner_radius=10,
            fg_color="#062e3d", border_color=NEON_CYAN, border_width=2,
            text_color=NEON_CYAN, hover_color="#0b485c",
            command=self._on_launch
        )
        self.launch_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.open_btn = ctk.CTkButton(
            btn_frame, text="🌐  Open Browser",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            height=40, corner_radius=10,
            fg_color="#172330", border_color=MUTED_TEXT, border_width=1.5,
            text_color=MUTED_TEXT, hover_color="#233549",
            command=self._open_browser, state="disabled"
        )
        self.open_btn.grid(row=0, column=1, sticky="ew", padx=(0, 6))

        self.exit_btn = ctk.CTkButton(
            btn_frame, text="✕",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            height=40, corner_radius=10,
            fg_color="#dc2626", hover_color="#ef4444", text_color="#ffffff",
            command=self._on_close
        )
        self.exit_btn.grid(row=0, column=2, sticky="ew")

        # ── Hover micro-animations ──
        def _hover_in_launch(e):
            if self.launch_btn.cget("state") == "normal":
                self.launch_btn.configure(fg_color="#0b485c")
        def _hover_out_launch(e):
            if self.launch_btn.cget("state") == "normal" and not self.server_running:
                self.launch_btn.configure(fg_color="#062e3d")
        def _hover_in_open(e):
            if self.open_btn.cget("state") == "normal":
                self.open_btn.configure(fg_color="#233549", border_color=NEON_CYAN, text_color=NEON_CYAN)
        def _hover_out_open(e):
            if self.open_btn.cget("state") == "normal":
                self.open_btn.configure(fg_color="#172330", border_color=MUTED_TEXT, text_color=MUTED_TEXT)

        self.launch_btn.bind("<Enter>", _hover_in_launch)
        self.launch_btn.bind("<Leave>", _hover_out_launch)
        self.open_btn.bind("<Enter>", _hover_in_open)
        self.open_btn.bind("<Leave>", _hover_out_open)

        self._server_start_time = None

    # ═══════════════ Animation Loop ═══════════════

    def _animate(self):
        self.anim_frame += 1
        self.visual_engine.draw_frame(self.bg_canvas, self.anim_frame)
        self.plasma.animate()

        # Pulsing status dot
        pulse = 0.5 + 0.5 * math.sin(self.anim_frame * 0.12)
        if self.server_running:
            g = int(212 + 43 * pulse)
            c = int(170 + 85 * pulse)
            color = f"#00{g:02x}{c:02x}"
            self.status_dot.configure(text_color=color)
            self.status_card.configure(border_color=color)
            # Update uptime
            if self._server_start_time:
                elapsed = int(time.time() - self._server_start_time)
                h, remainder = divmod(elapsed, 3600)
                m, s = divmod(remainder, 60)
                self._uptime_val.configure(text=f"{h:02d}:{m:02d}:{s:02d}", text_color=NEON_CYAN)

        self.after(33, self._animate)

    # ═══════════════ Server Lifecycle ═══════════════

    def _on_launch(self):
        if self.server_running:
            self._open_browser()
            return

        self.launch_btn.configure(state="disabled", text="Starting...")
        self.status_text.configure(text="Spinning up server...", text_color=NEON_CYAN)
        self.status_dot.configure(text_color=NEON_CYAN)
        self.progress.set(0.3)

        self._show_terminal()
        threading.Thread(target=self._start_server, daemon=True).start()

    def _start_server(self):
        try:
            import uvicorn
            sys.path.insert(0, str(PROJECT_DIR))
            from main import app

            self.log_q.write("\n[INIT] Starting uvicorn on http://127.0.0.1:8000 ...\n")

            def run():
                try:
                    uvicorn.run(app, host="127.0.0.1", port=8000,
                                log_level="info", log_config=None)
                except Exception as e:
                    self.log_q.write(f"\n[SERVER CRASH] {e}\n")

            self.server_thread = threading.Thread(target=run, daemon=True)
            self.server_thread.start()
            time.sleep(2.5)

            if self.server_thread.is_alive():
                self.server_running = True
                self._server_start_time = time.time()
                self.log_q.write("\n[SUCCESS] Server online at http://127.0.0.1:8000\n")
                self._update_running_state()
                webbrowser.open("http://127.0.0.1:8000")
            else:
                self.log_q.write("\n[ERROR] Server failed to start\n")
                self.launch_btn.configure(state="normal", text="⚡  Start Server")
                self.status_text.configure(text="Server failed. Check logs.", text_color="#ef4444")
        except Exception as e:
            self.log_q.write(f"\n[ERROR] Bootstrap failure: {e}\n")
            self.launch_btn.configure(state="normal", text="⚡  Start Server")

    def _update_running_state(self):
        self.status_text.configure(text="Server is running", text_color=NEON_CYAN)
        self.progress.set(1.0)
        self.launch_btn.configure(
            text="🌐  Open Dashboard",
            fg_color="#061c1a", border_color="#00D4AA",
            text_color="#00D4AA", hover_color="#004d3d",
            state="normal"
        )
        self.open_btn.configure(state="normal")
        self._api_status.configure(text="Kite", text_color=NEON_CYAN)
        self._engine_status.configure(text="Online", text_color=NEON_CYAN)

    def _open_browser(self):
        webbrowser.open("http://127.0.0.1:8000")

    # ═══════════════ Terminal Panel ═══════════════

    def _show_terminal(self):
        if self.terminal is not None or self._expanding:
            return
        self.terminal = EmbeddedTerminal(self, self.log_q, width=480, height=516)
        self.terminal.place(x=510, y=12)
        sys.stdout = StreamRedirector(self._orig_stdout, self.log_q)
        sys.stderr = StreamRedirector(self._orig_stderr, self.log_q)
        self._expanding = True
        self._expand_step(WIN_W, EXPANDED_W)

    def _expand_step(self, current, target):
        if current >= target:
            self.geometry(f"{target}x{WIN_H}")
            self._expanding = False
            self._expanded = True
            return
        nxt = min(current + 30, target)
        self.geometry(f"{nxt}x{WIN_H}")
        self.after(12, lambda: self._expand_step(nxt, target))

    # ═══════════════ Shutdown ═══════════════

    def _on_close(self):
        if self.server_running:
            self.log_q.write("\n[SHUTDOWN] Stopping server...\n")
        sys.stdout = self._orig_stdout
        sys.stderr = self._orig_stderr
        self.destroy()


if __name__ == "__main__":
    try:
        import ctypes
        import sys
        if sys.platform == 'win32':
            # Set DPI awareness to prevent blurry UI and blurry taskbar icons
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    ArcherHarvestLauncher().mainloop()
