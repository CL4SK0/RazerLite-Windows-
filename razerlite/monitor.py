"""Retour micro fait par RazerLite : le son du micro du Kraken est renvoyé directement dans le casque.

Depuis le firmware 1.07.04, le retour micro du casque lui-même est retardé et de mauvaise qualité.
Ici on capte le micro et on le rejoue dans le casque en WASAPI avec la plus petite latence possible,
sans passer par « Écouter ce périphérique » de Windows (qui ajoute beaucoup de délai).

Deux flux séparés (micro → tampon → casque) : plus robuste qu'un flux duplex entre deux périphériques.
Pour la latence : on demande les plus petits blocs que Windows accepte, on évite la conversion de format
(qui ajoute un rééchantillonneur) et le tampon ne garde jamais plus d'un bloc d'avance.
"""

import array
import threading

# Latences demandées à Windows, de la plus courte à la plus sûre (0 = le minimum du périphérique)
LATENCIES = (0.0, 0.005, "low")


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
    """Tampon entre le flux du micro et celui du casque.

    Il ne garde que de quoi remplir le prochain bloc du casque plus un bloc du micro : si les deux horloges
    dérivent et que le son s'accumule, on jette le plus ancien au lieu de laisser le retard grandir.
    """

    def __init__(self, frame=4):
        self.frame = frame
        self.data = bytearray()
        self.lock = threading.Lock()
        self.last_write = 0
        self.last_read = 0
        self.dropped = 0

    def write(self, chunk):
        with self.lock:
            self.data += chunk
            self.last_write = len(chunk)
            self._trim(self.last_write + max(self.last_read, self.last_write))

    def read(self, size):
        with self.lock:
            self.last_read = size
            chunk = bytes(self.data[:size])
            del self.data[:size]
            self._trim(self.last_write)
        return chunk + bytes(size - len(chunk))  # silence si le micro n'a pas encore fourni assez

    def _trim(self, keep):
        extra = len(self.data) - keep
        if extra > 0:
            extra += (-extra) % self.frame  # rester aligné sur une trame complète
            del self.data[:extra]
            self.dropped += 1


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
        in_ch = min(2, mic["max_input_channels"])
        out_ch = min(2, out["max_output_channels"])
        buf = Buffer(out_ch * 2)

        def on_mic(data, frames, time, status):
            buf.write(process(data, in_ch, out_ch, self.gain))

        def on_out(data, frames, time, status):
            data[:] = buf.read(len(data))

        streams, error = None, None
        # sans conversion d'abord (plus rapide), puis avec si le format natif est refusé
        for convert in (False, True):
            for latency in LATENCIES:
                opened = []
                try:
                    in_convert = convert or int(mic["default_samplerate"]) != rate
                    opened.append(sd.RawInputStream(
                        device=mic_index, samplerate=rate, channels=in_ch, dtype="int16", latency=latency,
                        callback=on_mic, extra_settings=sd.WasapiSettings(auto_convert=in_convert)))
                    opened.append(sd.RawOutputStream(
                        device=out_index, samplerate=rate, channels=out_ch, dtype="int16", latency=latency,
                        callback=on_out, extra_settings=sd.WasapiSettings(auto_convert=convert)))
                    streams = opened
                    break
                except Exception as exc:
                    error = exc
                    for st in opened:
                        st.close()
            if streams:
                break
        if not streams:
            raise RuntimeError(f"ouverture du son impossible : {error}")
        for s in streams:
            s.start()
        self.streams = streams
        # latence des deux flux + un bloc d'avance en moyenne dans le tampon
        block = streams[0].blocksize or round(streams[0].latency * rate / 2)
        self.latency_ms = round((sum(st.latency for st in streams) + block / rate) * 1000)
        return self.latency_ms

    def stop(self):
        streams, self.streams = self.streams, []
        for s in streams:
            try:
                s.stop()
                s.close()
            except Exception:
                pass


class AutoMonitor:
    """Essaie d'abord le moteur WASAPI direct (lowlat), puis PortAudio si le PC ou le pilote le refuse."""

    def __init__(self):
        self.engine = None
        self.error = None
        self.fallback_reason = None

    @property
    def running(self):
        return self.engine is not None and self.engine.running

    @property
    def latency_ms(self):
        return self.engine.latency_ms if self.engine else None

    @property
    def period_ms(self):
        return getattr(self.engine, "period_ms", None)

    def set_level(self, level):
        if self.engine:
            self.engine.set_level(level)

    def start(self, level):
        if self.running:
            self.engine.set_level(level)
            return self.engine.latency_ms
        self.fallback_reason = None
        try:
            from .lowlat import LowLatencyMonitor
            engine = LowLatencyMonitor()
            engine.start(level)
        except Exception as exc:
            self.fallback_reason = str(exc)
            engine = MicMonitor()
            engine.start(level)
        self.engine = engine
        return engine.latency_ms

    def stop(self):
        if self.engine:
            self.engine.stop()
