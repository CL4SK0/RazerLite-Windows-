"""Lecture de l'état des touches et boutons (Windows), pour les afficher dans l'aperçu.

Rien n'est enregistré : on regarde seulement quelles touches sont enfoncées à l'instant,
et uniquement quand la fenêtre de RazerLite est visible.
"""

import sys

MOUSE_BUTTONS = {"left": 0x01, "right": 0x02, "middle": 0x04, "back": 0x05, "forward": 0x06}


class KeyState:
    def __init__(self):
        self.available = False
        self._vk_cache = {}
        if sys.platform != "win32":
            return
        try:
            import ctypes
            user32 = ctypes.WinDLL("user32")
            self._get = user32.GetAsyncKeyState
            self._get.argtypes, self._get.restype = [ctypes.c_int], ctypes.c_short
            self._map = user32.MapVirtualKeyW
            self._map.argtypes, self._map.restype = [ctypes.c_uint, ctypes.c_uint], ctypes.c_uint
            self.available = True
        except (OSError, AttributeError):
            pass

    def _vk(self, code):
        if code is None:
            return 0
        kind, value = code
        if kind == "vk":
            return value
        if code not in self._vk_cache:
            self._vk_cache[code] = self._map(value, 1)  # MAPVK_VSC_TO_VK : suit la disposition (AZERTY…)
        return self._vk_cache[code]

    def down(self, vk):
        return bool(vk) and bool(self._get(vk) & 0x8000)

    def pressed_keys(self, codes):
        """Index des touches enfoncées parmi la liste de codes du rendu clavier."""
        if not self.available:
            return set()
        return {i for i, code in enumerate(codes) if self.down(self._vk(code))}

    def pressed_buttons(self):
        if not self.available:
            return set()
        return {name for name, vk in MOUSE_BUTTONS.items() if self.down(vk)}


_instance = None


def get():
    global _instance
    if _instance is None:
        _instance = KeyState()
    return _instance
