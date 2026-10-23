"""Moteur de retour micro basse latence : WASAPI direct avec IAudioClient3 (Windows 10 et plus).

PortAudio (sounddevice) ne descend pas sous les blocs de 10 ms de Windows, avec deux blocs d'avance de chaque côté.
Ici on parle directement à Windows : on demande au pilote du casque ses plus petits blocs (souvent 2 à 3 ms
quand il le permet), puis chaque paquet du micro est recopié tout de suite dans le casque, sans tampon
intermédiaire. Le micro reste en mode partagé : Discord et les jeux l'utilisent normalement en même temps.

Tout se passe dans un fil dédié (les objets COM y sont créés), en priorité « Pro Audio ».
"""

import array
import ctypes
import threading

AUDCLNT_STREAMFLAGS_EVENTCALLBACK = 0x00040000
AUDCLNT_BUFFERFLAGS_SILENT = 0x2
WAVE_FORMAT_PCM = 1
WAVE_FORMAT_IEEE_FLOAT = 3
WAVE_FORMAT_EXTENSIBLE = 0xFFFE
KSDATAFORMAT_SUBTYPE_IEEE_FLOAT = "{00000003-0000-0010-8000-00AA00389B71}"
KSDATAFORMAT_SUBTYPE_PCM = "{00000001-0000-0010-8000-00AA00389B71}"
CLSCTX_ALL = 23


def mix(samples, in_ch, out_ch, gain):
    """Son du micro (float, entrelacé) → son pour le casque : gain, première voie copiée sur gauche et droite.

    Les autres voies éventuelles du casque (son virtuel 7.1) restent silencieuses.
    """
    frames = len(samples) // in_ch
    voice = samples[::in_ch] if in_ch > 1 else samples
    if gain != 1:
        voice = array.array("f", (max(-1.0, min(1.0, s * gain)) for s in voice))
    out = array.array("f", bytes(frames * out_ch * 4))
    for c in range(min(2, out_ch)):
        out[c::out_ch] = voice
    return out


def _interfaces():
    from ctypes import HRESULT, POINTER, c_int, c_longlong, c_uint, c_ulonglong, c_void_p, wintypes

    from comtypes import COMMETHOD, GUID, IUnknown

    # structures « packées » sur 1 octet dans mmreg.h : sans ça, SubFormat est lu 2 octets trop loin
    class WAVEFORMATEX(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("wFormatTag", wintypes.WORD), ("nChannels", wintypes.WORD), ("nSamplesPerSec", wintypes.DWORD),
                    ("nAvgBytesPerSec", wintypes.DWORD), ("nBlockAlign", wintypes.WORD),
                    ("wBitsPerSample", wintypes.WORD), ("cbSize", wintypes.WORD)]

    class WAVEFORMATEXTENSIBLE(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("Format", WAVEFORMATEX), ("wValidBitsPerSample", wintypes.WORD),
                    ("dwChannelMask", wintypes.DWORD), ("SubFormat", GUID)]

    PFMT = POINTER(WAVEFORMATEX)

    class IAudioClient3(IUnknown):
        _iid_ = GUID("{7ED4EE07-8E67-4CD4-8C1A-2B7A5987AD42}")
        _methods_ = [
            # IAudioClient
            COMMETHOD([], HRESULT, "Initialize", (["in"], c_int), (["in"], wintypes.DWORD), (["in"], c_longlong),
                      (["in"], c_longlong), (["in"], PFMT), (["in"], c_void_p)),
            COMMETHOD([], HRESULT, "GetBufferSize", (["out"], POINTER(c_uint))),
            COMMETHOD([], HRESULT, "GetStreamLatency", (["out"], POINTER(c_longlong))),
            COMMETHOD([], HRESULT, "GetCurrentPadding", (["out"], POINTER(c_uint))),
            COMMETHOD([], HRESULT, "IsFormatSupported", (["in"], c_int), (["in"], PFMT), (["out"], POINTER(PFMT))),
            COMMETHOD([], HRESULT, "GetMixFormat", (["out"], POINTER(PFMT))),
            COMMETHOD([], HRESULT, "GetDevicePeriod", (["out"], POINTER(c_longlong)), (["out"], POINTER(c_longlong))),
            COMMETHOD([], HRESULT, "Start"),
            COMMETHOD([], HRESULT, "Stop"),
            COMMETHOD([], HRESULT, "Reset"),
            COMMETHOD([], HRESULT, "SetEventHandle", (["in"], wintypes.HANDLE)),
            COMMETHOD([], HRESULT, "GetService", (["in"], POINTER(GUID)), (["out"], POINTER(POINTER(IUnknown)))),
            # IAudioClient2
            COMMETHOD([], HRESULT, "IsOffloadCapable", (["in"], c_int), (["out"], POINTER(wintypes.BOOL))),
            COMMETHOD([], HRESULT, "SetClientProperties", (["in"], c_void_p)),
            COMMETHOD([], HRESULT, "GetBufferSizeLimits", (["in"], PFMT), (["in"], wintypes.BOOL),
                      (["out"], POINTER(c_longlong)), (["out"], POINTER(c_longlong))),
            # IAudioClient3
            COMMETHOD([], HRESULT, "GetSharedModeEnginePeriod", (["in"], PFMT), (["out"], POINTER(c_uint)),
                      (["out"], POINTER(c_uint)), (["out"], POINTER(c_uint)), (["out"], POINTER(c_uint))),
            COMMETHOD([], HRESULT, "GetCurrentSharedModeEnginePeriod", (["out"], POINTER(PFMT)),
                      (["out"], POINTER(c_uint))),
            COMMETHOD([], HRESULT, "InitializeSharedAudioStream", (["in"], wintypes.DWORD), (["in"], c_uint),
                      (["in"], PFMT), (["in"], c_void_p)),
        ]

    class IAudioCaptureClient(IUnknown):
        _iid_ = GUID("{C8ADBD64-E71E-48A0-A4DE-185C395CD317}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetBuffer", (["out"], POINTER(c_void_p)), (["out"], POINTER(c_uint)),
                      (["out"], POINTER(wintypes.DWORD)), (["out"], POINTER(c_ulonglong)),
                      (["out"], POINTER(c_ulonglong))),
            COMMETHOD([], HRESULT, "ReleaseBuffer", (["in"], c_uint)),
            COMMETHOD([], HRESULT, "GetNextPacketSize", (["out"], POINTER(c_uint))),
        ]

    class IAudioRenderClient(IUnknown):
        _iid_ = GUID("{F294ACFC-3146-4483-A7BF-ADDCA7C260E2}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetBuffer", (["in"], c_uint), (["out"], POINTER(c_void_p))),
            COMMETHOD([], HRESULT, "ReleaseBuffer", (["in"], c_uint), (["in"], wintypes.DWORD)),
        ]

    return WAVEFORMATEX, WAVEFORMATEXTENSIBLE, IAudioClient3, IAudioCaptureClient, IAudioRenderClient


