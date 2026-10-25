"""speech/loudness.py: spoken audio is made louder without clipping."""
import array
import io
import math
import wave

from speech.loudness import loud_wav


def rms(samples):
    return math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768


def decode(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        out = array.array("h")
        out.frombytes(w.readframes(w.getnframes()))
        return out, w.getframerate()


def speechlike():
    # quiet body with a few loud peaks, like speech
    return array.array("h", [int((3000 + (28000 if i % 4000 < 40 else 0)) * math.sin(i / 7)) for i in range(24000)])


def test_average_level_goes_up_and_nothing_clips():
    pcm = speechlike()
    out, rate = decode(loud_wav(pcm.tobytes(), 24000))
    assert rate == 24000 and len(out) == len(pcm)
    assert rms(out) > rms(pcm) * 1.5
    assert max(abs(s) for s in out) <= 32767


def test_silence_stays_silent_and_empty_input_is_still_a_wav():
    out, _ = decode(loud_wav(bytes(2000), 24000))
    assert set(out) == {0}
    assert decode(loud_wav(b"", 24000))[0] == array.array("h")
