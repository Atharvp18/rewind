"""Make spoken audio louder than Cartesia's own level (a phone speaker is quiet at full volume).

Cartesia speech peaks near full scale but averages about -17 dBFS, which is quiet on an iPhone
loudspeaker. This raises the average to about -11 dBFS with gain and a soft limiter (tanh), so
the loud parts are squeezed instead of clipped. Pure Python on 16-bit mono WAV; any input it cannot
parse comes back unchanged, so a bad file never silences a line.
"""
from __future__ import annotations

import array
import io
import math
import sys
import wave

TARGET_RMS = 0.28          # about -11 dBFS
MAX_GAIN = 6.0             # never turn near-silence into noise
DRIVE = 1.6                # how hard the soft limiter squeezes the peaks


def loud_wav(pcm: bytes, sample_rate: int) -> bytes:
    """16-bit mono PCM in, a louder WAV file out. On any problem the PCM is wrapped unchanged."""
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    if sys.byteorder == "big":
        samples.byteswap()
    try:
        rms = math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768 if samples else 0.0
        if rms > 0:
            gain = min(TARGET_RMS / rms, MAX_GAIN)
            k = DRIVE * gain
            norm = math.tanh(k)      # full scale stays full scale; everything below it is lifted
            samples = array.array("h", (max(-32767, min(32767, int(32767 * math.tanh(k * s / 32768) / norm)))
                                          for s in samples))
    except Exception:  # noqa: BLE001 - never lose a line over loudness
        pass
    if sys.byteorder == "big":
        samples.byteswap()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(samples.tobytes())
    return buf.getvalue()