def sample_kind(fmt, ext_cls):
    """« f » (float 32 bits), « h » (entier 16 bits), « i » (entier 32 bits) ou None si non géré."""
    f = fmt.contents
    tag = f.wFormatTag
    if tag == WAVE_FORMAT_EXTENSIBLE:
        sub = str(ctypes.cast(fmt, ctypes.POINTER(ext_cls)).contents.SubFormat).upper()
        tag = WAVE_FORMAT_IEEE_FLOAT if sub == KSDATAFORMAT_SUBTYPE_IEEE_FLOAT else (
            WAVE_FORMAT_PCM if sub == KSDATAFORMAT_SUBTYPE_PCM else None)
    if tag == WAVE_FORMAT_IEEE_FLOAT and f.wBitsPerSample == 32:
        return "f"
    if tag == WAVE_FORMAT_PCM and f.wBitsPerSample == 16:
        return "h"
    if tag == WAVE_FORMAT_PCM and f.wBitsPerSample == 32:
        return "i"
    return None


SCALE = {"f": 1.0, "h": 32768.0, "i": 2147483648.0}


def decode(raw, kind):
    """Octets bruts → array de floats entre -1 et 1."""
    data = array.array("i" if kind == "i" else kind)
    data.frombytes(raw)
    if kind == "f":
        return data
    scale = SCALE[kind]
    return array.array("f", (v / scale for v in data))


def encode(samples, kind):
    """Floats entre -1 et 1 → octets bruts au format du casque."""
    if kind == "f":
        return samples.tobytes()
    scale = SCALE[kind]
    top = scale - 1
    return array.array("i" if kind == "i" else kind,
                       (int(max(-scale, min(top, v * scale))) for v in samples)).tobytes()


