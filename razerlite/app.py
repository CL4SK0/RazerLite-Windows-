"""Interface graphique de RazerLite (customtkinter), icône de barre des tâches et notif DPI."""

import copy
import queue
import sys
import threading
import tkinter as tk
import urllib.parse
import webbrowser
from tkinter import colorchooser, messagebox

import customtkinter as ctk

from . import __version__, audio, instance, logo, monitor, profiles, protocol, updater
from . import theme as t
from .devices import RazerError, find_devices
from .osd import DpiOsd
from .preview import DevicePreview

EFFECT_LABELS = {
    "static": "Fixe",
    "spectrum": "Spectre",
    "wave": "Vague",
    "breathing": "Respiration",
    "reactive": "Réactif",
    "starlight": "Étoiles",
    "zones": "Par zone",
    "off": "Éteint",
}
KIND_LABELS = {"mouse": "Souris", "keyboard": "Clavier", "headset": "Casque"}
KIND_ICONS = {"mouse": "🖱", "keyboard": "⌨", "headset": "🎧"}
PAGES = {
    "mouse": ["Éclairage", "Performance", "Molette", "Alimentation"],
    "keyboard": ["Éclairage", "Alimentation"],
    "headset": ["Éclairage", "Audio"],
}
POLL_LABELS = {125: "125 Hz", 500: "500 Hz", 1000: "1000 Hz"}
DPI_MIN, DPI_MAX, DPI_STEP = 100, 26000, 50


def font(size=13, weight="normal"):
    return ctk.CTkFont(family=t.FONT, size=size, weight=weight)


def card(master, **kw):
    return ctk.CTkFrame(master, fg_color=t.CARD, corner_radius=14, border_width=1, border_color=t.BORDER, **kw)


def section(master, text):
    return ctk.CTkLabel(master, text=text.upper(), font=font(11, "bold"), text_color=t.MUTED, anchor="w")


# Qui fait le retour micro : le casque (firmware) ou RazerLite (micro rejoué par le PC)
SIDETONE_MODES = {"Casque": "headset", "RazerLite (faible délai)": "app"}


def segmented(master, values, command, **kw):
    return ctk.CTkSegmentedButton(master, values=values, command=command, font=font(12),
                                  selected_color=t.ACCENT, selected_hover_color=t.ACCENT_HOVER,
                                  unselected_color=t.CARD_HI, unselected_hover_color=t.BORDER,
                                  fg_color=t.CARD_HI, text_color=t.TEXT, **kw)


def slider(master, start, end, command, steps=None, **kw):
    return ctk.CTkSlider(master, from_=start, to=end, number_of_steps=steps, command=command,
                         progress_color=t.ACCENT, button_color=t.TEXT, button_hover_color=t.ACCENT,
                         fg_color=t.CARD_HI, **kw)


def switch(master, text, command, value):
    var = tk.BooleanVar(value=value)
    widget = ctk.CTkSwitch(master, text=text, variable=var, command=command, font=font(12),
                           progress_color=t.ACCENT, button_color=t.TEXT, fg_color=t.CARD_HI, text_color=t.TEXT)
    return widget, var


def button(master, text, command, primary=False, **kw):
    if primary:
        return ctk.CTkButton(master, text=text, command=command, font=font(12, "bold"), fg_color=t.ACCENT,
                             hover_color=t.ACCENT_HOVER, text_color=t.ACCENT_TEXT, corner_radius=8, **kw)
    return ctk.CTkButton(master, text=text, command=command, font=font(12), fg_color=t.CARD_HI,
                         hover_color=t.BORDER, text_color=t.TEXT, corner_radius=8, **kw)


class Page(ctk.CTkFrame):
    """Une page de réglages pour un appareil."""

    def __init__(self, master, app, device):
        super().__init__(master, fg_color="transparent")
        self.app, self.device = app, device

    @property
    def settings(self):
        return self.app.device_settings(self.device)

    def changed(self, what):
        self.app.schedule_apply(self.device, what)


# --- Éclairage ---------------------------------------------------------------

