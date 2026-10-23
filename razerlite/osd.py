"""Petite notification DPI à l'écran, comme celle de Synapse (au-dessus de tout, transparente aux clics)."""

import sys
import tkinter as tk

from . import theme as t

W, H = 230, 104
KEY = "#010203"  # couleur rendue transparente (coins arrondis)


class DpiOsd:
    def __init__(self, root):
        self.root = root
        self.win = None
        self._fade_job = None
        self._alpha = 0.0

    def _build(self):
        win = tk.Toplevel(self.root)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=KEY)
        if sys.platform == "win32":
            win.attributes("-transparentcolor", KEY)
        c = tk.Canvas(win, width=W, height=H, bg=KEY, highlightthickness=0)
        c.pack()
        t.rounded_rect(c, 1, 1, W - 1, H - 1, 22, fill="#0f1215", outline="#2a3139", width=1.5)
        try:
            from PIL import ImageTk

            from .logo import mark
            self._mark = ImageTk.PhotoImage(mark(20, glow=False))
            c.create_image(W / 2 - 52, 30, image=self._mark)
        except Exception:
            self._mark = None
        self.title = c.create_text(W / 2 + 10, 30, text="SENSIBILITÉ", fill=t.MUTED, font=(t.FONT, 9, "bold"))
        self.value = c.create_text(W / 2, 60, text="", fill=t.TEXT, font=(t.FONT, 26, "bold"))
        self.canvas = c
        self.dots = []
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"{W}x{H}+{(sw - W) // 2}+{sh - H - 150}")
        self.win = win
        self._click_through()

    def _click_through(self):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            self.win.update_idletasks()
            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(self.win.winfo_id()) or self.win.winfo_id()
            GWL_EXSTYLE = -20
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            # LAYERED | TRANSPARENT (clics traversants) | TOOLWINDOW (pas dans Alt+Tab) | NOACTIVATE
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | 0x80000 | 0x20 | 0x80 | 0x08000000)
        except Exception:
            pass

    def show(self, dpi, stage=None, count=None):
        if self.win is None:
            self._build()
        c = self.canvas
        c.itemconfigure(self.value, text=f"{dpi:,}".replace(",", " ") + " DPI")
        for d in self.dots:
            c.delete(d)
        self.dots = []
        if stage and count:
            gap = 16
            x0 = W / 2 - (count - 1) * gap / 2
            for i in range(count):
                active = i + 1 == stage
                r = 4.5 if active else 3.5
                self.dots.append(c.create_oval(x0 + i * gap - r, 88 - r, x0 + i * gap + r, 88 + r, outline="",
                                               fill=t.ACCENT if active else "#3a424c"))
        if self._fade_job:
            self.root.after_cancel(self._fade_job)
        self._alpha = 0.96
        self.win.attributes("-alpha", self._alpha)
        self.win.deiconify()
        self.win.lift()
        self._fade_job = self.root.after(1300, self._fade)

    def _fade(self):
        self._alpha -= 0.12
        if self._alpha <= 0:
            self.win.withdraw()
            self._fade_job = None
            return
        self.win.attributes("-alpha", self._alpha)
        self._fade_job = self.root.after(30, self._fade)
