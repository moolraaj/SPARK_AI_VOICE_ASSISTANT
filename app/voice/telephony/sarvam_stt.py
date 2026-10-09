"""
Hardware Voice STT + TTS helper.

STT:  ESP32 PCM  -> VAD segmenter -> Deepgram Nova -> text
TTS:  text       -> Sarvam Bulbul -> 16-bit mono PCM -> ESP32 HFP

STT debug lines (printed per stage on the terminal):
    🎚️ [VAD]        mic level every 3 s (is mic audio arriving?)
    🎙️ [SPEECH]     speech start detected
    🧩 [UTTERANCE]  utterance captured
    🗑️ [VAD DROP]   utterance too short
    🔇 [STT GATE]   energy too low
    🎤 [STT]        sent to Deepgram Nova
    🎯 [STT RESULT] Deepgram transcript

Set STT_DEBUG=0 to disable periodic VAD level lines.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import re
import sys
import time
import wave
from array import array
from collections import deque
from typing import Awaitable, Callable, Optional

import httpx

logger = logging.getLogger(__name__)


# ============================================================
# CONFIG
# ============================================================

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, "1" if default else "0") == "1"


# --- STT / VAD tuning ---------------------------------------------------

STT_LANGUAGE       = os.getenv("STT_LANGUAGE", "hi-IN")
STT_DEBUG          = _env_bool("STT_DEBUG", True)

# Thresholds tuned for short words like "hii". Low-latency end-of-speech.
STT_SILENCE_MS     = _env_int("STT_SILENCE_MS", 500)
STT_MIN_SPEECH_MS  = _env_int("STT_MIN_SPEECH_MS", 120)
STT_MIN_ENERGY     = _env_int("STT_MIN_ENERGY", 100)
STT_VAD_RMS        = _env_int("STT_VAD_RMS", 220)

STT_NOISE_MULT     = 2.8
STT_KEEP_RATIO     = 0.70
STT_MAX_UTTER_MS   = 25_000   
STT_PREROLL_MS     = 180
STT_TIMEOUT        = _env_int("STT_TIMEOUT", 20)
STT_PHRASE_LIMIT   = _env_int("STT_PHRASE_TIME_LIMIT", 20)

# Half-duplex gate: while TTS plays, ignore mic unless energy is clearly a
# barge-in. Short hangover lets user reply sooner after the AI finishes.
TTS_GATE_HANGOVER_SEC = _env_float("TTS_GATE_HANGOVER_SEC", 0.22)
TTS_BARGE_IN_RMS      = _env_int("TTS_BARGE_IN_RMS", 4500)

# --- Deepgram STT -------------------------------------------------------

DEEPGRAM_API_URL      = "https://api.deepgram.com/v1/listen"
DEEPGRAM_API_KEY      = os.getenv("DEEPGRAM_API_KEY", "").strip()
DEEPGRAM_MODEL        = os.getenv("DEEPGRAM_MODEL", "nova-3")
DEEPGRAM_LANGUAGE     = os.getenv("DEEPGRAM_LANGUAGE", "multi")
DEEPGRAM_SMART_FORMAT = _env_bool("DEEPGRAM_SMART_FORMAT", True)
DEEPGRAM_TIMEOUT_SEC  = _env_float("DEEPGRAM_TIMEOUT_SEC", 8.0)

# --- Sarvam TTS ---------------------------------------------------------

SARVAM_TTS_URL  = "https://api.sarvam.ai/text-to-speech"
TTS_MODEL       = os.getenv("TTS_MODEL", "bulbul:v3")
TTS_SPEAKER     = os.getenv("TTS_SPEAKER", "shubh")
TTS_LANGUAGE    = os.getenv("TTS_LANGUAGE", "hi-IN")
TTS_DEBUG_DUMP  = _env_bool("TTS_DEBUG_DUMP", False)
TTS_MAX_CHARS   = 2500 if TTS_MODEL.startswith("bulbul:v3") else 1500


# ============================================================
# SHARED HTTP CLIENT
# ============================================================

_http: Optional[httpx.AsyncClient] = None


def _client() -> httpx.AsyncClient:
    """Return the shared AsyncClient, creating it if needed."""
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(
                max_keepalive_connections=4, keepalive_expiry=60
            ),
        )
    return _http


async def close_http_client() -> None:
    """Close the shared AsyncClient (call on shutdown)."""
    global _http
    if _http is not None and not _http.is_closed:
        await _http.aclose()
    _http = None


# ============================================================
# PCM HELPERS
# ============================================================

def _to_samples(pcm: bytes) -> array:
    """Little-endian 16-bit PCM bytes -> array('h')."""
    usable = len(pcm) - (len(pcm) % 2)
    samples = array("h")
    samples.frombytes(pcm[:usable])
    if sys.byteorder == "big":
        samples.byteswap()
    return samples


def _from_samples(samples: array) -> bytes:
    """array('h') -> little-endian 16-bit PCM bytes."""
    if sys.byteorder == "big":
        samples.byteswap()
    return samples.tobytes()


def _rms(data: bytes) -> int:
    """Root-mean-square amplitude of 16-bit PCM."""
    samples = _to_samples(data)
    if not samples:
        return 0
    total = sum(s * s for s in samples)
    return int((total / len(samples)) ** 0.5)


def _upsample_2x(pcm: bytes) -> bytes:
    """8 kHz -> 16 kHz via linear interpolation."""
    src = _to_samples(pcm)
    out = array("h")
    n = len(src)
    for i in range(n):
        a = src[i]
        b = src[i + 1] if i + 1 < n else a
        out.append(a)
        out.append((a + b) // 2)
    return _from_samples(out)


def _downsample_2x(pcm: bytes) -> bytes:
    """16 kHz -> 8 kHz via pair averaging."""
    usable = len(pcm) - (len(pcm) % 4)
    src = _to_samples(pcm[:usable])
    out = array("h")
    for i in range(0, len(src) - 1, 2):
        out.append((src[i] + src[i + 1]) // 2)
    return _from_samples(out)


def _mono_from_pcm16(pcm: bytes, channels: int) -> bytes:
    """Downmix interleaved 16-bit PCM to mono."""
    if channels <= 1:
        return pcm
    samples = _to_samples(pcm)
    out = array("h")
    frame_count = len(samples) // channels
    for frame in range(frame_count):
        start = frame * channels
        total = sum(samples[start + ch] for ch in range(channels))
        value = max(-32768, min(32767, int(total / channels)))
        out.append(value)
    return _from_samples(out)


def _linear_resample(pcm: bytes, source_rate: int, target_rate: int) -> bytes:
    """Linear-interpolation resample of 16-bit PCM."""
    if source_rate <= 0 or target_rate <= 0 or source_rate == target_rate:
        return pcm

    samples = _to_samples(pcm)
    if not samples:
        return b""

    output_length = int(len(samples) * target_rate / source_rate)
    ratio = source_rate / target_rate
    out = array("h")

    for i in range(output_length):
        position = i * ratio
        left = int(position)
        fraction = position - left
        if left >= len(samples) - 1:
            value = samples[-1]
        else:
            a = samples[left]
            b = samples[left + 1]
            value = int(a + (b - a) * fraction)
        out.append(max(-32768, min(32767, value)))

    return _from_samples(out)


def _wav_to_pcm(wav_bytes: bytes, target_rate: int) -> bytes:
    """Decode a WAV byte-blob into mono 16-bit PCM at target_rate."""
    with io.BytesIO(wav_bytes) as buf:
        with wave.open(buf, "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            source_rate = wav.getframerate()
            raw = wav.readframes(wav.getnframes())

    logger.info(
        "🔍 [TTS WAV] rate=%s channels=%s width=%s bytes=%s",
        source_rate, channels, sample_width, len(raw),
    )

    if sample_width == 2:
        pcm = raw
    elif sample_width == 1:
        out = array("h")
        for value in raw:
            out.append((value - 128) << 8)
        pcm = _from_samples(out)
    elif sample_width == 3:
        out = array("h")
        for i in range(0, len(raw) - 2, 3):
            value = raw[i] | (raw[i + 1] << 8) | (raw[i + 2] << 16)
            if value & 0x800000:
                value -= 1 << 24
            value >>= 8
            out.append(max(-32768, min(32767, value)))
        pcm = _from_samples(out)
    elif sample_width == 4:
        src = array("i")
        src.frombytes(raw)
        if sys.byteorder == "big":
            src.byteswap()
        out = array("h")
        for value in src:
            out.append(max(-32768, min(32767, value >> 16)))
        pcm = _from_samples(out)
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")

    if channels != 1:
        pcm = _mono_from_pcm16(pcm, channels)

    if source_rate != target_rate:
        if source_rate == 16000 and target_rate == 8000:
            pcm = _downsample_2x(pcm)
        elif source_rate == 8000 and target_rate == 16000:
            pcm = _upsample_2x(pcm)
        else:
            pcm = _linear_resample(pcm, source_rate, target_rate)

    return pcm[: len(pcm) - (len(pcm) % 2)]


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap raw mono 16-bit PCM in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


# ============================================================
# ADAPTIVE VAD / UTTERANCE SEGMENTER
# ============================================================

class UtteranceSegmenter:
    """
    Streaming VAD that turns a continuous PCM feed into discrete utterances.

    Feed short PCM chunks; when a complete utterance is detected, `feed`
    returns `(pcm_bytes, speech_rms)`. Otherwise it returns `None`.
    """

    def __init__(self, sample_rate: int = 8000) -> None:
        self.sample_rate = sample_rate
        self.noise_floor = 150.0
        self.last_rms = 0
        self.last_threshold = 0.0
        self.reset()

    # -- public API ---------------------------------------------------

    def reset(self) -> None:
        self.speaking = False
        self.buf = bytearray()
        self.preroll: deque[tuple[bytes, float]] = deque()
        self.preroll_ms = 0.0
        self.speech_ms = 0.0
        self.silence_ms = 0.0
        self.total_ms = 0.0
        self.last_loud_len = 0

    def feed(self, chunk: bytes) -> Optional[tuple[bytes, int]]:
        if not chunk:
            return None

        duration_ms = len(chunk) / 2 / self.sample_rate * 1000
        rms = _rms(chunk)
        threshold = self._threshold()

        self.last_rms = rms
        self.last_threshold = threshold

        if not self.speaking:
            return self._feed_waiting(chunk, duration_ms, rms, threshold)
        return self._feed_speaking(chunk, duration_ms, rms, threshold)

    # -- internals ----------------------------------------------------

    def _threshold(self) -> float:
        return max(float(STT_VAD_RMS), self.noise_floor * STT_NOISE_MULT)

    def _feed_waiting(
        self, chunk: bytes, duration_ms: float, rms: int, threshold: float
    ) -> None:
        if rms >= threshold:
            # Speech begins — prepend preroll so we don't clip the onset.
            self.speaking = True
            self.buf = bytearray(b"".join(data for data, _ in self.preroll))
            self.buf += chunk
            self.last_loud_len = len(self.buf)
            self.speech_ms = duration_ms
            self.silence_ms = 0.0
            self.total_ms = self.preroll_ms + duration_ms
            self.preroll.clear()
            self.preroll_ms = 0.0
            print(
                f"🎙️ [SPEECH] start | rms={rms} thr={threshold:.0f}",
                flush=True,
            )
            return None

        # Still silence — adapt noise floor and keep a rolling preroll.
        self.noise_floor = min(400.0, 0.95 * self.noise_floor + 0.05 * rms)
        self.preroll.append((chunk, duration_ms))
        self.preroll_ms += duration_ms
        while self.preroll_ms > STT_PREROLL_MS and self.preroll:
            _, old = self.preroll.popleft()
            self.preroll_ms -= old
        return None

    
    def _feed_speaking(
        self,
        chunk: bytes,
        duration_ms: float,
        rms: int,
        threshold: float,
    ) -> Optional[tuple[bytes, int]]:
        loud = rms >= threshold * STT_KEEP_RATIO

        self.buf += chunk
        self.total_ms += duration_ms

        if loud:
            self.silence_ms = 0.0
            self.speech_ms += duration_ms
            self.last_loud_len = len(self.buf)
        else:
            self.silence_ms += duration_ms

        if (
            self.silence_ms < STT_SILENCE_MS
            and self.total_ms < STT_MAX_UTTER_MS
        ):
            return None

        pcm = bytes(self.buf)
        speech_rms = _rms(pcm[:self.last_loud_len])
        speech_ms = self.speech_ms

        enough = speech_ms >= STT_MIN_SPEECH_MS
        end_reason = (
            "silence"
            if self.silence_ms >= STT_SILENCE_MS
            else "max_duration"
        )

        print(
            f"🧩 [VAD END] reason={end_reason} "
            f"total={self.total_ms:.0f}ms "
            f"speech={speech_ms:.0f}ms "
            f"silence={self.silence_ms:.0f}ms "
            f"bytes={len(pcm)} "
            f"rms={speech_rms} "
            f"accepted={enough}",
            flush=True,
        )

        self.reset()

        if enough:
            return pcm, speech_rms

        print(
            f"🗑️ [VAD DROP] speech={speech_ms:.0f}ms "
            f"< minimum={STT_MIN_SPEECH_MS}ms",
            flush=True,
        )
        return None



# ============================================================
# DEEPGRAM NOVA STT
# ============================================================

async def _deepgram_transcribe(wav_bytes: bytes, sample_rate: int) -> str:
    """Send one complete WAV utterance to Deepgram Nova and return text."""
    if not DEEPGRAM_API_KEY:
        print("❌ [DEEPGRAM STT] DEEPGRAM_API_KEY missing", flush=True)
        return ""

    params = {
        "model": DEEPGRAM_MODEL,
        "language": DEEPGRAM_LANGUAGE,
        "encoding": "linear16",
        "sample_rate": str(sample_rate),
        "channels": "1",
        "punctuate": "true",
        "smart_format": "true" if DEEPGRAM_SMART_FORMAT else "false",
    }
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "audio/wav",
    }

    try:
        response = await _client().post(
            DEEPGRAM_API_URL,
            params=params,
            headers=headers,
            content=wav_bytes,
            timeout=httpx.Timeout(DEEPGRAM_TIMEOUT_SEC, connect=3.0),
        )
    except httpx.TimeoutException:
        print("❌ [DEEPGRAM STT] Request timeout", flush=True)
        return ""
    except Exception as e:
        print(f"❌ [DEEPGRAM STT] Exception: {e}", flush=True)
        logger.error("Deepgram STT exception: %s", e, exc_info=True)
        return ""

    if response.status_code != 200:
        print(
            f"❌ [DEEPGRAM STT] HTTP {response.status_code} | "
            f"{response.text[:500]}",
            flush=True,
        )
        return ""

    data = response.json()
    channels = data.get("results", {}).get("channels", [])
    if not channels:
        print("⚠️ [DEEPGRAM STT] No channels in response", flush=True)
        return ""

    alternatives = channels[0].get("alternatives", [])
    if not alternatives:
        print("⚠️ [DEEPGRAM STT] No alternatives in response", flush=True)
        return ""

    return (alternatives[0].get("transcript") or "").strip()


async def transcribe_pcm(
    pcm: bytes,
    sample_rate: int,
    energy_rms: Optional[int] = None,
) -> str:
    """Transcribe a single PCM utterance via Deepgram Nova."""
    if not pcm:
        return ""

    energy = energy_rms if energy_rms is not None else _rms(pcm)
    if energy < STT_MIN_ENERGY:
        print(
            f"🔇 [STT GATE] energy kam hai: rms={energy} < {STT_MIN_ENERGY}",
            flush=True,
        )
        return ""

    # Deepgram receives the native PCM rate; no Google/SpeechRecognition
    # fallback and no forced 8k -> 16k conversion.
    recognition_rate = sample_rate
    wav_bytes = _pcm_to_wav(pcm, recognition_rate)

    print(
        f"🎤 [STT] Deepgram {DEEPGRAM_MODEL} ko bhej rahe hain: "
        f"{len(wav_bytes)} B @ {recognition_rate} Hz | "
        f"rms={energy} | lang={DEEPGRAM_LANGUAGE}",
        flush=True,
    )

    t0 = time.monotonic()
    text = await _deepgram_transcribe(wav_bytes, recognition_rate)
    elapsed_ms = (time.monotonic() - t0) * 1000

    print(
        f"🎯 [STT RESULT] Deepgram | {elapsed_ms:.0f} ms | "
        f"{'EMPTY' if not text else repr(text)}",
        flush=True,
    )
    return text


# ============================================================
# SPEECH TRANSCRIBER (stateful per device)
# ============================================================

class SpeechTranscriber:
    """
    Per-device speech pipeline:

        PCM chunks -> UtteranceSegmenter -> asyncio.Queue -> Deepgram -> on_text
    """

    def __init__(self, device_id: str, sample_rate: int = 8000) -> None:
        self.device_id = device_id
        self.sample_rate = sample_rate
        self.segmenter = UtteranceSegmenter(sample_rate)
        self._queue: Optional[asyncio.Queue] = None
        self._worker: Optional[asyncio.Task] = None
        self._on_text: Optional[Callable[[str], Awaitable[None]]] = None

        # Half-duplex TTS gate.
        self._tts_playing = False
        self._tts_gate_until = 0.0

        # Periodic debug counters.
        self._dbg_t = time.monotonic()
        self._dbg_max_rms = 0
        self._dbg_bytes = 0
        self._dbg_gated = 0

    # -- TTS gate -----------------------------------------------------

    def set_tts_playing(self, playing: bool) -> None:
        """Called by the backend when TTS starts/stops going to the device."""
        now = time.monotonic()
        if playing:
            self._tts_playing = True
            self.segmenter.reset()
            print(
                f"🔇 [STT GATE] ON (TTS playing) device={self.device_id}",
                flush=True,
            )
        else:
            self._tts_playing = False
            self._tts_gate_until = now + TTS_GATE_HANGOVER_SEC
            self.segmenter.reset()
            print(
                f"🎤 [STT GATE] OFF (+{TTS_GATE_HANGOVER_SEC:.2f}s hangover) "
                f"device={self.device_id}",
                flush=True,
            )

    def is_gated(self) -> bool:
        return self._tts_playing or time.monotonic() < self._tts_gate_until

    # -- audio input --------------------------------------------------

    def set_sample_rate(self, sample_rate: int) -> None:
        if sample_rate == self.sample_rate:
            self.segmenter.reset()
            return
        self.sample_rate = sample_rate
        self.segmenter = UtteranceSegmenter(sample_rate)

    def feed(
        self,
        data: bytes,
        on_text: Callable[[str], Awaitable[None]],
    ) -> None:
        """Feed a PCM chunk. Detected utterances are queued for STT."""
        # Ignore mic while TTS is (or just was) playing; allow real barge-in.
        if self.is_gated():
            energy = _rms(data)
            self.segmenter.last_rms = energy
            self._debug_level(len(data), gated=True)
            if energy < TTS_BARGE_IN_RMS:
                return
            print(
                f"⚡ [BARGE-IN] rms={energy} >= {TTS_BARGE_IN_RMS} | "
                f"device={self.device_id}",
                flush=True,
            )
            self._tts_playing = False
            self._tts_gate_until = 0.0
            self.segmenter.reset()

        result = self.segmenter.feed(data)
        self._debug_level(len(data))
        if not result:
            return

        pcm, energy = result
        self._ensure_worker(on_text)
        duration = len(pcm) / (2 * self.sample_rate)

        print(
            f"📥 [STT QUEUE] duration={duration:.2f}s "
            f"bytes={len(pcm)} rms={energy} "
            f"rate={self.sample_rate} "
            f"queue={self._queue.qsize()}",
            flush=True,
        )
        try:
            self._queue.put_nowait((pcm, energy, self.sample_rate))
        except asyncio.QueueFull:
            print("⚠️ [STT] Queue full; utterance dropped", flush=True)

    def reset(self) -> None:
        self.segmenter.reset()
        self._drain_queue()
        self._tts_playing = False
        self._tts_gate_until = 0.0

    async def close(self) -> None:
        self._drain_queue()
        if self._worker and not self._worker.done():
            self._worker.cancel()
            try:
                await asyncio.wait_for(self._worker, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception:
                pass
        self._worker = None

    # -- internals ----------------------------------------------------

    def _ensure_worker(
        self, on_text: Callable[[str], Awaitable[None]]
    ) -> None:
        self._on_text = on_text
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=8)
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._worker_loop())

    def _drain_queue(self) -> None:
        if self._queue is None:
            return
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def _debug_level(self, nbytes: int, gated: bool = False) -> None:
        if not STT_DEBUG:
            return
        self._dbg_bytes += nbytes
        self._dbg_max_rms = max(self._dbg_max_rms, self.segmenter.last_rms)
        if gated:
            self._dbg_gated += 1

        now = time.monotonic()
        if now - self._dbg_t < 3.0:
            return

        dt = now - self._dbg_t
        print(
            f"🎚️ [VAD] mic={self._dbg_bytes / dt:,.0f} B/s "
            f"(expect {self.sample_rate * 2:,}) | "
            f"max_rms={self._dbg_max_rms} | "
            f"thr={self.segmenter.last_threshold:.0f} | "
            f"noise={self.segmenter.noise_floor:.0f} | "
            f"speaking={self.segmenter.speaking} | "
            f"gated={self.is_gated()} drops={self._dbg_gated}",
            flush=True,
        )
        self._dbg_t = now
        self._dbg_max_rms = 0
        self._dbg_bytes = 0
        self._dbg_gated = 0

    async def _worker_loop(self) -> None:
        assert self._queue is not None
        while True:
            pcm, energy, rate = await self._queue.get()
            try:
                duration = len(pcm) / 2 / rate
                print(
                    f"🧩 [UTTERANCE] {duration:.1f}s | rms={energy} | "
                    f"device={self.device_id}",
                    flush=True,
                )
                text = await transcribe_pcm(pcm, rate, energy)
                if text and self._on_text:
                    await self._on_text(text)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("❌ [STT WORKER] %s", e, exc_info=True)
                print(f"❌ [STT WORKER] {e}", flush=True)
            finally:
                try:
                    self._queue.task_done()
                except Exception:
                    pass


# ============================================================
# TTS TEXT CLEANING
# ============================================================

_URL_RE   = re.compile(r"https?://\S+")
_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]+")
_MD_RE    = re.compile(r"[\*\_\`#>\~|]+")
_WS_RE    = re.compile(r"\s+")


def clean_for_tts(text: str) -> str:
    """Strip URLs, emojis, markdown punctuation and collapse whitespace."""
    text = text or ""
    text = _URL_RE.sub("", text)
    text = _EMOJI_RE.sub("", text)
    text = _MD_RE.sub("", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


# ============================================================
# SARVAM TTS
# ============================================================

async def synthesize_tts_pcm(
    text: str,
    sample_rate: int = 8000,
    speaker: Optional[str] = None,
) -> bytes:
    """Text -> Sarvam Bulbul -> mono 16-bit PCM at `sample_rate`."""
    # Imported lazily so this module can be used standalone.
    from app.core.config import settings

    text = clean_for_tts(text)
    if not text:
        return b""

    sarvam_key = os.getenv("SARVAM_API_KEY", "") or getattr(
        settings, "SARVAM_API_KEY", ""
    )
    if not sarvam_key:
        print("❌ [TTS] SARVAM_API_KEY missing", flush=True)
        return b""

    safe_text = text[:TTS_MAX_CHARS]
    payload = {
        "text": safe_text,
        "target_language_code": TTS_LANGUAGE,
        "model": TTS_MODEL,
        "speaker": speaker or TTS_SPEAKER,
        "speech_sample_rate": sample_rate,
    }

    try:
        t0 = time.monotonic()
        response = await _client().post(
            SARVAM_TTS_URL,
            headers={
                "api-subscription-key": sarvam_key,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        elapsed_ms = (time.monotonic() - t0) * 1000
    except Exception as e:
        print(f"❌ [SARVAM TTS EXCEPTION] {e}", flush=True)
        logger.error("Sarvam TTS exception: %s", e, exc_info=True)
        return b""

    if response.status_code != 200:
        print(
            f"❌ [SARVAM TTS] HTTP {response.status_code} | "
            f"speaker={payload['speaker']} model={TTS_MODEL} | "
            f"{response.text[:300]}",
            flush=True,
        )
        return b""

    audios = response.json().get("audios") or []
    if not audios:
        print("❌ [SARVAM TTS] Empty audios response", flush=True)
        return b""

    wav_bytes = base64.b64decode(audios[0])
    pcm = await asyncio.to_thread(_wav_to_pcm, wav_bytes, sample_rate)
    if not pcm:
        print("❌ [TTS] Normalized PCM empty", flush=True)
        return b""

    if TTS_DEBUG_DUMP:
        try:
            path = f"/tmp/tts_{int(time.time() * 1000)}.wav"
            with open(path, "wb") as f:
                f.write(_pcm_to_wav(pcm, sample_rate))
            print(f"💾 [TTS DUMP] {path}", flush=True)
        except Exception as e:
            logger.warning("TTS dump failed: %s", e)

    audio_seconds = len(pcm) / 2 / sample_rate
    print(
        f"🔊 [SARVAM TTS] {elapsed_ms:.0f} ms | {audio_seconds:.2f}s | "
        f"{len(pcm)} B | {sample_rate} Hz | rms={_rms(pcm)} | "
        f"'{safe_text[:60]}'",
        flush=True,
    )
    return pcm