class LightingPage(Page):
    def __init__(self, master, app, device):
        super().__init__(master, app, device)
        self.target = "color1"
        self.wide = wide = device.kind == "keyboard"
        self.columnconfigure(0, weight=5, uniform="c")
        self.columnconfigure(1, weight=6, uniform="c")
        self.rowconfigure(0, weight=1)

        left = card(self)
        if wide:  # clavier : aperçu sur toute la largeur, réglages dessous
            left.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 10))
        else:
            left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        section(left, "Aperçu").pack(anchor="w", padx=18, pady=(16, 0))
        self.preview = DevicePreview(left, device.kind, width=320, height=330 if not wide else 200)
        self.preview.pack(fill="both", expand=True, padx=12, pady=(4, 10))

        self.controls = card(self)
        if wide:
            self.controls.grid(row=1, column=0, columnspan=2, sticky="nsew")
        else:
            self.controls.grid(row=0, column=1, sticky="nsew")
        self.build_controls()

    @property
    def lighting(self):
        return self.settings.setdefault("lighting", {"effect": "static", "color1": t.ACCENT})

    def build_controls(self):
        for w in self.controls.winfo_children():
            w.destroy()
        L, spec = self.lighting, self.device.spec
        effect = L.get("effect", "static")
        body = ctk.CTkFrame(self.controls, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=16)

        section(body, "Effet").pack(anchor="w")
        grid = ctk.CTkFrame(body, fg_color="transparent")
        grid.pack(fill="x", pady=(8, 14))
        per_row = len(spec.effects) if self.wide else 4
        for i, key in enumerate(spec.effects):
            active = key == effect
            b = ctk.CTkButton(grid, text=EFFECT_LABELS[key], height=34, corner_radius=8,
                              font=font(12, "bold" if active else "normal"),
                              fg_color=t.ACCENT if active else t.CARD_HI,
                              hover_color=t.ACCENT_HOVER if active else t.BORDER,
                              text_color=t.ACCENT_TEXT if active else t.TEXT,
                              command=lambda k=key: self.set_effect(k))
            b.grid(row=i // per_row, column=i % per_row, sticky="ew", padx=3, pady=3)
        for c in range(per_row):
            grid.columnconfigure(c, weight=1)

        if len(spec.zones) > 1 and effect not in ("zones", "off"):
            section(body, "Zone").pack(anchor="w")
            seg = segmented(body, list(spec.zones), lambda v: self.update(zone=v))
            seg.set(L.get("zone") or next(iter(spec.zones)))
            seg.pack(fill="x", pady=(8, 14))

        if effect in ("static", "breathing", "reactive", "starlight", "zones"):
            section(body, "Couleur").pack(anchor="w")
            if effect == "zones":
                targets = [z for z, *_ in spec.frame]
                if self.target not in targets:
                    self.target = targets[0]
                seg = segmented(body, targets, self.set_target)
                seg.set(self.target)
                seg.pack(fill="x", pady=(8, 6))
            elif effect in ("breathing", "starlight"):
                row = ctk.CTkFrame(body, fg_color="transparent")
                row.pack(fill="x", pady=(8, 6))
                sw, self.two_var = switch(row, "Deux couleurs", self.toggle_two, bool(L.get("color2")))
                sw.pack(side="left")
                if L.get("color2"):
                    seg = segmented(row, ["Couleur 1", "Couleur 2"],
                                    lambda v: self.set_target("color1" if v == "Couleur 1" else "color2"))
                    seg.set("Couleur 1" if self.target == "color1" else "Couleur 2")
                    seg.pack(side="right")
                else:
                    self.target = "color1"
            else:
                self.target = "color1"
            self.build_swatches(body)

        if effect == "wave":
            section(body, "Sens").pack(anchor="w")
            seg = segmented(body, ["← Gauche", "Droite →"],
                            lambda v: self.update(direction=1 if v.startswith("←") else 2))
            seg.set("← Gauche" if int(L.get("direction", 1)) == 1 else "Droite →")
            seg.pack(fill="x", pady=(8, 14))
        if effect in ("reactive", "starlight"):
            section(body, "Durée" if effect == "reactive" else "Vitesse").pack(anchor="w")
            values = ["1", "2", "3", "4"] if effect == "reactive" else ["1", "2", "3"]
            seg = segmented(body, values, lambda v: self.update(speed=int(v)))
            seg.set(str(min(int(L.get("speed", 2)), len(values))))
            seg.pack(fill="x", pady=(8, 14))

        if effect != "off" and "brightness" in spec.features:
            head = ctk.CTkFrame(body, fg_color="transparent")
            head.pack(fill="x")
            section(head, "Luminosité").pack(side="left")
            self.bright_label = ctk.CTkLabel(head, text=f"{self.settings.get('brightness', 100)} %",
                                             font=font(12, "bold"), text_color=t.TEXT)
            self.bright_label.pack(side="right")
            s = slider(body, 0, 100, self.set_brightness, steps=100)
            s.set(self.settings.get("brightness", 100))
            s.pack(fill="x", pady=(8, 4))
        if effect == "zones":
            ctk.CTkLabel(body, text="Ce mode n'est pas gardé en mémoire par la souris : "
                                    "RazerLite le réapplique à chaque démarrage.",
                         font=font(11), text_color=t.MUTED, wraplength=380, justify="left").pack(anchor="w", pady=(12, 0))
        self.preview.show(self.lighting, self.settings.get("brightness", 100))

    def build_swatches(self, body):
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(4, 14))
        current = self.current_color()
        for color in t.SWATCHES:
            selected = color.lower() == (current or "").lower()
            ctk.CTkButton(row, text="", width=30, height=30, corner_radius=15, fg_color=color, hover_color=color,
                          border_width=3 if selected else 0, border_color=t.TEXT,
                          command=lambda c=color: self.set_color(c)).pack(side="left", padx=(0, 6))
        custom = current if current and current.lower() not in [c.lower() for c in t.SWATCHES] else None
        ctk.CTkButton(row, text="+", width=30, height=30, corner_radius=15, font=font(15, "bold"),
                      fg_color=custom or t.CARD_HI, hover_color=t.BORDER, text_color=t.TEXT,
                      border_width=3 if custom else 0, border_color=t.TEXT,
                      command=self.pick_color).pack(side="left")

    def current_color(self):
        L = self.lighting
        if L.get("effect") == "zones":
            return L.setdefault("zone_colors", {}).get(self.target, "#000000")
        return L.get(self.target) or (t.ACCENT if self.target == "color1" else "#2d6bff")

    def set_color(self, color):
        L = self.lighting
        if L.get("effect") == "zones":
            L.setdefault("zone_colors", {})[self.target] = color
        else:
            L[self.target] = color
        self.changed("lighting")
        self.build_controls()

    def pick_color(self):
        _, hexa = colorchooser.askcolor(self.current_color(), parent=self, title="Couleur personnalisée")
        if hexa:
            self.set_color(hexa)

    def set_target(self, target):
        self.target = target
        self.build_controls()

    def toggle_two(self):
        self.lighting["color2"] = "#2d6bff" if self.two_var.get() else None
        self.target = "color2" if self.two_var.get() else "color1"
        self.changed("lighting")
        self.build_controls()

    def set_effect(self, effect):
        self.lighting["effect"] = effect
        self.changed("lighting")
        self.build_controls()

    def update(self, **values):
        self.lighting.update(values)
        self.changed("lighting")
        self.preview.show(self.lighting, self.settings.get("brightness", 100))

    def set_brightness(self, value):
        self.settings["brightness"] = int(value)
        self.bright_label.configure(text=f"{int(value)} %")
        self.preview.show(self.lighting, int(value))
        self.changed("brightness")


# --- Performance (souris) -------------------------------------------------------

