"""Profils (JSON dans %APPDATA%\\RazerLite) et application aux appareils."""

import copy
import json
import os
import sys
from pathlib import Path

from .devices import RazerError

DEFAULT_PROFILE = {
    "mouse": {
        "lighting": {"effect": "static", "zone": "Tout", "color1": "#00ff88", "color2": None,
                     "speed": 2, "direction": 1,
                     "zone_colors": {"Molette": "#00ff88", "Logo": "#00ff88", "Bande": "#0066ff"}},
        "brightness": 100,
        "dpi_stages": [800, 1600, 3200],
        "active_stage": 2,
        "poll_rate": 1000,
        "idle_time": 300,
        "scroll_mode": "tactile",
        "scroll_accel": False,
        "smart_reel": False,
    },
    "keyboard": {
        "lighting": {"effect": "static", "zone": "Clavier", "color1": "#00ff88", "color2": None,
                     "speed": 2, "direction": 1},
        "brightness": 80,
    },
    "headset": {
        "lighting": {"effect": "static", "zone": "Casque", "color1": "#00ff88", "color2": None,
                     "speed": 2, "direction": 1},
        "brightness": 100,
    },
}

DEFAULT_CONFIG = {
    "active": "Défaut",
    "osd": True,
    "profiles": {
        "Défaut": DEFAULT_PROFILE,
        "Nuit": {
            "mouse": {**DEFAULT_PROFILE["mouse"], "brightness": 20,
                      "lighting": {**DEFAULT_PROFILE["mouse"]["lighting"], "color1": "#ff4400"}},
            "keyboard": {**DEFAULT_PROFILE["keyboard"], "brightness": 15,
                         "lighting": {**DEFAULT_PROFILE["keyboard"]["lighting"], "color1": "#ff4400"}},
            "headset": {**DEFAULT_PROFILE["headset"],
                        "lighting": {**DEFAULT_PROFILE["headset"]["lighting"], "effect": "off"}},
        },
    },
}


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or Path.home() / ".config"
    path = Path(base) / "RazerLite"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return config_dir() / "config.json"


def load() -> dict:
    path = config_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            path.rename(path.with_suffix(".json.bak"))
    return copy.deepcopy(DEFAULT_CONFIG)


def save(config: dict):
    tmp = config_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(config_path())


def active_profile(config: dict) -> dict:
    profiles = config.setdefault("profiles", {})
    name = config.get("active")
    if name not in profiles:
        name = next(iter(profiles), "Défaut")
        profiles.setdefault(name, copy.deepcopy(DEFAULT_PROFILE))
        config["active"] = name
    return profiles[name]


def apply_lighting(device, lighting: dict):
    effect = lighting.get("effect", "static")
    if effect == "zones":
        device.set_zone_colors(lighting.get("zone_colors", {}))
        return
    device.set_effect(effect, zone=lighting.get("zone"), color1=lighting.get("color1") or "#00ff88",
                      color2=lighting.get("color2"), speed=int(lighting.get("speed", 2)),
                      direction=int(lighting.get("direction", 1)))


def apply_device(device, settings: dict):
    """Applique les réglages d'un appareil. Renvoie la liste des erreurs (on continue malgré elles)."""
    errors = []

    def attempt(label, fn, *args):
        try:
            fn(*args)
        except RazerError as exc:
            errors.append(f"{label} : {exc}")

    features = device.spec.features
    if "device_mode" in features:
        attempt("mode", device.set_normal_mode)
    if "lighting" in settings:
        attempt("éclairage", apply_lighting, device, settings["lighting"])
    if "brightness" in settings and "brightness" in features and settings.get("lighting", {}).get("effect") != "off":
        attempt("luminosité", device.set_brightness, int(settings["brightness"]))
    if "dpi" in features and settings.get("dpi_stages"):
        stages = [int(s) for s in settings["dpi_stages"]][:5]
        active = max(1, min(len(stages), int(settings.get("active_stage", 1))))
        attempt("DPI", device.set_dpi_stages, stages, active)
        attempt("DPI", device.set_dpi, stages[active - 1])
    if "poll_rate" in features and settings.get("poll_rate"):
        attempt("fréquence", device.set_poll_rate, int(settings["poll_rate"]))
    if "scroll" in features:
        if settings.get("scroll_mode"):
            attempt("molette", device.set_scroll_mode, settings["scroll_mode"])
        if "scroll_accel" in settings:
            attempt("molette", device.set_scroll_acceleration, settings["scroll_accel"])
        if "smart_reel" in settings:
            attempt("molette", device.set_smart_reel, settings["smart_reel"])
    if "idle_time" in features and settings.get("idle_time"):
        attempt("veille", device.set_idle_time, int(settings["idle_time"]))
    return errors


def apply_profile(devices, profile: dict):
    errors = []
    for device in devices:
        if device.kind in profile:
            errors += [f"{device.name} - {e}" for e in apply_device(device, profile[device.kind])]
    return errors


# --- Démarrage avec Windows ------------------------------------------------

def _startup_file() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RazerError("Démarrage automatique disponible seulement sous Windows")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "RazerLite.cmd"


def autostart_enabled() -> bool:
    try:
        return _startup_file().exists()
    except RazerError:
        return False


def set_autostart(enabled: bool):
    target = _startup_file()
    if not enabled:
        target.unlink(missing_ok=True)
        return
    if getattr(sys, "frozen", False):
        command = f'start "" "{sys.executable}" --tray'
    else:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        exe = pythonw if pythonw.exists() else Path(sys.executable)
        root = Path(__file__).resolve().parent.parent
        command = f'cd /d "{root}"\r\nstart "" "{exe}" -m razerlite --tray'
    target.write_text(f"@echo off\r\nrem Lance RazerLite au demarrage (supprimer ce fichier pour l arreter)\r\n{command}\r\n",
                      encoding="mbcs" if os.name == "nt" else "utf-8")
