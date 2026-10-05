"""Desktop app (tkinter + Pillow). Dark theme, result cards with thumbnails."""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

import agent
import config
import indexer
from store import get_store
from toast import Notice, Toast

BG, PANEL, CARD, LINE = "#0f1115", "#171a21", "#1c2029", "#2a2f3b"
TEXT, MUTED, ACCENT, GOOD = "#e8eaf0", "#8b93a7", "#7c9cff", "#5bd6a0"
FONT = "Segoe UI"


def open_file(path):
    if not os.path.exists(path):
        messagebox.showwarning("File missing", f"This file was moved or deleted:\n{path}")
    elif sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path])


def show_in_folder(path):
    if not os.path.exists(path):
        messagebox.showwarning("File missing", f"This file was moved or deleted:\n{path}")
    elif sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Screen Memory")
        self.geometry("1020x780")
        self.minsize(840, 560)
        self.configure(bg=BG)
        self.store = get_store()
        self.events = queue.Queue()
        self.photos, self.wrap_labels, self.step_lines = [], [], []
        self.observer = None
        self.indexing = False
        self.stop_index = threading.Event()
        self.ask_mode = True          # ask before describing new screenshots
        self.toasts, self.toast, self.notice = [], None, None
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(120, self._poll)
        self._refresh_subtitle()
        self.after(400, self._toggle_watch)  # auto-describe is on by default

    # ------------------------------------------------------------------ layout
    def _button(self, parent, text, command, primary=False):
        return tk.Button(
            parent, text=text, command=command, relief="flat", bd=0, cursor="hand2",
            highlightthickness=0,
            font=(FONT, 10, "bold" if primary else "normal"),
            bg=ACCENT if primary else PANEL, fg="#0b0d12" if primary else TEXT,
            activebackground="#9db4ff" if primary else LINE, activeforeground="#0b0d12" if primary else TEXT,
            padx=18 if primary else 12, pady=9 if primary else 6,
        )

    def _build(self):
        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=28, pady=(22, 4))
        tk.Label(head, text="Screen Memory", font=(FONT, 22, "bold"), fg=TEXT, bg=BG).pack(anchor="w")
        self.sub = tk.Label(head, text="", font=(FONT, 9), fg=MUTED, bg=BG)
        self.sub.pack(anchor="w")

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=28, pady=(12, 4))
        box = tk.Frame(bar, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        box.pack(side="left", fill="x", expand=True)
        self.entry = tk.Entry(box, font=(FONT, 13), bg=PANEL, fg=TEXT, insertbackground=TEXT,
                              relief="flat", bd=0)
        self.entry.pack(fill="x", padx=14, pady=12)
        self.entry.bind("<Return>", lambda e: self.search())
        self.entry.focus_set()
        self.search_btn = self._button(bar, "Search", self.search, primary=True)
        self.search_btn.pack(side="left", padx=(10, 0))

        tk.Label(self, text="Ask naturally, e.g. \"the site where I compared laptop prices last week\"",
                 font=(FONT, 9), fg=MUTED, bg=BG).pack(anchor="w", padx=30)

        tools = tk.Frame(self, bg=BG)
        tools.pack(fill="x", padx=28, pady=(10, 0))
        self.watch_var = tk.BooleanVar(value=True)
        tk.Checkbutton(tools, text="Auto-describe new screenshots", variable=self.watch_var,
                       command=self._toggle_watch, bg=BG, fg=TEXT, selectcolor=PANEL,
                       activebackground=BG, activeforeground=TEXT, font=(FONT, 10),
                       highlightthickness=0, bd=0).pack(side="left")
        self.ask_var = tk.BooleanVar(value=True)
        tk.Checkbutton(tools, text="Ask me first", variable=self.ask_var,
                       command=lambda: setattr(self, "ask_mode", self.ask_var.get()),
                       bg=BG, fg=TEXT, selectcolor=PANEL, activebackground=BG, activeforeground=TEXT,
                       font=(FONT, 10), highlightthickness=0, bd=0).pack(side="left", padx=(10, 0))
        self.index_btn = self._button(tools, "Index existing screenshots", self._toggle_index)
        self.index_btn.pack(side="left", padx=14)
        self.status = tk.Label(tools, text="", font=(FONT, 9), fg=MUTED, bg=BG, anchor="w")
        self.status.pack(side="left", fill="x", expand=True)

        self.answer = tk.Label(self, text="", font=(FONT, 12), fg=TEXT, bg=BG, justify="left",
                               anchor="w", wraplength=900)
        self.answer.pack(fill="x", padx=30, pady=(14, 0))
        self.steps = tk.Label(self, text="", font=("Consolas", 9), fg=MUTED, bg=BG, justify="left",
                              anchor="w")
        self.steps.pack(fill="x", padx=30, pady=(4, 0))

        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True, padx=(28, 10), pady=(8, 16))
        self.canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_resize)
        self.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-e.delta / 120), "units"))

    def _on_resize(self, e):
        self.canvas.itemconfigure(self.win, width=e.width)
        self.answer.configure(wraplength=max(300, e.width - 20))
        self.steps.configure(wraplength=max(300, e.width - 20))
        for lbl in self.wrap_labels:
            try:
                lbl.configure(wraplength=max(260, e.width - 340))
            except tk.TclError:
                pass

    # ------------------------------------------------------------------ actions
    def _refresh_subtitle(self):
        try:
            n = self.store.count()
        except Exception as e:
            n = f"? ({e})"
        self.sub.configure(
            text=f"{n} screenshots indexed   |   database: {self.store.name}")

    def search(self):
        q = self.entry.get().strip()
        if not q or self.search_btn["state"] == "disabled":
            return
        self.search_btn.configure(state="disabled", text="Thinking...")
        self._clear()
        self.answer.configure(text="")
        self.step_lines = []
        self.steps.configure(text="")

        def work():
            try:
                res = agent.run_agent(q, self.store, on_step=lambda s: self.events.put(("step", s)))
            except Exception as e:
                self.events.put(("error", str(e)))
                return
            self.events.put(("done", res))

        threading.Thread(target=work, daemon=True).start()

    def _toggle_index(self):
        if self.indexing:
            self.stop_index.set()
            return
        self.indexing = True
        self.stop_index.clear()
        self.index_btn.configure(text="Stop indexing")

        def work():
            try:
                indexer.index_all(self.store, log=lambda s: self.events.put(("log", s)), stop=self.stop_index)
            except Exception as e:
                self.events.put(("log", f"Indexing error: {e}"))
            self.events.put(("index_done", None))

        threading.Thread(target=work, daemon=True).start()

    def _toggle_watch(self):
        if self.watch_var.get():
            if self.observer:
                return
            try:
                self.observer = indexer.start_watcher(
                    self.store,
                    on_indexed=lambda r: self.events.put(("indexed", r)),
                    on_new=self._on_new_file,
                    log=lambda s: self.events.put(("log", s)))
            except Exception as e:
                self.watch_var.set(False)
                self.status.configure(text=f"Watcher not started: {e}")
        elif self.observer:
            self.observer.stop()
            self.observer = None
            self.status.configure(text="Auto-describe is off.")

    def _poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "step":
                    self.step_lines.append(data)
                    self.steps.configure(text="\n".join(self.step_lines[-5:]))
                elif kind == "done":
                    self._show(data)
                elif kind == "error":
                    self.answer.configure(text=f"Something went wrong: {data}")
                    self.search_btn.configure(state="normal", text="Search")
                elif kind == "working":
                    self._notice("working", "Describing screenshot...", os.path.basename(data))
                elif kind == "failed":
                    self._notice("error", "Could not describe screenshot", data[1])
                    self.status.configure(text=f"Could not describe {os.path.basename(data[0])}")
                elif kind == "ask":
                    self.toasts.append(data)
                    self._next_toast()
                elif kind == "log":
                    self.status.configure(text=data)
                elif kind == "indexed":
                    self.status.configure(text=f"Described new screenshot: {data['title']}")
                    self._refresh_subtitle()
                    self._notice("ok", "Screenshot indexed", f"{data['title']}  -  {data.get('description', '')}")
                elif kind == "index_done":
                    self.indexing = False
                    self.index_btn.configure(text="Index existing screenshots")
                    self._refresh_subtitle()
        except queue.Empty:
            pass
        self.after(120, self._poll)

    # ------------------------------------------------- new-screenshot permission
    def _on_new_file(self, path):  # called from the watcher thread
        if self.ask_mode:
            self.events.put(("ask", str(path)))
        else:
            self._describe_async(str(path))

    def _describe_async(self, path):
        self.events.put(("working", path))

        def work():
            try:
                rec = indexer.index_file(self.store, path)
                if rec:
                    self.events.put(("indexed", rec))
            except Exception as e:
                self.events.put(("failed", (path, str(e))))

        threading.Thread(target=work, daemon=True).start()

    def _notice(self, kind, title, subtitle=""):
        if self.notice is not None and self.notice.alive:
            self.notice.set(kind, title, subtitle)
        else:
            self.notice = Notice(self, kind, title, subtitle)

    def _next_toast(self):
        if self.toast is not None or not self.toasts:
            return
        path = self.toasts.pop(0)
        if self.store.exists(path):
            return self._next_toast()
        self.toast = Toast(self, path,
                           on_yes=lambda: self._toast_done(path, True),
                           on_no=lambda: self._toast_done(path, False),
                           on_always=lambda: self._always(path))

    def _toast_done(self, path, yes):
        self.toast = None
        if yes:
            self.status.configure(text="Describing the new screenshot...")
            self._describe_async(path)
        self.after(300, self._next_toast)

    def _always(self, path):
        self.ask_var.set(False)
        self.ask_mode = False
        for p in [path] + self.toasts:
            self._describe_async(p)
        self.toasts = []
        self.toast = None
        self.status.configure(text="Describing all new screenshots automatically. Tick \"Ask me first\" to turn permission back on.")

    # ------------------------------------------------------------------ results
    def _clear(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self.photos, self.wrap_labels = [], []
        self.canvas.yview_moveto(0)

    def _show(self, res):
        self.search_btn.configure(state="normal", text="Search")
        self.answer.configure(text=res.get("answer", ""))
        results = res.get("results", [])
        if not results:
            tk.Label(self.inner, text="No matching screenshots.", font=(FONT, 11), fg=MUTED,
                     bg=BG).pack(anchor="w", pady=20)
        for rec in results:
            self._card(rec)

    def _thumb(self, path):
        try:
            img = Image.open(path).convert("RGB")
            img.thumbnail((250, 160))
            photo = ImageTk.PhotoImage(img)
            self.photos.append(photo)  # keep a reference or Tk drops the image
            return photo
        except Exception:
            return None

    def _card(self, rec):
        path = rec["path"]
        card = tk.Frame(self.inner, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        card.pack(fill="x", padx=4, pady=8)
        card.columnconfigure(1, weight=1)

        photo = self._thumb(path)
        if photo:
            thumb = tk.Label(card, image=photo, bg=CARD, cursor="hand2")
            thumb.bind("<Button-1>", lambda e, p=path: open_file(p))
        else:
            thumb = tk.Label(card, text="file\nmissing", width=26, height=8, fg=MUTED, bg=PANEL)
        thumb.grid(row=0, column=0, padx=14, pady=14, sticky="n")

        body = tk.Frame(card, bg=CARD)
        body.grid(row=0, column=1, sticky="nsew", padx=(0, 14), pady=14)

        top = tk.Frame(body, bg=CARD)
        top.pack(fill="x")
        tk.Label(top, text=rec.get("title") or rec["filename"], font=(FONT, 13, "bold"),
                 fg=TEXT, bg=CARD, anchor="w").pack(side="left")
        tk.Label(top, text=f" {rec['taken_at']} ", font=(FONT, 9), fg=ACCENT, bg=PANEL).pack(side="left", padx=10)

        def para(text, color, font):
            lbl = tk.Label(body, text=text, fg=color, bg=CARD, font=font, justify="left",
                           anchor="w", wraplength=560)
            lbl.pack(fill="x", pady=(6, 0))
            self.wrap_labels.append(lbl)

        para(rec.get("description", ""), TEXT, (FONT, 10))
        if rec.get("why"):
            para("Why it matches: " + rec["why"], GOOD, (FONT, 10, "italic"))
        if rec.get("tags"):
            para("#" + "  #".join(rec["tags"].split()), MUTED, (FONT, 9))
        para(path, MUTED, ("Consolas", 8))

        row = tk.Frame(body, bg=CARD)
        row.pack(anchor="w", pady=(10, 0))
        self._button(row, "Open", lambda p=path: open_file(p), primary=True).pack(side="left")
        self._button(row, "Show in folder", lambda p=path: show_in_folder(p)).pack(side="left", padx=8)
        self._button(row, "Copy path", lambda p=path: self._copy(p)).pack(side="left")

    def _copy(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.configure(text="Path copied to clipboard.")

    def _close(self):
        self.stop_index.set()
        if self.observer:
            self.observer.stop()
        self.destroy()


def run():
    App().mainloop()