class PerformancePage(Page):
    def __init__(self, master, app, device):
        super().__init__(master, app, device)
        s = self.settings

        top = card(self)
        top.pack(fill="x")
        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=16)
        left = ctk.CTkFrame(inner, fg_color="transparent")
        left.pack(side="left")
        section(left, "Sensibilité actuelle").pack(anchor="w")
        self.live = ctk.CTkLabel(left, text="—", font=font(34, "bold"), text_color=t.TEXT)
        self.live.pack(anchor="w")
        self.live_sub = ctk.CTkLabel(left, text="Appuie sur le bouton DPI de la souris pour changer de palier",
                                     font=font(11), text_color=t.MUTED)
        self.live_sub.pack(anchor="w")
        right = ctk.CTkFrame(inner, fg_color="transparent")
        right.pack(side="right")
        section(right, "Fréquence d'interrogation").pack(anchor="e")
        seg = segmented(right, list(POLL_LABELS.values()), self.set_poll)
        seg.set(POLL_LABELS.get(int(s.get("poll_rate", 1000)), "1000 Hz"))
        seg.pack(anchor="e", pady=(8, 0))

        stages = card(self)
        stages.pack(fill="both", expand=True, pady=(12, 0))
        head = ctk.CTkFrame(stages, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(16, 6))
        section(head, "Paliers de sensibilité").pack(side="left")
        ctk.CTkLabel(head, text="Clique sur un numéro pour choisir le palier actif", font=font(11),
                     text_color=t.MUTED).pack(side="right")
        self.rows = ctk.CTkFrame(stages, fg_color="transparent")
        self.rows.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self.build_rows()

    def build_rows(self):
        for w in self.rows.winfo_children():
            w.destroy()
        s = self.settings
        stages, active = s["dpi_stages"], int(s.get("active_stage", 1))
        self.entries = []
        for i in range(5):
            enabled = i < len(stages)
            value = stages[i] if enabled else min(DPI_MAX, (i + 1) * 800)
            row = ctk.CTkFrame(self.rows, fg_color=t.CARD_HI if enabled else "transparent", corner_radius=10)
            row.pack(fill="x", pady=3)
            is_active = enabled and i + 1 == active
            ctk.CTkButton(row, text=str(i + 1), width=34, height=34, corner_radius=17, font=font(13, "bold"),
                          fg_color=t.ACCENT if is_active else t.BORDER, hover_color=t.ACCENT_HOVER,
                          text_color=t.ACCENT_TEXT if is_active else t.TEXT,
                          state="normal" if enabled else "disabled",
                          command=lambda n=i + 1: self.set_active(n)).pack(side="left", padx=10, pady=8)
            sl = slider(row, DPI_MIN, DPI_MAX, lambda v, n=i: self.on_slide(n, v),
                        steps=(DPI_MAX - DPI_MIN) // DPI_STEP, state="normal" if enabled else "disabled")
            if not enabled:
                sl.configure(progress_color=t.BORDER, button_color=t.FAINT)
            sl.set(value)
            sl.pack(side="left", fill="x", expand=True, padx=8)
            entry = ctk.CTkEntry(row, width=80, justify="center", font=font(13, "bold"), fg_color=t.CARD,
                                 border_color=t.BORDER, text_color=t.TEXT if enabled else t.FAINT)
            entry.insert(0, str(value))
            entry.bind("<Return>", lambda e, n=i: self.on_entry(n))
            entry.bind("<FocusOut>", lambda e, n=i: self.on_entry(n))
            if not enabled:
                entry.configure(state="disabled")
            entry.pack(side="left", padx=(4, 6))
            ctk.CTkLabel(row, text="DPI", font=font(11), text_color=t.MUTED).pack(side="left", padx=(0, 8))
            sw, _ = switch(row, "", lambda n=i: self.toggle(n), enabled)
            sw.configure(width=46)
            if i == 0:
                sw.configure(state="disabled")
            sw.pack(side="right", padx=6)
            self.entries.append((sl, entry))

    def on_slide(self, n, value):
        value = int(round(value / DPI_STEP) * DPI_STEP)
        stages = self.settings["dpi_stages"]
        if n < len(stages):
            stages[n] = value
            _, entry = self.entries[n]
            entry.delete(0, "end")
            entry.insert(0, str(value))
            self.changed("dpi")

    def on_entry(self, n):
        stages = self.settings["dpi_stages"]
        if n >= len(stages):
            return
        sl, entry = self.entries[n]
        try:
            value = max(DPI_MIN, min(DPI_MAX, int(entry.get().replace(" ", ""))))
        except ValueError:
            value = stages[n]
        if value == stages[n]:
            return
        stages[n] = value
        entry.delete(0, "end")
        entry.insert(0, str(value))
        sl.set(value)
        self.changed("dpi")

    def toggle(self, n):
        stages = self.settings["dpi_stages"]
        if n < len(stages):
            del stages[n:]
        else:
            while len(stages) <= n:
                stages.append(min(DPI_MAX, (len(stages) + 1) * 800))
        self.settings["active_stage"] = min(int(self.settings.get("active_stage", 1)), len(stages))
        self.changed("dpi")
        self.build_rows()

    def set_active(self, n):
        self.settings["active_stage"] = n
        self.changed("dpi")
        self.build_rows()

    def set_poll(self, label):
        self.settings["poll_rate"] = int(label.split()[0])
        self.changed("poll_rate")

    def show_live(self, dpi, stage, count):
        self.live.configure(text=f"{dpi:,}".replace(",", " ") + " DPI")
        if stage and count:
            self.live_sub.configure(text=f"Palier {stage} sur {count}")
            if stage != self.settings.get("active_stage") and stage <= len(self.settings["dpi_stages"]):
                self.settings["active_stage"] = stage
                self.build_rows()


# --- Molette (souris) ---------------------------------------------------------------

class ScrollPage(Page):
    def __init__(self, master, app, device):
        super().__init__(master, app, device)
        s = self.settings
        c = card(self)
        c.pack(fill="x")
        body = ctk.CTkFrame(c, fg_color="transparent")
        body.pack(fill="x", padx=20, pady=18)
        section(body, "Mode de la molette").pack(anchor="w")
        seg = segmented(body, ["Crantée", "Libre"],
                        lambda v: self.set("scroll_mode", "free" if v == "Libre" else "tactile"))
        seg.set("Libre" if s.get("scroll_mode") == "free" else "Crantée")
        seg.pack(anchor="w", pady=(8, 4))
        ctk.CTkLabel(body, text="Libre : la molette tourne sans crans, pratique pour les longues pages.",
                     font=font(11), text_color=t.MUTED).pack(anchor="w", pady=(0, 16))
        for key, label, hint in (
            ("scroll_accel", "Accélération du défilement", "Défile plus loin quand tu tournes vite."),
            ("smart_reel", "Smart Reel", "Passe tout seul en mode libre quand tu lances la molette, puis revient en cranté."),
        ):
            sw, var = switch(body, label, None, bool(s.get(key, False)))
            sw.configure(command=lambda k=key, v=var: self.set(k, v.get()))
            sw.pack(anchor="w")
            ctk.CTkLabel(body, text=hint, font=font(11), text_color=t.MUTED).pack(anchor="w", padx=(52, 0), pady=(0, 12))

    def set(self, key, value):
        self.settings[key] = value
        self.changed("scroll")


# --- Alimentation --------------------------------------------------------------------

class PowerPage(Page):
    def __init__(self, master, app, device):
        super().__init__(master, app, device)
        c = card(self)
        c.pack(fill="x")
        body = ctk.CTkFrame(c, fg_color="transparent")
        body.pack(fill="x", padx=20, pady=18)
        section(body, "Batterie").pack(anchor="w")
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(6, 0))
        self.level = ctk.CTkLabel(row, text="—", font=font(34, "bold"), text_color=t.TEXT)
        self.level.pack(side="left")
        self.state = ctk.CTkLabel(row, text="", font=font(12), text_color=t.MUTED)
        self.state.pack(side="left", padx=14, pady=(12, 0))
        self.bar = ctk.CTkProgressBar(body, height=10, progress_color=t.ACCENT, fg_color=t.CARD_HI)
        self.bar.set(0)
        self.bar.pack(fill="x", pady=(10, 0))
        self.refresh(app.battery_cache.get(device.name))

        if "idle_time" in device.spec.features:
            c2 = card(self)
            c2.pack(fill="x", pady=(12, 0))
            body2 = ctk.CTkFrame(c2, fg_color="transparent")
            body2.pack(fill="x", padx=20, pady=18)
            head = ctk.CTkFrame(body2, fg_color="transparent")
            head.pack(fill="x")
            section(head, "Mise en veille après").pack(side="left")
            minutes = max(1, int(self.settings.get("idle_time", 300)) // 60)
            self.idle_label = ctk.CTkLabel(head, text=f"{minutes} min", font=font(12, "bold"), text_color=t.TEXT)
            self.idle_label.pack(side="right")
            s = slider(body2, 1, 15, self.set_idle, steps=14)
            s.set(minutes)
            s.pack(fill="x", pady=(8, 0))

    def set_idle(self, value):
        self.settings["idle_time"] = int(value) * 60
        self.idle_label.configure(text=f"{int(value)} min")
        self.changed("idle_time")

    def refresh(self, battery):
        if not battery:
            self.level.configure(text="—")
            self.state.configure(text="Non disponible (appareil en veille ou éteint)")
            return
        level, charging = battery
        low = level <= 15 and not charging
        self.level.configure(text=f"{level} %", text_color=t.DANGER if low else t.TEXT)
        self.state.configure(text="⚡ En charge" if charging else "Sur batterie")
        self.bar.configure(progress_color=t.DANGER if low else t.ACCENT)
        self.bar.set(level / 100)


# --- Audio (casque) ----------------------------------------------------------------

class AudioPage(Page):
    """Volumes, retour micro, égaliseurs et suppression de bruit, comme l'onglet Audio/Micro de Synapse."""

    def __init__(self, master, app, device):
        super().__init__(master, app, device)
        self.cfg = self.settings.setdefault("audio", {})
        self.out, self.mic = app.headset_endpoints()
        self.apo = audio.apo_config_dir()
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent", scrollbar_button_color=t.CARD_HI)
        scroll.pack(fill="both", expand=True)
        scroll.columnconfigure((0, 1), weight=1, uniform="audio")
        self.build_output(scroll)
        self.build_mic(scroll)
        self.build_apo_status(scroll)

    # Casque
    def build_output(self, master):
        c = card(master)
        c.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 12))
        body = ctk.CTkFrame(c, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=18)
        section(body, "Casque").pack(anchor="w")
        self.volume_row(body, self.out, "Volume")
        section(body, "Égaliseur").pack(anchor="w", pady=(18, 0))
        self.eq_block(body, "eq", audio.HEADSET_PRESETS, "Neutre")

    # Micro
    def build_mic(self, master):
        c = card(master)
        c.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 12))
        body = ctk.CTkFrame(c, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=18)
        section(body, "Micro").pack(anchor="w")
        self.volume_row(body, self.mic, "Sensibilité")
        # Retour micro : fait par le casque lui-même, comme dans Synapse (sans délai ni traitement Windows)
        side = self.cfg.setdefault("sidetone", {"on": False, "level": 50})
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(14, 0))
        ctk.CTkLabel(row, text="Retour micro", font=font(12), text_color=t.TEXT, anchor="w").pack(side="left")
        sw, self.side_var = switch(row, "Activé", self.set_sidetone, side.get("on", False))
        sw.pack(side="right")
        self.side_value = ctk.CTkLabel(row, text=f"{side.get('level', 50)} %", font=font(12, "bold"), text_color=t.TEXT)
        self.side_value.pack(side="right", padx=(0, 16))
        self.side_slider = slider(body, 0, 100, lambda v: self.set_sidetone(level=int(v)), 100)
        self.side_slider.set(side.get("level", 50))
        self.side_slider.pack(fill="x", pady=(6, 0))

        self.side_mode = segmented(body, list(SIDETONE_MODES), self.set_sidetone_mode)
        self.side_mode.set(next((k for k, v in SIDETONE_MODES.items() if v == side.get("mode", "headset")),
                                "Casque"))
        self.side_mode.pack(fill="x", pady=(10, 0))
        self.side_info = ctk.CTkLabel(body, text="", font=font(11), text_color=t.MUTED, wraplength=320,
                                      justify="left", anchor="w")
        self.side_info.pack(anchor="w", pady=(4, 0))
        self.show_sidetone_info()

        section(body, "Nettoyage de la voix").pack(anchor="w", pady=(18, 4))
        for key, label, hint in (
            ("noise", "Suppression de bruit", "Retire clavier, souris, souffle et ventilateur (RNNoise)."),
            ("highpass", "Coupe les graves parasites", "Enlève les bruits sourds : bureau, pas, vibrations (sous 90 Hz)."),
            ("declick", "Atténue les clics", "Adoucit le claquement sec des touches et de la souris (au-dessus de 8 kHz)."),
        ):
            sw, var = switch(body, label, None, bool(self.cfg.get(key, False)))
            sw.configure(command=lambda k=key, v=var: self.set(k, v.get()))
            sw.pack(anchor="w", pady=(6, 0))
            if not self.apo:
                sw.configure(state="disabled")
            ctk.CTkLabel(body, text=hint, font=font(11), text_color=t.MUTED, wraplength=300, justify="left",
                         anchor="w").pack(anchor="w", padx=(52, 0))
        section(body, "Égaliseur du micro").pack(anchor="w", pady=(18, 0))
        self.eq_block(body, "mic_eq", audio.MIC_PRESETS, "Neutre", bands=False)

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(14, 0))
        ctk.CTkLabel(row, text="Volume de la voix", font=font(12), text_color=t.TEXT, anchor="w").pack(side="left")
        self.gain_value = ctk.CTkLabel(row, text=f"+{self.cfg.get('mic_gain', 0)} dB", font=font(12, "bold"),
                                       text_color=t.TEXT)
        self.gain_value.pack(side="right")
        self.gain_slider = slider(body, 0, audio.MIC_GAIN_MAX, self.set_mic_gain, audio.MIC_GAIN_MAX)
        self.gain_slider.set(self.cfg.get("mic_gain", 0))
        self.gain_slider.pack(fill="x", pady=(6, 0))
        rec = button(body, "Réglage conseillé", self.recommended)
        rec.pack(anchor="w", pady=(12, 0))
        if not self.apo:
            self.gain_slider.configure(state="disabled")
            rec.configure(state="disabled")
        ctk.CTkLabel(body, text="Voix plus forte, clavier et souris retirés. Le volume est ajouté après le nettoyage, "
                     "donc les clics ne remontent pas avec.", font=font(11), text_color=t.MUTED, wraplength=320,
                     justify="left", anchor="w").pack(anchor="w", pady=(4, 0))

    def set_sidetone_mode(self, label):
        self.cfg.setdefault("sidetone", {"on": False, "level": 50})["mode"] = SIDETONE_MODES[label]
        self.set_sidetone()

    def show_sidetone_info(self):
        side = self.cfg.get("sidetone", {})
        if side.get("mode") != "app":
            text = "Casque : retour fait par le Kraken, comme dans Synapse."
        elif self.app.monitor.running:
            m = self.app.monitor
            if m.period_ms:
                text = (f"RazerLite basse latence : délai ≈ {m.latency_ms} ms "
                        f"(blocs de {m.period_ms:g} ms acceptés par le casque).")
            else:
                text = f"RazerLite : délai ≈ {m.latency_ms} ms (mode standard"
                text += f", basse latence refusée : {m.fallback_reason})." if m.fallback_reason else ")."
        elif self.app.monitor.error:
            text = f"RazerLite : {self.app.monitor.error}"
        else:
            text = "RazerLite : retour fait par le PC, sans le délai du firmware du casque."
        self.side_info.configure(text=text, text_color=t.DANGER if side.get("mode") == "app" and
                                 self.app.monitor.error else t.MUTED)

    def set_sidetone(self, level=None):
        side = self.cfg.setdefault("sidetone", {"on": False, "level": 50})
        side["on"] = bool(self.side_var.get())
        if level is not None:
            side["level"] = level
            self.side_value.configure(text=f"{level} %")
        self.app.schedule_apply(self.device, "sidetone")

    def volume_row(self, master, endpoint, label):
        row = ctk.CTkFrame(master, fg_color="transparent")
        row.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(row, text=label, font=font(12), text_color=t.TEXT, anchor="w").pack(side="left")
        if endpoint is None:
            ctk.CTkLabel(master, text="Kraken introuvable dans Windows (est-il branché ?)", font=font(11),
                         text_color=t.MUTED, anchor="w").pack(anchor="w")
            return
        sw, var = switch(row, "Muet", None, endpoint.muted())
        sw.configure(command=lambda: endpoint.set_muted(var.get()))
        sw.pack(side="right")
        value = ctk.CTkLabel(row, text=f"{endpoint.volume()} %", font=font(12, "bold"), text_color=t.TEXT)
        value.pack(side="right", padx=(0, 16))
        s = slider(master, 0, 100, lambda v: (endpoint.set_volume(int(v)), value.configure(text=f"{int(v)} %")), 100)
        s.set(endpoint.volume())
        s.pack(fill="x", pady=(6, 0))

    def eq_block(self, master, key, presets, default, bands=True):
        current = self.cfg.get(key, default)
        names = list(presets) + (["Perso"] if bands else [])
        seg = segmented(master, names, lambda v: self.set_preset(key, presets, v))
        seg.set(current if current in names else default)
        seg.pack(anchor="w", pady=(8, 0))
        if not self.apo:
            seg.configure(state="disabled")
        if not bands:
            return
        grid = ctk.CTkFrame(master, fg_color="transparent")
        grid.pack(fill="x", pady=(12, 0))
        gains = self.gains(key, presets, default)
        self.band_sliders = []
        for i, label in enumerate(audio.EQ_LABELS):
            grid.columnconfigure(i, weight=1)
            s = ctk.CTkSlider(grid, from_=-12, to=12, number_of_steps=24, orientation="vertical", height=120,
                              width=16, progress_color=t.ACCENT, button_color=t.TEXT, button_hover_color=t.ACCENT,
                              fg_color=t.CARD_HI, command=lambda v, n=i: self.set_band(key, seg, n, v))
            s.set(gains[i])
            s.grid(row=0, column=i)
            if not self.apo:
                s.configure(state="disabled")
            ctk.CTkLabel(grid, text=label, font=font(10), text_color=t.MUTED).grid(row=1, column=i)
            self.band_sliders.append(s)

    def gains(self, key, presets, default):
        name = self.cfg.get(key, default)
        if name == "Perso":
            return list(self.cfg.get(key + "_custom", presets[default]))
        return list(presets.get(name, presets[default]))

    def set_preset(self, key, presets, name):
        self.cfg[key] = name
        if name != "Perso" and key == "eq":
            for s, g in zip(self.band_sliders, presets[name]):
                s.set(g)
        self.app.apply_audio(self.device)

    def set_band(self, key, seg, n, value):
        gains = [round(s.get()) for s in self.band_sliders]
        self.cfg[key] = "Perso"
        self.cfg[key + "_custom"] = gains
        seg.set("Perso")
        self.app.apply_audio(self.device)

    def set(self, key, value):
        self.cfg[key] = value
        self.app.apply_audio(self.device)

    def set_mic_gain(self, value):
        self.cfg["mic_gain"] = int(round(value))
        self.gain_value.configure(text=f"+{self.cfg['mic_gain']} dB")
        self.app.apply_audio(self.device)

    def recommended(self):
        self.cfg.update(audio.MIC_RECOMMENDED)
        self.app.apply_audio(self.device)
        self.app.after(0, self.app.show_page, "Audio")  # recharge la page pour afficher les nouveaux réglages

    # Equalizer APO
    def build_apo_status(self, master):
        c = card(master)
        c.grid(row=1, column=0, columnspan=2, sticky="ew")
        body = ctk.CTkFrame(c, fg_color="transparent")
        body.pack(fill="x", padx=20, pady=16)
        if self.apo:
            ctk.CTkLabel(body, text="Égaliseurs et nettoyage de la voix passent par Equalizer APO (installé). "
                         "Si un réglage du micro ne change rien, ouvre « Equalizer APO Device Selector » et coche le micro "
                         "du Kraken dans « Capture devices », puis redémarre le PC. Ne coche pas la sortie du Kraken "
                         "(« Playback devices ») : avec les effets THX du pilote Razer, elle coupe tout le son.",
                         font=font(11), text_color=t.MUTED, wraplength=700, justify="left", anchor="w").pack(anchor="w")
            return
        ctk.CTkLabel(body, text="Pour l'égaliseur et la suppression de bruit, installe Equalizer APO (gratuit, libre)",
                     font=font(12, "bold"), text_color=t.TEXT).pack(anchor="w")
        ctk.CTkLabel(body, text="Pendant l'installation, coche seulement le micro du Kraken dans « Capture devices », puis redémarre "
                     "le PC. Ne coche pas sa sortie (« Playback devices ») : avec THX, elle coupe tout le son.",
                     font=font(11), text_color=t.MUTED, wraplength=700, justify="left", anchor="w").pack(anchor="w", pady=(4, 10))
        button(body, "Télécharger Equalizer APO ↗", lambda: webbrowser.open(audio.APO_DOWNLOAD), primary=True,
               height=32).pack(anchor="w")


