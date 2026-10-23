"""Réglages audio du casque sous Windows : volumes, retour micro, égaliseur et suppression de bruit.

- Volumes et sourdine : API audio de Windows (Core Audio), comme le mélangeur de volume.
- Retour micro (sidetone) : voir KrakenV3.set_sidetone (commande HID du casque).
- Égaliseur et suppression de bruit : Equalizer APO (gratuit, libre), que RazerLite configure.
  La suppression de bruit utilise RNNoise (noise-suppression-for-voice), qui retire clavier, souffle, ventilateur.
"""

import io
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

from . import profiles

HEADSET_MATCH = "kraken"
APO_DOWNLOAD = "https://sourceforge.net/projects/equalizerapo/files/latest/download"
APO_PAGE = "https://sourceforge.net/projects/equalizerapo/"
RNNOISE_ZIP = "https://github.com/werman/noise-suppression-for-voice/releases/latest/download/win-rnnoise.zip"
RNNOISE_PAGE = "https://github.com/werman/noise-suppression-for-voice/releases/latest"

EQ_BANDS = (31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
EQ_LABELS = ("31", "62", "125", "250", "500", "1k", "2k", "4k", "8k", "16k")
# Préréglages dans l'esprit de ceux de Synapse (gain en dB par bande)
HEADSET_PRESETS = {
    "Neutre": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    "Jeu": (2, 2, 1, 0, -1, 0, 2, 3, 3, 2),
    "Film": (4, 3, 2, 0, 0, 0, 1, 2, 2, 1),
    "Musique": (3, 3, 2, 1, 0, 0, 1, 2, 2, 2),
    "Basses+": (6, 5, 4, 2, 0, 0, 0, 0, 0, 0),
    "Voix": (-3, -2, -1, 0, 1, 2, 3, 3, 1, 0),
}
MIC_PRESETS = {
    "Neutre": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    "Voix claire": (-12, -8, -3, 0, 0, 1, 3, 3, 1, -2),
    "Voix chaude": (-10, -4, 2, 2, 1, 0, 0, 1, 0, -3),
    "Radio": (-12, -12, -6, 0, 2, 3, 4, 2, -4, -10),
}


# --- Core Audio (Windows) ----------------------------------------------------------

def available():
    return sys.platform == "win32" and _com() is not None


_com_cache = []


def _com():
    """Définitions COM chargées à la demande (comtypes n'existe que sous Windows)."""
    if _com_cache:
        return _com_cache[0]
    try:
        import ctypes
        from ctypes import HRESULT, POINTER, c_float, c_uint, c_void_p, wintypes

        import comtypes  # noqa: F401 (vérifie que comtypes est installé)
        from comtypes import COMMETHOD, GUID, IUnknown
    except (ImportError, OSError):
        _com_cache.append(None)
        return None

    class PROPERTYKEY(ctypes.Structure):
        _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]

    class PROPVARIANT(ctypes.Structure):
        _fields_ = [("vt", wintypes.USHORT), ("r1", wintypes.WORD), ("r2", wintypes.WORD), ("r3", wintypes.WORD),
                    ("pwszVal", ctypes.c_wchar_p), ("pad", ctypes.c_void_p)]

    class IPropertyStore(IUnknown):
        _iid_ = GUID("{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetCount", (["out"], POINTER(wintypes.DWORD), "count")),
            COMMETHOD([], HRESULT, "GetAt", (["in"], wintypes.DWORD), (["out"], POINTER(PROPERTYKEY))),
            COMMETHOD([], HRESULT, "GetValue", (["in"], POINTER(PROPERTYKEY)), (["out"], POINTER(PROPVARIANT))),
        ]

    class IAudioEndpointVolume(IUnknown):
        _iid_ = GUID("{5CDF2C82-841E-4546-9722-0CF74078229A}")
        _methods_ = [
            COMMETHOD([], HRESULT, "RegisterControlChangeNotify", (["in"], c_void_p)),
            COMMETHOD([], HRESULT, "UnregisterControlChangeNotify", (["in"], c_void_p)),
            COMMETHOD([], HRESULT, "GetChannelCount", (["out"], POINTER(c_uint))),
            COMMETHOD([], HRESULT, "SetMasterVolumeLevel", (["in"], c_float), (["in"], c_void_p)),
            COMMETHOD([], HRESULT, "SetMasterVolumeLevelScalar", (["in"], c_float), (["in"], c_void_p)),
            COMMETHOD([], HRESULT, "GetMasterVolumeLevel", (["out"], POINTER(c_float))),
            COMMETHOD([], HRESULT, "GetMasterVolumeLevelScalar", (["out"], POINTER(c_float))),
            COMMETHOD([], HRESULT, "SetChannelVolumeLevel", (["in"], c_uint), (["in"], c_float), (["in"], c_void_p)),
            COMMETHOD([], HRESULT, "SetChannelVolumeLevelScalar", (["in"], c_uint), (["in"], c_float), (["in"], c_void_p)),
            COMMETHOD([], HRESULT, "GetChannelVolumeLevel", (["in"], c_uint), (["out"], POINTER(c_float))),
            COMMETHOD([], HRESULT, "GetChannelVolumeLevelScalar", (["in"], c_uint), (["out"], POINTER(c_float))),
            COMMETHOD([], HRESULT, "SetMute", (["in"], wintypes.BOOL), (["in"], c_void_p)),
            COMMETHOD([], HRESULT, "GetMute", (["out"], POINTER(wintypes.BOOL))),
        ]

    class IMMDevice(IUnknown):
        _iid_ = GUID("{D666063F-1587-4E43-81F1-B948E807363F}")
        _methods_ = [
            COMMETHOD([], HRESULT, "Activate", (["in"], POINTER(GUID)), (["in"], wintypes.DWORD),
                      (["in"], c_void_p), (["out"], POINTER(POINTER(IUnknown)))),
            COMMETHOD([], HRESULT, "OpenPropertyStore", (["in"], wintypes.DWORD),
                      (["out"], POINTER(POINTER(IPropertyStore)))),
            COMMETHOD([], HRESULT, "GetId", (["out"], POINTER(ctypes.c_wchar_p))),
            COMMETHOD([], HRESULT, "GetState", (["out"], POINTER(wintypes.DWORD))),
        ]

    class IMMDeviceCollection(IUnknown):
        _iid_ = GUID("{0BD7A1BE-7A1A-44DB-8397-CC5392387B5E}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetCount", (["out"], POINTER(c_uint))),
            COMMETHOD([], HRESULT, "Item", (["in"], c_uint), (["out"], POINTER(POINTER(IMMDevice)))),
        ]

    class IMMDeviceEnumerator(IUnknown):
        _iid_ = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
        _methods_ = [
            COMMETHOD([], HRESULT, "EnumAudioEndpoints", (["in"], c_uint), (["in"], wintypes.DWORD),
                      (["out"], POINTER(POINTER(IMMDeviceCollection)))),
        ]

    ns = dict(locals())
    ns["CLSID_MMDeviceEnumerator"] = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
    ns["PKEY_FriendlyName"] = PROPERTYKEY(GUID("{A45C254E-DF1C-4EFD-8020-67D146A850E0}"), 14)
    _com_cache.append(ns)
    return ns


