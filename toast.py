"""Small non-blocking popups in the bottom-right corner of the screen.

  Toast   "New screenshot - describe it so you can search it later?"  [Describe] [Skip] [Always]
  Notice  "Describing..."  ->  "Screenshot indexed: <title>"   (or an error)

Both fade in, never steal keyboard focus, pause their countdown while the mouse
is over them, and stack above each other when several are visible.
"""
import sys
import tkinter as tk

from PIL import Image, ImageTk

import config

CARD, LINE, PANEL = "#1c2029", "#2a2f3b", "#171a21"
TEXT, MUTED, ACCENT, GOOD, WARN, ERR = "#e8eaf0", "#8b93a7", "#7c9cff", "#5bd6a0", "#f0b45b", "#ff7b7b"
FONT = "Segoe UI"
MAX_ALPHA = 0.97


class _Popup(tk.Toplevel):
    _stack = []  # visible popups, oldest (lowest) first

    def __init__(self, master):
        super().__init__(master)
        self.done = False
        self.fading = False
        self.paused = False
        self.overrideredirect(True)          # no title bar
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.0)
        self.configure(bg=LINE)              # 1px border colour
        self.card = tk.Frame(self, bg=CARD)
        self.card.pack(padx=1, pady=1)
        self.card.bind("<Enter>", lambda e: setattr(self, "paused", True))
        self.card.bind("<Leave>", lambda e: setattr(self, "paused", False))

    @property
    def alive(self):
        return not self.done

    def _show(self):
        _Popup._stack.append(self)
        self.update_idletasks()
        _Popup._reflow()
        self._no_focus()
        self._fade_in()

    @classmethod
    def _reflow(cls):
        y = None
        for p in cls._stack:
            w, h = p.winfo_reqwidth(), p.winfo_reqheight()
            if y is None:
                y = p.winfo_screenheight() - 72  # above the taskbar
            y -= h
            p.geometry(f"+{p.winfo_screenwidth() - w - 24}+{y}")
            y -= 10

    def _no_focus(self):
        """Windows: show without activating, so typing in other windows continues."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(self.winfo_id()) or self.winfo_id()
            style = user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
            user32.SetWindowLongW(hwnd, -20, style | 0x08000000 | 0x00000080)  # NOACTIVATE | TOOLWINDOW
        except Exception:
            pass

    def _fade_in(self, alpha=0.0):
        if self.done or self.fading:
            return
        alpha = min(MAX_ALPHA, alpha + 0.14)
        self.attributes("-alpha", alpha)
        if alpha < MAX_ALPHA:
            self.after(25, lambda: self._fade_in(alpha))

    def _fade_out(self, alpha=MAX_ALPHA):
        if self.done:
            return
        self.fading = True
        self._fade_step(alpha)

    def _fade_step(self, alpha):
        if self.done or not self.fading:
            return
        if alpha <= 0.1:
            self._close()
        else:
            self.attributes("-alpha", alpha)
            self.after(25, lambda: self._fade_step(alpha - 0.12))

    def _close(self):
        if self.done:
            return
        self.done = True
        if self in _Popup._stack:
            _Popup._stack.remove(self)
        self.destroy()
        _Popup._reflow()

    @staticmethod
    def _btn(parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, relief="flat", bd=0,
                         highlightthickness=0, cursor="hand2",
                         font=(FONT, 9, "bold" if primary else "normal"),
                         bg=ACCENT if primary else PANEL, fg="#0b0d12" if primary else TEXT,
                         activebackground="#9db4ff" if primary else LINE,
                         activeforeground="#0b0d12" if primary else TEXT, padx=12, pady=5)


class Toast(_Popup):
    """The permission question."""

    def __init__(self, master, path, on_yes, on_no, on_always, seconds=12):
        super().__init__(master)
        self.on_yes, self.on_no, self.on_always = on_yes, on_no, on_always
        self.total = seconds * 20            # countdown ticks of 50 ms
        self.left = self.total

        row = tk.Frame(self.card, bg=CARD)
        row.pack(padx=14, pady=(14, 8))
        self.photo = None
        try:
            img = Image.open(path).convert("RGB")
            img.thumbnail((130, 82))
            self.photo = ImageTk.PhotoImage(img)
            tk.Label(row, image=self.photo, bg=CARD).pack(side="left", padx=(0, 12))
        except Exception:
            pass
        text = tk.Frame(row, bg=CARD)
        text.pack(side="left")
        tk.Label(text, text="New screenshot", font=(FONT, 11, "bold"), fg=TEXT, bg=CARD).pack(anchor="w")
        tk.Label(text, text="Describe it so you can search it later?", font=(FONT, 9),
                 fg=MUTED, bg=CARD).pack(anchor="w")
        if config.IS_LOCAL:
            tk.Label(text, text="Stays on this PC", font=(FONT, 8), fg=GOOD, bg=CARD).pack(anchor="w", pady=(3, 0))
        else:
            tk.Label(text, text=f"Image will be sent to {config.HOST}", font=(FONT, 8),
                     fg=WARN, bg=CARD).pack(anchor="w", pady=(3, 0))

        btns = tk.Frame(self.card, bg=CARD)
        btns.pack(fill="x", padx=14, pady=(0, 10))
        self.btn_yes = self._btn(btns, "Describe", lambda: self._finish(self.on_yes), True)
        self.btn_yes.pack(side="left")
        self._btn(btns, "Skip", lambda: self._finish(self.on_no)).pack(side="left", padx=6)
        self._btn(btns, "Always describe", lambda: self._finish(self.on_always)).pack(side="left")

        self.bar = tk.Canvas(self.card, height=3, bg=CARD, highlightthickness=0)
        self.bar.pack(fill="x")
        self._show()
        self._tick()

    def _tick(self):
        if self.done:
            return
        if not self.paused:
            self.left -= 1
        self.bar.delete("all")
        w = self.bar.winfo_width()
        self.bar.create_rectangle(0, 0, w * max(self.left, 0) / self.total, 3, fill=ACCENT, width=0)
        if self.left <= 0:
            self._finish(self.on_no)
        else:
            self.after(50, self._tick)

    def _finish(self, callback):
        if self.done:
            return
        self._close()
        callback()


class Notice(_Popup):
    """The confirmation: working -> ok (or error). One Notice is reused via set()."""

    COLORS = {"working": ACCENT, "ok": GOOD, "error": ERR}
    ICONS = {"working": "...", "ok": "\u2713", "error": "!"}
    TICKS = {"working": None, "ok": 100, "error": 160}  # 5 s / 8 s

    def __init__(self, master, kind, title, subtitle=""):
        super().__init__(master)
        row = tk.Frame(self.card, bg=CARD)
        row.pack(padx=14, pady=(12, 8), anchor="w")
        self.icon = tk.Label(row, width=3, font=(FONT, 15, "bold"), bg=CARD)
        self.icon.pack(side="left", padx=(0, 8))
        text = tk.Frame(row, bg=CARD)
        text.pack(side="left")
        self.title = tk.Label(text, font=(FONT, 11, "bold"), fg=TEXT, bg=CARD, anchor="w", justify="left")
        self.title.pack(anchor="w")
        self.sub = tk.Label(text, font=(FONT, 9), fg=MUTED, bg=CARD, anchor="w", justify="left",
                            wraplength=300)
        self.sub.pack(anchor="w")
        self.bar = tk.Canvas(self.card, height=3, bg=CARD, highlightthickness=0)
        self.bar.pack(fill="x")
        self.phase = 0
        self.set(kind, title, subtitle)
        self._show()
        self._tick()

    def set(self, kind, title, subtitle=""):
        """Update this notice in place (e.g. 'Describing...' -> 'Indexed')."""
        self.kind = kind
        self.total = self.TICKS[kind] or 1
        self.left = self.total
        self.fading = False
        self.icon.configure(text=self.ICONS[kind], fg=self.COLORS[kind])
        self.title.configure(text=title)
        self.sub.configure(text=(subtitle or "")[:170])
        if not self.done:
            self.attributes("-alpha", MAX_ALPHA)
            self.update_idletasks()
            _Popup._reflow()

    def _tick(self):
        if self.done:
            return
        self.phase += 1
        self.bar.delete("all")
        w = max(self.bar.winfo_width(), 1)
        if self.kind == "working":               # sliding segment = "busy"
            x = (self.phase * 10) % (w + 80) - 80
            self.bar.create_rectangle(x, 0, x + 80, 3, fill=ACCENT, width=0)
        else:                                    # shrinking bar = time until it fades
            if not self.paused and not self.fading:
                self.left -= 1
            self.bar.create_rectangle(0, 0, w * max(self.left, 0) / self.total, 3,
                                      fill=self.COLORS[self.kind], width=0)
            if self.left <= 0 and not self.fading:
                self._fade_out()
        self.after(50, self._tick)