PAGE_CLASSES = {"Éclairage": LightingPage, "Performance": PerformancePage,
                "Molette": ScrollPage, "Alimentation": PowerPage, "Audio": AudioPage}


# --- Fenêtre principale -----------------------------------------------------------

class DeviceItem(ctk.CTkFrame):
    def __init__(self, master, device, command):
        super().__init__(master, fg_color="transparent", corner_radius=10, cursor="hand2")
        self.device = device
        self.icon = ctk.CTkLabel(self, text=KIND_ICONS[device.kind], font=font(20), width=36)
        self.icon.grid(row=0, column=0, rowspan=2, padx=(10, 6), pady=8)
        self.title = ctk.CTkLabel(self, text=KIND_LABELS[device.kind], font=font(13, "bold"), anchor="w",
                                  text_color=t.TEXT)
        self.title.grid(row=0, column=1, sticky="w", pady=(8, 0))
        self.sub = ctk.CTkLabel(self, text=device.name.split(" (")[0], font=font(11), anchor="w", text_color=t.MUTED)
        self.sub.grid(row=1, column=1, sticky="w", pady=(0, 8))
        self.battery = ctk.CTkLabel(self, text="", font=font(11), text_color=t.MUTED)
        self.battery.grid(row=0, column=2, rowspan=2, padx=10)
        self.columnconfigure(1, weight=1)
        for w in (self, self.icon, self.title, self.sub, self.battery):
            w.bind("<Button-1>", lambda e: command(device))

    def select(self, selected):
        self.configure(fg_color=t.CARD_HI if selected else "transparent")
        self.title.configure(text_color=t.ACCENT if selected else t.TEXT)