class Endpoint:
    """Une sortie (casque) ou une entrée (micro) Windows."""

    CLSCTX_ALL = 23

    def __init__(self, device, name, flow):
        self.device, self.name, self.flow = device, name, flow  # flow : 0 sortie, 1 entrée
        com = _com()
        self.id = device.GetId()
        unk = device.Activate(com["IAudioEndpointVolume"]._iid_, self.CLSCTX_ALL, None)
        self.volume_ctl = unk.QueryInterface(com["IAudioEndpointVolume"])

    @property
    def guid(self):
        """Identifiant reconnu par Equalizer APO (dernière partie de l'id Windows)."""
        return self.id.rsplit(".", 1)[-1]

    def channels(self):
        return self.volume_ctl.GetChannelCount()

    def volume(self):
        return round(self.volume_ctl.GetMasterVolumeLevelScalar() * 100)

    def set_volume(self, percent):
        self.volume_ctl.SetMasterVolumeLevelScalar(max(0.0, min(1.0, percent / 100)), None)

    def muted(self):
        return bool(self.volume_ctl.GetMute())

    def set_muted(self, value):
        self.volume_ctl.SetMute(bool(value), None)


def find_headset():
    """(sortie, micro) du casque Kraken, ou (None, None)."""
    if not available():
        return None, None
    import comtypes
    com = _com()
    comtypes.CoInitialize()
    enum = comtypes.CoCreateInstance(com["CLSID_MMDeviceEnumerator"], com["IMMDeviceEnumerator"],
                                     comtypes.CLSCTX_ALL)
    found = [None, None]
    for flow in (0, 1):
        devices = enum.EnumAudioEndpoints(flow, 1)  # 1 = appareils actifs
        for i in range(devices.GetCount()):
            dev = devices.Item(i)
            try:
                name = dev.OpenPropertyStore(0).GetValue(com["PKEY_FriendlyName"]).pwszVal or ""
            except Exception:
                continue
            if HEADSET_MATCH in name.lower():
                found[flow] = Endpoint(dev, name, flow)
                break
    return tuple(found)


