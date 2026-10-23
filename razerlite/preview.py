"""Aperçu animé de l'éclairage, affiché à partir des rendus réalistes de render.py."""

import math
import random
import time
import tkinter as tk

from PIL import ImageTk

from . import keystate, render
from . import theme as t

ANIMATED = ("spectrum", "wave", "breathing", "reactive", "starlight")


class DevicePreview(tk.Canvas):
    def __init__(self, master, kind, width=300, height=330, bg=t.CARD):
        super().__init__(master, width=width, height=height, bg=bg, highlightthickness=0)
        self.kind = kind
        self.lighting, self.brightness = {}, 100
        self.model = None
        self.twinkle = {}
        self._photo = None
        self._item = None
        self._job = None
        self._resize_job = None
        self.pressed = set()
        self.flashes = {}       # bouton -> instant de fin (ex. bouton DPI, invisible pour Windows)
        self.keys = keystate.get()
        self._poll_job = None
        self.bind("<Configure>", self._on_resize)
        self.bind("<Destroy>", lambda e: self._stop(all_jobs=True) if e.widget is self else None)
        if self.kind in ("keyboard", "mouse"):
            self._poll_job = self.after(200, self._poll)

    def _on_resize(self, event):
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, self._rebuild)

    def _rebuild(self):
        self._resize_job = None
        w, h = self.winfo_width(), self.winfo_height()
        if w < 50 or h < 50:  # pas encore affiché : taille demandée
            w, h = int(self["width"]), int(self["height"])
        w, h = max(200, w), max(160, h)
        self.model = render.get(self.kind, w, h)
        self.paint()

    def _stop(self, all_jobs=False):
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        if all_jobs and self._poll_job:
            self.after_cancel(self._poll_job)
            self._poll_job = None

    # --- appuis en direct ---
    def flash(self, button, duration=0.35):
        self.flashes[button] = time.monotonic() + duration
        self._refresh_pressed(force=True)

    def _poll(self):
        self._poll_job = self.after(35, self._poll)
        if self.model is None or not self.winfo_viewable():
            return
        self._refresh_pressed()

    def _refresh_pressed(self, force=False):
        now = time.monotonic()
        if self.kind == "keyboard":
            current = self.keys.pressed_keys(self.model.key_codes) if self.model else set()
        else:
            current = self.keys.pressed_buttons()
        self.flashes = {b: end for b, end in self.flashes.items() if end > now}
        current |= set(self.flashes)
        if current == self.pressed and not force:
            return
        new = current - self.pressed
        self.pressed = current
        if self.kind == "keyboard" and self.lighting.get("effect") == "reactive":
            color = self.lighting.get("color1") or t.ACCENT
            for i in new:
                if isinstance(i, int):
                    self.twinkle[i] = (now, color)
        if self._job is None:  # pas d'animation en cours : on redessine tout de suite
            self.paint()

    def show(self, lighting, brightness):
        self.lighting, self.brightness = dict(lighting), brightness
        self._stop()
        if self.model is None:
            self._rebuild()
        else:
            self.paint()

    # --- couleurs ---
    def _rgb(self, color, level=1.0):
        factor = (0.3 + 0.7 * self.brightness / 100) * level
        return tuple(int(c * factor) for c in t.hex_to_rgb(color))

    def _zone_color(self, zone, now, pos=0.0):
        L = self.lighting
        effect = L.get("effect", "static")
        c1, c2 = L.get("color1") or t.ACCENT, L.get("color2")
        if effect == "off":
            return None
        if effect == "zones":
            return self._rgb(L.get("zone_colors", {}).get(zone, "#000000"))
        if effect == "static":
            target = L.get("zone")
            if self.kind == "mouse" and target not in (None, "Tout", zone):
                return None
            return self._rgb(c1)
        if effect == "spectrum":
            return self._rgb(t.hue(now / 6))
        if effect == "wave":
            direction = -1 if int(L.get("direction", 1)) == 1 else 1
            return self._rgb(t.hue(pos * 0.85 + direction * now / 3))
        if effect == "breathing":
            phase = (math.sin(now * 1.6) + 1) / 2
            color = c2 if c2 and int(now * 1.6 / math.pi) % 2 else c1
            return self._rgb(color, 0.08 + 0.92 * phase)
        return self._rgb(c1)

    def _key_colors(self, now):
        L = self.lighting
        effect = L.get("effect", "static")
        keys = self.model.keys
        if effect in ("reactive", "starlight"):
            c1, c2 = L.get("color1") or t.ACCENT, L.get("color2")
            simulated = effect == "starlight" or not self.keys.available
            if simulated and random.random() < (0.45 if effect == "reactive" else 0.8):
                self.twinkle[random.randrange(len(keys))] = (now, c2 if c2 and random.random() < 0.5 else c1)
            out = []
            for i in range(len(keys)):
                start, color = self.twinkle.get(i, (-10, c1))
                age = now - start
                if effect == "reactive":
                    level = max(0.0, 1 - age / 0.9)
                else:
                    level = math.sin(age / 1.4 * math.pi) if 0 <= age < 1.4 else 0
                out.append(self._rgb(color, level) if level > 0.02 else None)
            return out
        return [self._zone_color("Clavier", now, k[4]) for k in keys]

    def paint(self):
        if self.model is None:
            return
        self._stop()
        now = time.monotonic()
        if self.kind == "keyboard":
            img = self.model.compose({}, self._key_colors(now), pressed=self.pressed)
        else:
            zones = list(self.model.zones) + list(self.model.under)
            img = self.model.compose({z: self._zone_color(z, now) for z in zones}, pressed=self.pressed)
        self._photo = ImageTk.PhotoImage(img)
        if self._item is None:
            self._item = self.create_image(0, 0, anchor="nw", image=self._photo)
        else:
            self.itemconfigure(self._item, image=self._photo)
        reacting = self.lighting.get("effect") == "reactive" and any(
            now - start < 1.0 for start, _ in self.twinkle.values())
        if self.lighting.get("effect") in ANIMATED and (self.lighting.get("effect") != "reactive"
                                                         or not self.keys.available or reacting):
            self._job = self.after(50 if self.kind != "keyboard" else 70, self.paint)