class App(ctk.CTk):
    def __init__(self, start_in_tray=False):
        ctk.set_appearance_mode("dark")
        super().__init__(fg_color=t.BG)
        self.title("RazerLite")
        self.geometry("1120x720")
        self.minsize(1000, 660)
        self.cfg = profiles.load()
        self.devices, self.items, self.pages = [], [], {}
        self.current, self.page_name = None, None
        self.battery_cache = {}
        self.firmware_cache = {}
        self._headset_audio = None
        self._apply_jobs = {}
        self.monitor = monitor.AutoMonitor()
        self.tray = None
        self.low_warned = set()
        self.osd = DpiOsd(self)
        self._dpi_last = None
        self.set_icon()
        self.build()
        self.scan(apply=start_in_tray)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.setup_tray()
        if start_in_tray and self.tray:
            self.withdraw()
        self.after(1000, self.dpi_watch)
        self.after(60_000, self.battery_loop)
        self.update_info = None
        self._from_threads = queue.SimpleQueue()
        self.after(100, self.run_thread_calls)
        self.after(700, self.watch_show_requests)
        self.after(4000, self.check_updates)

    # --- construction ---
    def icon_image(self, size=64):
        return logo.app_icon(size)

    def set_icon(self):
        try:
            from PIL import ImageTk
            self._icon = ImageTk.PhotoImage(self.icon_image())
            self.iconphoto(True, self._icon)
        except Exception:
            pass
        # Sous Windows, la barre des tâches lit l'icône .ico. L'appel à iconbitmap empêche aussi
        # customtkinter de remettre sa propre icône bleue 200 ms après l'ouverture.
        path = logo.ico_path()
        if sys.platform == "win32" and path:
            try:
                self.iconbitmap(default=path)
            except tk.TclError:
                pass

    def build(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        side = ctk.CTkFrame(self, fg_color=t.SIDEBAR, corner_radius=0, width=260)
        side.grid(row=0, column=0, sticky="nsw")
        side.pack_propagate(False)
        mark = logo.wordmark(76)  # dessiné en double pour rester net sur les écrans haute densité
        self._wordmark = ctk.CTkImage(light_image=mark, dark_image=mark, size=(mark.width // 2, mark.height // 2))
        ctk.CTkLabel(side, text="", image=self._wordmark).pack(anchor="w", padx=18, pady=(22, 24))
        section(side, "Appareils").pack(fill="x", padx=22)
        self.device_list = ctk.CTkFrame(side, fg_color="transparent")
        self.device_list.pack(fill="x", padx=12, pady=(8, 0))

        bottom = ctk.CTkFrame(side, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=18, pady=18)
        section(bottom, "Profil").pack(fill="x")
        self.profile_menu = ctk.CTkOptionMenu(bottom, values=["Défaut"], command=self.switch_profile, font=font(12),
                                              fg_color=t.CARD_HI, button_color=t.BORDER, button_hover_color=t.FAINT,
                                              dropdown_fg_color=t.CARD_HI, dropdown_hover_color=t.BORDER,
                                              text_color=t.TEXT, corner_radius=8)
        self.profile_menu.pack(fill="x", pady=(8, 6))
        row = ctk.CTkFrame(bottom, fg_color="transparent")
        row.pack(fill="x", pady=(0, 14))
        button(row, "Nouveau", self.new_profile, height=30, width=100).pack(side="left", fill="x", expand=True, padx=(0, 4))
        button(row, "Supprimer", self.delete_profile, height=30, width=100).pack(side="left", fill="x", expand=True, padx=(4, 0))
        sw, self.osd_var = switch(bottom, "Notification DPI", self.toggle_osd, self.cfg.get("osd", True))
        sw.pack(anchor="w", pady=3)
        sw, self.autostart_var = switch(bottom, "Démarrer avec Windows", self.toggle_autostart,
                                        profiles.autostart_enabled())
        sw.pack(anchor="w", pady=3)
        button(bottom, "↻  Rechercher les appareils", self.scan, height=32).pack(fill="x", pady=(14, 0))
        self.update_button = button(bottom, "⇩  Rechercher une mise à jour", lambda: self.check_updates(True), height=32)
        self.update_button.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(bottom, text=f"version {__version__}", font=font(10), text_color=t.FAINT).pack(pady=(10, 0))

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=28, pady=(22, 10))
        main.columnconfigure(0, weight=1)
        main.rowconfigure(3, weight=1)
        self.build_update_banner(main)
        header = ctk.CTkFrame(main, fg_color="transparent")
        header.grid(row=1, column=0, sticky="ew")
        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.pack(side="left")
        self.h_title = ctk.CTkLabel(titles, text="", font=font(24, "bold"), text_color=t.TEXT, anchor="w")
        self.h_title.pack(anchor="w")
        self.h_sub = ctk.CTkLabel(titles, text="", font=font(12), text_color=t.MUTED, anchor="w")
        self.h_sub.pack(anchor="w")
        self.h_battery = ctk.CTkLabel(header, text="", font=font(12, "bold"), corner_radius=12, fg_color=t.CARD_HI,
                                      text_color=t.TEXT, height=28, padx=12)
        self.h_battery.pack(side="right")
        button(header, "Firmware Razer ↗", self.open_firmware_page, height=28, width=130).pack(side="right", padx=(0, 8))
        self.tabs = segmented(main, ["Éclairage"], self.show_page, height=34)
        self.tabs.grid(row=2, column=0, sticky="w", pady=(16, 14))
        self.content = ctk.CTkFrame(main, fg_color="transparent")
        self.content.grid(row=3, column=0, sticky="nsew")
        self.status_label = ctk.CTkLabel(main, text="", font=font(11), text_color=t.MUTED, anchor="w")
        self.status_label.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.refresh_profiles()

    def build_update_banner(self, master):
        self.banner = ctk.CTkFrame(master, fg_color=t.CARD_HI, corner_radius=12, border_width=1, border_color=t.ACCENT)
        self.banner_text = ctk.CTkLabel(self.banner, text="", font=font(12), text_color=t.TEXT, anchor="w",
                                        justify="left")
        self.banner_text.pack(side="left", padx=16, pady=10, fill="x", expand=True)
        self.banner_later = button(self.banner, "Plus tard", self.hide_update, height=30, width=90)
        self.banner_later.pack(side="right", padx=(6, 12))
        self.banner_go = button(self.banner, "Mettre à jour", self.install_update, primary=True, height=30, width=120)
        self.banner_go.pack(side="right")
        self.banner_bar = ctk.CTkProgressBar(self.banner, width=140, progress_color=t.ACCENT)

    def from_thread(self, fn, *args):
        """Fait exécuter fn par l'interface (tkinter ne doit être touché que depuis son propre fil)."""
        self._from_threads.put((fn, args))

    def run_thread_calls(self):
        while not self._from_threads.empty():
            fn, args = self._from_threads.get()
            fn(*args)
        self.after(100, self.run_thread_calls)

    def watch_show_requests(self):
        if instance.show_requested():
            self.show()
        self.after(700, self.watch_show_requests)

    # --- mises à jour ---
    def check_updates(self, manual=False):
        if not manual:
            self.after(6 * 3600 * 1000, self.check_updates)
        if not updater.repo():
            if manual:
                self.tell_update("Mises à jour non configurées (dépôt GitHub inconnu).")
            return
        if manual:
            self.update_button.configure(state="disabled", text="Recherche en cours…")

        def work():
            try:
                info = updater.check()
            except Exception as exc:  # pas d'Internet, GitHub indisponible…
                info = exc
            self.from_thread(self.on_update_checked, info, manual)

        threading.Thread(target=work, daemon=True).start()

    def tell_update(self, text):
        """Réponse à une recherche demandée : dans la fenêtre si elle est ouverte, sinon en notification."""
        if self.winfo_viewable():
            self.status(text)
        else:
            self.notify(text)

    def on_update_checked(self, info, manual):
        if manual:
            self.update_button.configure(state="normal", text="⇩  Rechercher une mise à jour")
        if isinstance(info, Exception):
            if manual:
                self.tell_update("Impossible de vérifier les mises à jour (connexion ?).")
            return
        if not info:
            if manual:
                self.tell_update(f"RazerLite est à jour (version {__version__}).")
            return
        if manual:
            self.status(f"Nouvelle version {info['version']} disponible : clique sur « Mettre à jour » en haut.")
        first = not self.update_info or self.update_info["version"] != info["version"]
        self.update_info = info
        notes = info["notes"].splitlines()[0] if info["notes"] else ""
        text = f"Nouvelle version {info['version']} disponible (tu as la {__version__})."
        self.banner_text.configure(text=text + (f"\n{notes[:110]}" if notes else ""))
        self.banner.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        if first and not self.winfo_viewable():
            self.notify(f"Nouvelle version {info['version']} disponible : ouvre RazerLite pour l'installer.")

    def hide_update(self):
        self.banner.grid_remove()

    def install_update(self):
        info = self.update_info
        if not info:
            return
        self.banner_go.pack_forget()
        self.banner_later.pack_forget()
        self.banner_bar.set(0)
        self.banner_bar.pack(side="right", padx=16)
        self.banner_text.configure(text=f"Téléchargement de la version {info['version']}…")

        def work():
            try:
                updater.install(info, lambda frac: self.from_thread(self.banner_bar.set, frac))
            except Exception as exc:
                self.from_thread(self.update_failed, exc)
                return
            self.from_thread(self.update_done)

        threading.Thread(target=work, daemon=True).start()

    def update_done(self):
        self.banner_text.configure(text="Mise à jour installée, redémarrage…")
        profiles.save(self.cfg)
        self.after(600, self.quit_app)

    def update_failed(self, exc):
        self.banner_bar.pack_forget()
        self.banner_later.pack(side="right", padx=(6, 12))
        self.banner_go.pack(side="right")
        self.banner_text.configure(text=f"La mise à jour a échoué : {exc}")

    def status(self, text, error=False):
        self.status_label.configure(text=text, text_color=t.DANGER if error else t.MUTED)

    def refresh_profiles(self):
        profiles.active_profile(self.cfg)
        self.profile_menu.configure(values=list(self.cfg.get("profiles", {})))
        self.profile_menu.set(self.cfg.get("active"))

    def device_settings(self, device):
        profile = profiles.active_profile(self.cfg)
        settings = profile.setdefault(device.kind, copy.deepcopy(profiles.DEFAULT_PROFILE[device.kind]))
        for key, value in profiles.DEFAULT_PROFILE[device.kind].items():
            settings.setdefault(key, copy.deepcopy(value))
        return settings

    # --- audio du casque ---
    def headset_endpoints(self):
        if self._headset_audio is None:
            try:
                self._headset_audio = audio.find_headset()
            except Exception as exc:
                self.status(f"Audio du casque inaccessible : {exc}", True)
                self._headset_audio = (None, None)
        return self._headset_audio

    def sync_sidetone(self, device):
        """Applique le retour micro choisi : celui du casque, ou celui de RazerLite (le casque coupe alors le sien)."""
        side = self.device_settings(device).get("audio", {}).get("sidetone", {})
        on, level = bool(side.get("on")), int(side.get("level", 50))
        if side.get("mode") == "app":
            device.set_sidetone(False, level)
            if on:
                try:
                    self.monitor.start(level)
                    self.monitor.error = None
                except RuntimeError as exc:
                    self.monitor.error = str(exc)
                    self.status(f"Retour micro RazerLite : {exc}", True)
            else:
                self.monitor.stop()
        else:
            self.monitor.stop()
            device.set_sidetone(on, level)
        page = self.pages.get("Audio") if device is self.current else None
        if page is not None and hasattr(page, "show_sidetone_info"):
            page.show_sidetone_info()

    def apply_audio(self, device):
        key = (device.name, "audio")
        if key in self._apply_jobs:
            self.after_cancel(self._apply_jobs[key])
        self._apply_jobs[key] = self.after(250, lambda: self._apply_audio(device, key))

    def _apply_audio(self, device, key):
        self._apply_jobs.pop(key, None)
        cfg = self.device_settings(device).setdefault("audio", {})
        out, mic = self.headset_endpoints()
        noise_dll = None
        if cfg.get("noise") and mic is not None:
            noise_dll = audio.rnnoise_dll(mic.channels())
            if noise_dll is None:
                self.status("Téléchargement du filtre anti-bruit RNNoise…")

                def work():
                    try:
                        audio.download_rnnoise()
                    except Exception as exc:
                        self.from_thread(self.status, f"Téléchargement de RNNoise impossible : {exc}", True)
                        return
                    if audio.rnnoise_dll(mic.channels()) is None:
                        self.from_thread(self.status, "RNNoise téléchargé mais introuvable dans l'archive.", True)
                        return
                    self.from_thread(self.apply_audio, device)

                threading.Thread(target=work, daemon=True).start()
                return

        def gains(k, presets):
            name = cfg.get(k, "Neutre")
            return cfg.get(k + "_custom") if name == "Perso" else presets.get(name)

        text = audio.build_config(out.guid if out else None, mic.guid if mic else None,
                                  gains("eq", audio.HEADSET_PRESETS), gains("mic_eq", audio.MIC_PRESETS),
                                  noise_dll, bool(cfg.get("highpass")), cfg.get("mic_gain", 0),
                                  bool(cfg.get("declick")))
        try:
            audio.write_apo_config(text)
            profiles.save(self.cfg)
            self.status("Réglages audio appliqués.")
        except PermissionError:
            self.status("Equalizer APO refuse l'écriture : lance RazerLite une fois en administrateur.", True)
        except OSError as exc:
            self.status(f"Réglages audio : {exc}", True)

    # --- appareils ---
    def scan(self, apply=False):
        for d in self.devices:
            d.close()
        for w in self.device_list.winfo_children():
            w.destroy()
        try:
            self.devices = find_devices()
        except RazerError as exc:
            self.devices = []
            self.status(str(exc), True)
        self.items = [DeviceItem(self.device_list, d, self.select_device) for d in self.devices]
        for item in self.items:
            item.pack(fill="x", pady=2)
        self._dpi_last = None
        # Rend la main au firmware : sans ça, les boutons DPI restent muets quand Synapse est fermé
        for d in self.devices:
            if "device_mode" in d.spec.features:
                try:
                    if d.set_normal_mode():
                        self.status(f"{d.name} : mode matériel réactivé, les boutons DPI refonctionnent.")
                except RazerError:
                    pass
        self.refresh_batteries()
        if self.devices:
            if apply:
                self.apply_all()
            self.select_device(self.current if self.current in self.devices else self.devices[0])
        else:
            self.show_empty()

    def show_empty(self):
        self.current = None
        self.h_title.configure(text="Aucun appareil")
        self.h_sub.configure(text="")
        self.h_battery.configure(text="", fg_color="transparent")
        self.tabs.grid_remove()
        for w in self.content.winfo_children():
            w.destroy()
        c = card(self.content)
        c.pack(fill="both", expand=True)
        ctk.CTkLabel(c, text="Aucun périphérique Razer reconnu", font=font(18, "bold"),
                     text_color=t.TEXT).pack(pady=(120, 8))
        ctk.CTkLabel(c, text="Ferme Razer Synapse (synapse-off.bat), rebranche le câble ou le dongle,\n"
                             "puis clique sur « Rechercher les appareils ».",
                     font=font(12), text_color=t.MUTED).pack()

    def select_device(self, device):
        self.current = device
        for item in self.items:
            item.select(item.device is device)
        wireless = "Sans fil (HyperSpeed)" if device.spec.wireless else "Filaire"
        self.h_title.configure(text=device.name.split(" (")[0])
        firmware = self.firmware_version(device)
        self.h_sub.configure(text=f"{KIND_LABELS[device.kind]} · {wireless}" + (f" · Firmware {firmware}" if firmware else ""))
        self.update_header_battery()
        pages = PAGES[device.kind]
        if "battery" not in device.spec.features:
            pages = [p for p in pages if p != "Alimentation"]
        self.tabs.configure(values=pages)
        self.tabs.grid()
        name = self.page_name if self.page_name in pages else pages[0]
        self.tabs.set(name)
        self.show_page(name)

    def firmware_version(self, device):
        if device.name not in self.firmware_cache:
            try:
                version = device.firmware()
            except (RazerError, OSError):
                version = None
            self.firmware_cache[device.name] = version if version and version != "?" else None
        return self.firmware_cache[device.name]

    def open_firmware_page(self):
        """Les firmwares se mettent à jour avec les outils officiels de Razer (pas besoin de Synapse)."""
        model = self.current.name.split(" (")[0] if self.current else "Basilisk V3 Pro"
        firmware = self.firmware_version(self.current) if self.current else None
        mine = f"Ta version actuelle : {firmware}.\n\n" if firmware else ""
        if not messagebox.askokcancel(
                "Mise à jour du firmware",
                f"{mine}La page d'assistance Razer va s'ouvrir. Si un « Firmware Updater » plus récent y est proposé "
                f"pour le {model}, télécharge-le.\n\nAvant de le lancer, quitte RazerLite (icône de la barre des tâches "
                "> Quitter) et branche l'appareil en USB (avec le dongle pour la souris).", parent=self):
            return
        query = urllib.parse.quote(f"{model} firmware updater")
        webbrowser.open(f"https://mysupport.razer.com/app/answers/list/kw/{query}")

    def show_page(self, name):
        self.page_name = name
        for w in self.content.winfo_children():
            w.destroy()
        page = PAGE_CLASSES[name](self.content, self, self.current)
        page.pack(fill="both", expand=True)
        self.pages = {name: page}
        if name == "Performance" and self._dpi_last:
            page.show_live(*self._dpi_last)

    # --- application des réglages (en direct, avec un petit délai) ---
    def schedule_apply(self, device, what):
        key = (device.name, what)
        if key in self._apply_jobs:
            self.after_cancel(self._apply_jobs[key])
        self._apply_jobs[key] = self.after(180, lambda: self._apply(device, what, key))

    def _apply(self, device, what, key):
        self._apply_jobs.pop(key, None)
        s = self.device_settings(device)
        try:
            if what == "lighting":
                profiles.apply_lighting(device, s["lighting"])
                if s["lighting"].get("effect") != "off" and "brightness" in device.spec.features:
                    device.set_brightness(int(s.get("brightness", 100)))
            elif what == "brightness":
                device.set_brightness(int(s.get("brightness", 100)))
            elif what == "sidetone":
                self.sync_sidetone(device)
            elif what == "dpi":
                stages = s["dpi_stages"][:5] or [800]
                active = max(1, min(len(stages), int(s.get("active_stage", 1))))
                device.set_dpi_stages(stages, active)
                device.set_dpi(stages[active - 1])
            elif what == "poll_rate":
                device.set_poll_rate(int(s["poll_rate"]))
            elif what == "scroll":
                device.set_scroll_mode(s.get("scroll_mode", "tactile"))
                device.set_scroll_acceleration(bool(s.get("scroll_accel")))
                device.set_smart_reel(bool(s.get("smart_reel")))
            elif what == "idle_time":
                device.set_idle_time(int(s["idle_time"]))
            self.status(f"Enregistré dans le profil « {self.cfg['active']} ».")
        except RazerError as exc:
            self.status(str(exc), True)
        profiles.save(self.cfg)

    def apply_all(self):
        errors = profiles.apply_profile(self.devices, profiles.active_profile(self.cfg))
        for d in self.devices:
            if hasattr(d, "set_sidetone"):
                try:
                    self.sync_sidetone(d)
                except RazerError:
                    pass
        self.status("\n".join(errors) if errors else f"Profil « {self.cfg['active']} » appliqué.", bool(errors))

    # --- suivi DPI et batterie ---
    def dpi_watch(self):
        mouse = next((d for d in self.devices if "dpi" in d.spec.features), None)
        delay = 250
        if mouse is not None:
            try:
                dpi = mouse.dpi()[0]
                if self._dpi_last is None or dpi != self._dpi_last[0]:
                    stages, stage = mouse.dpi_stages()
                    first = self._dpi_last is None
                    self._dpi_last = (dpi, stage, len(stages))
                    if not first and self.cfg.get("osd", True):
                        self.osd.show(dpi, stage, len(stages))
                    lighting = self.pages.get("Éclairage")
                    if not first and lighting is not None and lighting.winfo_exists() and self.current is mouse:
                        lighting.preview.flash("dpi")
                    page = self.pages.get("Performance")
                    if page is not None and page.winfo_exists():
                        page.show_live(*self._dpi_last)
            except RazerError:
                delay = 3000  # souris en veille ou débranchée : on réessaie plus tard
            except Exception as exc:  # quoi qu'il arrive, la surveillance du bouton DPI ne doit jamais s'arrêter
                mouse.close()
                self.status(f"Surveillance DPI : {exc}", True)
                delay = 3000
        self.after(delay, self.dpi_watch)

    def refresh_batteries(self):
        for item in self.items:
            d = item.device
            try:
                b = d.battery()
            except RazerError:
                b = None
            self.battery_cache[d.name] = b
            if b:
                low = b[0] <= 15 and not b[1]
                item.battery.configure(text=f"{'⚡' if b[1] else ''}{b[0]} %", text_color=t.DANGER if low else t.MUTED)
                if low and d.name not in self.low_warned:
                    self.low_warned.add(d.name)
                    self.notify(f"{d.name} : batterie faible ({b[0]} %)")
                elif not low:
                    self.low_warned.discard(d.name)
        self.update_header_battery()
        page = self.pages.get("Alimentation")
        if page is not None and page.winfo_exists() and self.current:
            page.refresh(self.battery_cache.get(self.current.name))

    def update_header_battery(self):
        b = self.battery_cache.get(self.current.name) if self.current else None
        if b:
            low = b[0] <= 15 and not b[1]
            self.h_battery.configure(text=f"{'⚡ ' if b[1] else '🔋 '}{b[0]} %", fg_color=t.CARD_HI,
                                     text_color=t.DANGER if low else t.TEXT)
        else:
            self.h_battery.configure(text="", fg_color="transparent")

    def battery_loop(self):
        self.refresh_batteries()
        self.after(60_000, self.battery_loop)

    # --- profils ---
    def switch_profile(self, name):
        self.cfg["active"] = name
        profiles.save(self.cfg)
        self.refresh_profiles()
        self.apply_all()
        if self.current:
            self.show_page(self.page_name)
        self.update_tray_menu()

    def new_profile(self):
        dialog = ctk.CTkInputDialog(text="Nom du nouveau profil (copie du profil actuel) :", title="Nouveau profil",
                                    button_fg_color=t.ACCENT, button_hover_color=t.ACCENT_HOVER,
                                    button_text_color=t.ACCENT_TEXT)
        name = (dialog.get_input() or "").strip()
        if not name:
            return
        self.cfg["profiles"][name] = copy.deepcopy(profiles.active_profile(self.cfg))
        self.switch_profile(name)

    def delete_profile(self):
        name = self.cfg.get("active")
        if len(self.cfg["profiles"]) <= 1:
            self.status("Il faut garder au moins un profil.", True)
            return
        if messagebox.askyesno("RazerLite", f"Supprimer le profil « {name} » ?", parent=self):
            del self.cfg["profiles"][name]
            self.switch_profile(next(iter(self.cfg["profiles"])))

    def toggle_osd(self):
        self.cfg["osd"] = bool(self.osd_var.get())
        profiles.save(self.cfg)
        if self.cfg["osd"] and self._dpi_last:
            self.osd.show(*self._dpi_last)

    def toggle_autostart(self):
        try:
            profiles.set_autostart(self.autostart_var.get())
            self.status("Démarrage avec Windows " + ("activé." if self.autostart_var.get() else "désactivé."))
        except (RazerError, OSError) as exc:
            self.autostart_var.set(False)
            self.status(str(exc), True)

    # --- barre des tâches ---
    def setup_tray(self):
        try:
            import pystray
        except Exception:  # module absent ou pas de zone de notification disponible
            return
        self.pystray = pystray
        self.tray = pystray.Icon("RazerLite", self.icon_image(), "RazerLite", menu=self.tray_menu())
        self.tray.run_detached()

    def tray_menu(self):
        ps = self.pystray

        def profile_item(name):
            return ps.MenuItem(name, lambda: self.after(0, self.switch_profile, name),
                               checked=lambda item: self.cfg.get("active") == name, radio=True)

        return ps.Menu(
            ps.MenuItem("Ouvrir RazerLite", lambda: self.after(0, self.show), default=True),
            ps.Menu.SEPARATOR,
            *[profile_item(n) for n in self.cfg.get("profiles", {})],
            ps.Menu.SEPARATOR,
            ps.MenuItem("Rechercher une mise à jour", lambda: self.after(0, self.check_updates, True)),
            ps.MenuItem("Quitter", lambda: self.after(0, self.quit_app)),
        )

    def update_tray_menu(self):
        if self.tray:
            self.tray.menu = self.tray_menu()
            self.tray.update_menu()

    def notify(self, text):
        if self.tray:
            try:
                self.tray.notify(text, "RazerLite")
                return
            except Exception:
                pass
        self.status(text, True)

    def show(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def on_close(self):
        profiles.save(self.cfg)
        if self.tray:
            self.withdraw()
        else:
            self.quit_app()

    def quit_app(self):
        if self.tray:
            # retirer l'icône tout de suite : si le programme se ferme avant, Windows en garde un fantôme
            try:
                self.tray.visible = False
            except Exception:
                pass
            self.tray.stop()
        self.monitor.stop()
        for d in self.devices:
            d.close()
        self.destroy()


def run(start_in_tray=False, after_update=False):
    # Après une mise à jour, l'ancienne copie est en train de se fermer : on lui laisse le temps.
    lock = instance.acquire(wait=20 if after_update else 0)
    if lock is None:
        instance.ask_existing_to_show()
        return 0
    instance.show_requested()  # efface une vieille demande restée en plan
    if sys.platform == "win32":
        # Identité propre : la barre des tâches n'affiche plus RazerLite comme « Python » avec son icône
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RazerLite.App")
        except (AttributeError, OSError):
            pass
    app = App(start_in_tray=start_in_tray)
    app.mainloop()
    return 0