class LowLatencyMonitor:
    """Même usage que monitor.MicMonitor : start(level) / set_level / stop / running / latency_ms."""

    def __init__(self):
        self.gain = 1.0
        self.latency_ms = None
        self.period_ms = None
        self.error = None
        self._thread = None
        self._stop = threading.Event()

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def set_level(self, level):
        from .monitor import gain_for
        self.gain = gain_for(level)

    def start(self, level):
        self.set_level(level)
        if self.running:
            return self.latency_ms
        self._stop.clear()
        ready = threading.Event()
        result = {}
        self._thread = threading.Thread(target=self._run, args=(ready, result), daemon=True, name="retour-micro")
        self._thread.start()
        if not ready.wait(5):
            self._stop.set()
            raise RuntimeError("le moteur basse latence ne répond pas")
        if "error" in result:
            self._thread = None
            raise RuntimeError(result["error"])
        return self.latency_ms

    def stop(self):
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(2)

    def _run(self, ready, result):
        clients, events, formats, kinds, task = [], [], [], [], None
        k32 = ole32 = None
        try:
            import comtypes

            from . import audio
            k32 = ctypes.windll.kernel32
            ole32 = ctypes.windll.ole32
            comtypes.CoInitialize()  # même mode que find_headset, qui l'appelle aussi
            WFX, WFXE, IAC3, ICapture, IRender = _interfaces()
            out_ep, mic_ep = audio.find_headset()
            if out_ep is None or mic_ep is None:
                raise RuntimeError("micro ou sortie du Kraken introuvable dans Windows")
            setup = []
            for ep in (mic_ep, out_ep):
                client = ep.device.Activate(IAC3._iid_, CLSCTX_ALL, None).QueryInterface(IAC3)
                fmt = client.GetMixFormat()
                formats.append(fmt)
                kind = sample_kind(fmt, WFXE)
                if kind is None:
                    f = fmt.contents
                    raise RuntimeError(f"format audio non géré ({f.wBitsPerSample} bits, type {f.wFormatTag})")
                kinds.append(kind)
                default, fundamental, minimum, maximum = client.GetSharedModeEnginePeriod(fmt)
                setup.append((client, fmt, minimum, default))
                clients.append(client)
            (mic, mic_fmt, mic_min, mic_def), (out, out_fmt, out_min, out_def) = setup
            rate = mic_fmt.contents.nSamplesPerSec
            if rate != out_fmt.contents.nSamplesPerSec:
                raise RuntimeError(f"fréquences différentes (micro {rate} Hz, casque "
                                   f"{out_fmt.contents.nSamplesPerSec} Hz) : règle-les pareil dans Windows")
            for client, fmt, minimum, _ in setup:
                event = k32.CreateEventW(None, False, False, None)
                events.append(event)
                try:
                    client.InitializeSharedAudioStream(AUDCLNT_STREAMFLAGS_EVENTCALLBACK, minimum, fmt, None)
                except Exception:
                    # un autre programme impose déjà une période : on prend la période standard
                    client.Initialize(0, AUDCLNT_STREAMFLAGS_EVENTCALLBACK, 0, 0, fmt, None)
                client.SetEventHandle(event)
            capture = mic.GetService(ICapture._iid_).QueryInterface(ICapture)
            render = out.GetService(IRender._iid_).QueryInterface(IRender)
            in_ch, out_ch = mic_fmt.contents.nChannels, out_fmt.contents.nChannels
            in_align, out_align = mic_fmt.contents.nBlockAlign, out_fmt.contents.nBlockAlign
            out_size = out.GetBufferSize()
            mic_period = mic.GetCurrentSharedModeEnginePeriod()[1]
            out_period = out.GetCurrentSharedModeEnginePeriod()[1]
            # on garde au plus deux périodes du casque d'avance : au-delà, on jette pour ne pas prendre de retard
            target = max(2 * out_period, mic_period + out_period)

            # amorce : une période de silence pour que le casque ne manque pas de son au démarrage
            ptr = render.GetBuffer(out_period)
            ctypes.memset(ptr, 0, out_period * out_align)
            render.ReleaseBuffer(out_period, 0)

            try:
                index = ctypes.c_ulong(0)
                task = ctypes.windll.avrt.AvSetMmThreadCharacteristicsW("Pro Audio", ctypes.byref(index))
            except (AttributeError, OSError):
                task = None
            mic.Start()
            out.Start()
            self.period_ms = round(min(mic_period, out_period) * 1000 / rate, 1)
            self.latency_ms = round((mic_period + target + out_period) * 1000 / rate)
            ready.set()

            while not self._stop.is_set():
                if k32.WaitForSingleObject(events[0], 200) != 0:
                    continue
                while True:
                    if capture.GetNextPacketSize() == 0:
                        break
                    data, frames, flags, _, _ = capture.GetBuffer()
                    if flags & AUDCLNT_BUFFERFLAGS_SILENT or not data:
                        samples = array.array("f", bytes(frames * in_ch * 4))
                    else:
                        samples = decode(ctypes.string_at(data, frames * in_align), kinds[0])
                    capture.ReleaseBuffer(frames)
                    padding = out.GetCurrentPadding()
                    room = min(out_size - padding, max(0, target - padding))
                    n = min(frames, room)
                    if n <= 0:
                        continue  # le casque a déjà assez d'avance : ce paquet est sauté
                    block = mix(samples[len(samples) - n * in_ch:], in_ch, out_ch, self.gain)
                    ptr = render.GetBuffer(n)
                    ctypes.memmove(ptr, encode(block, kinds[1]), n * out_align)
                    render.ReleaseBuffer(n, 0)
        except BaseException as exc:
            result["error"] = str(exc) or exc.__class__.__name__
            ready.set()
        finally:
            for client in clients:
                try:
                    client.Stop()
                except Exception:
                    pass
            if task:
                ctypes.windll.avrt.AvRevertMmThreadCharacteristics(task)
            for event in events:
                k32.CloseHandle(event)
            for fmt in formats:
                ole32.CoTaskMemFree(fmt)
            del clients[:]
