"""Retour micro fait par RazerLite : le son du micro du Kraken est renvoyé directement dans le casque.

Depuis le firmware 1.07.04, le retour micro du casque lui-même est retardé et de mauvaise qualité.
Ici on capte le micro et on le rejoue dans le casque en WASAPI avec la plus petite latence possible,
sans passer par « Écouter ce périphérique » de Windows (qui ajoute beaucoup de délai).

Deux flux séparés (micro → tampon → casque) : plus robuste qu'un flux duplex entre deux périphériques.
Le tampon est volontairement minuscule : s'il grossit, on jette le plus ancien pour ne jamais accumuler de retard.
"""

import array
import threading

MAX_BUFFER_MS = 30  # au-delà, on jette l'ancien son plutôt que d'accumuler du retard


def gain_for(level):
    """Curseur 0–100 → gain : 50 = volume naturel, 100 = deux fois plus fort."""
    return max(0, min(100, int(level))) / 50


def process(data, in_channels, out_channels, gain):
    """Applique le gain au son brut 16 bits du micro et l'adapte au nombre de voies du casque."""
    samples = array.array("h")
    samples.frombytes(bytes(data))
    if gain != 1:
        samples = array.array("h", (max(-32768, min(32767, int(s * gain))) for s in samples))
    if in_channels == out_channels:
        return samples.tobytes()
    if in_channels > 1:
        samples = samples[::in_channels]  # on garde la première voie
    out = array.array("h", bytes(len(samples) * out_channels * 2))
    for c in range(out_channels):
        out[c::out_channels] = samples
    return out.tobytes()


class Buffer:
    """Tampon entre le flux du micro et celui du casque, borné pour garder la latence basse."""

    def __init__(self, max_bytes, frame=4):
        self.max_bytes = max_bytes
        self.frame = frame
        self.data = bytearray()
        self.lock = threading.Lock()
        self.dropped = 0

    def write(self, chunk):
        with self.lock:
            self.data += chunk
            extra = len(self.data) - self.max_bytes
            if extra > 0:
                extra += (-extra) % self.frame  # rester aligné sur une trame complète
                del self.data[:extra]
                self.dropped += 1

    def read(self, size):
        with self.lock:
            chunk = bytes(self.data[:size])
            del self.data[:size]
        return chunk + bytes(size - len(chunk))  # silence si le micro n'a pas encore fourni assez


def _find(sd, wasapi, want_input):
    key = "max_input_channels" if want_input else "max_output_channels"
    for index, dev in enumerate(sd.query_devices()):
        if dev["hostapi"] == wasapi and dev[key] > 0 and "kraken" in dev["name"].lower():
            return index, dev
    return None, None


class MicMonitor:
    def __init__(self):
        self.streams = []
        self.gain = 1.0
        self.latency_ms = None
        self.error = None

    @property
    def running(self):
        return bool(self.streams)

    def set_level(self, level):
        self.gain = gain_for(level)

    def start(self, level):
        """Démarre le retour (ou le laisse tourner). Renvoie la latence en ms ; lève RuntimeError sinon."""
        self.set_level(level)
        if self.running:
            return self.latency_ms
        try:
            import sounddevice as sd
        except (ImportError, OSError) as exc:
            raise RuntimeError(f"module audio manquant ({exc})") from exc
        wasapi = next((i for i, h in enumerate(sd.query_hostapis()) if "WASAPI" in h["name"]), None)
        if wasapi is None:
            raise RuntimeError("WASAPI indisponible sur ce PC")
        mic_index, mic = _find(sd, wasapi, True)
        out_index, out = _find(sd, wasapi, False)
        if mic is None or out is None:
            raise RuntimeError("micro ou sortie du Kraken introuvable dans Windows")
        rate = int(out["default_samplerate"])
        in_ch = 1
        out_ch = min(2, out["max_output_channels"])
        buf = Buffer(int(rate * MAX_BUFFER_MS / 1000) * out_ch * 2, out_ch * 2)
        extra = sd.WasapiSettings(exclusive=False, auto_convert=True)

        def on_mic(data, frames, time, status):
            buf.write(process(data, in_ch, out_ch, self.gain))

        def on_out(data, frames, time, status):
            data[:] = buf.read(len(data))

        try:
            streams = [
                sd.RawInputStream(device=mic_index, samplerate=rate, channels=in_ch, dtype="int16",
                                  latency="low", callback=on_mic, extra_settings=extra),
                sd.RawOutputStream(device=out_index, samplerate=rate, channels=out_ch, dtype="int16",
                                   latency="low", callback=on_out, extra_settings=extra),
            ]
        except Exception as exc:
            raise RuntimeError(f"ouverture du son impossible : {exc}") from exc
        for s in streams:
            s.start()
        self.streams = streams
        self.latency_ms = round(sum(s.latency for s in streams) * 1000)
        return self.latency_ms

    def stop(self):
        streams, self.streams = self.streams, []
        for s in streams:
            try:
                s.stop()
                s.close()
            except Exception:
                pass