# --- Equalizer APO -------------------------------------------------------------------

def apo_config_dir():
    """Dossier de configuration d'Equalizer APO, ou None s'il n'est pas installé."""
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EqualizerAPO") as key:
                path = Path(winreg.QueryValueEx(key, "ConfigPath")[0])
                if path.is_dir():
                    return path
        except OSError:
            pass
    default = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "EqualizerAPO" / "config"
    return default if default.is_dir() else None


def rnnoise_dir():
    return profiles.config_dir() / "rnnoise"


def rnnoise_dll(channels):
    """Chemin du filtre RNNoise (VST 2) pour ce nombre de canaux, s'il est déjà téléchargé."""
    kind = "mono" if channels == 1 else "stereo"
    for path in sorted(rnnoise_dir().rglob("*.dll")):
        low = str(path).lower()
        if "vst3" not in low and "rnnoise" in path.name.lower() and kind in path.name.lower():
            return path
    return None


def download_rnnoise(progress=None):
    """Télécharge noise-suppression-for-voice (version Windows) dans %APPDATA%\\RazerLite\\rnnoise."""
    req = urllib.request.Request(RNNOISE_ZIP, headers={"User-Agent": "RazerLite"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    target = rnnoise_dir()
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for member in z.infolist():
            name = member.filename.lower()
            if member.is_dir() or not name.endswith(".dll") or "vst3" in name or ".." in member.filename:
                continue
            (target / Path(member.filename).name).write_bytes(z.read(member))


def graphic_eq(gains):
    return "GraphicEQ: " + "; ".join(f"{f} {g:g}" for f, g in zip(EQ_BANDS, gains))


def build_config(headset_guid=None, mic_guid=None, headset_eq=None, mic_eq=None, noise_dll=None,
                 mic_highpass=False):
    """Texte du fichier razerlite.txt lu par Equalizer APO."""
    lines = ["# Fichier géré par RazerLite : il est réécrit à chaque changement dans l'appli.", ""]
    if headset_guid and headset_eq and any(headset_eq):
        lines += [f"Device: {headset_guid}", f"Preamp: {-max(0, max(headset_eq)):g} dB", graphic_eq(headset_eq), ""]
    if mic_guid and (noise_dll or mic_highpass or (mic_eq and any(mic_eq))):
        lines.append(f"Device: {mic_guid}")
        if mic_highpass:
            lines.append("Filter: ON HP Fc 90 Hz")
        if noise_dll:
            lines.append(f'VSTPlugin: Library "{noise_dll}"')
        if mic_eq and any(mic_eq):
            lines += [f"Preamp: {-max(0, max(mic_eq)):g} dB", graphic_eq(mic_eq)]
        lines.append("")
    lines.append("Device: all")
    return "\n".join(lines) + "\n"


def write_apo_config(text):
    """Écrit razerlite.txt et l'ajoute à config.txt. Lève PermissionError si le dossier est protégé."""
    folder = apo_config_dir()
    if folder is None:
        raise FileNotFoundError("Equalizer APO n'est pas installé.")
    (folder / "razerlite.txt").write_text(text, encoding="utf-8")
    main = folder / "config.txt"
    current = main.read_text(encoding="utf-8", errors="replace") if main.exists() else ""
    if "include: razerlite.txt" not in current.lower():
        main.write_text(current.rstrip("\n") + ("\n" if current else "") + "Include: razerlite.txt\n", encoding="utf-8")
