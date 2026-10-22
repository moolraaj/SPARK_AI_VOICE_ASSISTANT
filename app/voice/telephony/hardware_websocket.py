"""
Hardware voice session over WebRTC.

The ESP32 posts an SDP offer to /api/v1/webrtc/offer/{device_id}.
Audio is G.711 A-law at 8 kHz. JSON events use the negotiated data channel.

Changes vs v3:
  1. logging.basicConfig(INFO) -> Sarvam / STT logger.info lines ab terminal me dikhengi.
  2. Terminal par clean conversation print:  👤 USER: ...  /  🤖 AI: ...
  3. extract_text(): LLM chunk content str ya list dono handle.
  4. Fallback: agar stream se text nahi mila to graph state se final AI reply utha ke bolta hai.
  5. Har turn ke liye alag thread_id (checkpoint corrupt / duplicate history problem khatam).
  6. Bahut chhote transcripts (<3 chars) ignore (noise "hmm" se barge-in nahi hoga).
  7. Device credit / playback IDs replace estimated TTS pacing.
  8. DEBUG_EVENTS=1 env se graph events print kar sakte ho.

Transport patch:
  - Pace all outbound frames, including idle silence, at 20 ms intervals.
  - Drop unsent PCM on cancellation/failure without resetting RTP timestamps.
  - Trim input audio plane alignment padding before feeding STT.
  - Separate session creation logs from actual transport/data-channel readiness.

Firmware compatibility note: the existing byte-count playback protocol does not
identify individual RTP frames by playback_id. Idle silence, loss and control /
media reordering still require a coordinated firmware protocol update. This file
fixes backend pacing; it does not claim to fix an ESP32 reconnect panic.
"""

import os
import re
import sys
import json
import time
import wave
import logging
import asyncio
from array import array
from fractions import Fraction

from fastapi import APIRouter, HTTPException, Request, WebSocketDisconnect
from aiortc import RTCPeerConnection, RTCRtpSender, RTCSessionDescription
from aiortc.mediastreams import MediaStreamTrack, MediaStreamError
from av import AudioFrame
from av.audio.resampler import AudioResampler
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.ai.context.session_context_resolver import SessionContextResolver
from app.ai.prompts.prompt_builder import RuntimePromptBuilder
from app.ai.graph.graph import SparkAgentGraph
from app.modules.conversations.conversation_repository import ConversationRepository
from app.modules.organizations.organization_repository import OrganizationRepository
from app.database.mongodb import mongodb
from app.voice.telephony.sarvam_stt import SpeechTranscriber, synthesize_tts_pcm

tts_log = logging.getLogger("tts_stream")

def log_tts(event: str, **fields):
    record = {
        "event": event,
        "ts": time.time(),
        **fields,
    }
    tts_log.info(
        json.dumps(record, ensure_ascii=False, default=str)
    )

# Logger ko INFO pe laao, warna [SARVAM TTS] / [SPEECH RECOGNITION] lines dikhti hi nahi
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logging.getLogger("aiortc.rtcsctptransport").setLevel(logging.DEBUG)
logging.getLogger("aiortc.rtcdatachannel").setLevel(logging.DEBUG)
logging.getLogger("aiortc.rtcdtlstransport").setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)
# Temporary WebRTC handshake diagnostics
logging.getLogger("aiortc.rtcsctptransport").setLevel(logging.DEBUG)
logging.getLogger("aiortc.rtcdatachannel").setLevel(logging.DEBUG)
logging.getLogger("aiortc.rtcdtlstransport").setLevel(logging.DEBUG)


def log_sdp_transport(label: str, sdp: str):
    prefixes = (
        "m=",
        "a=mid:",
        "a=group:",
        "a=setup:",
        "a=sctp-port:",
        "a=sctpmap:",
        "a=max-message-size:",
    )

    lines = [
        line for line in sdp.splitlines()
        if line.startswith(prefixes)
    ]

    logger.info("[SDP %s]\n%s", label, "\n".join(lines))

router = APIRouter(tags=["Hardware Voice WebRTC"])

AUDIO_LOG_EVERY = int(os.getenv("AUDIO_LOG_EVERY", "0"))
SAVE_AUDIO_WAV = os.getenv("SAVE_AUDIO_WAV", "0") == "1"
SEND_STREAM_CHUNKS = os.getenv("SEND_STREAM_CHUNKS", "0") == "1"
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "16"))
DEBUG_EVENTS = os.getenv("DEBUG_EVENTS", "0") == "1"
MIN_TRANSCRIPT_CHARS = int(os.getenv("MIN_TRANSCRIPT_CHARS", "3"))

# ============================================================
# TTS PLAYBACK CONFIG
# ============================================================
TTS_SEND_CHUNK = 480
# Device-reported credit, rather than a guessed playback clock.
TTS_BUFFER_TARGET_SEC = 0.60
TTS_FEEDBACK_TIMEOUT_SEC = 8.0
TTS_COMPLETION_TIMEOUT_SEC = 8.0
TTS_ALLOW_BARGE_IN = os.getenv("TTS_ALLOW_BARGE_IN", "0") == "1"
DEFAULT_VOICE_ID = "shubh"

_SENT_SPLIT = re.compile(r"(?<=[.!?।])\s+|\n+")
MIN_SENT_CHARS = 14


def pop_sentences(buf: str):
    parts = _SENT_SPLIT.split(buf)
    if len(parts) <= 1:
        return [], buf
    return parts[:-1], parts[-1]


def trim_history(msgs: list, max_n: int) -> list:
    if len(msgs) <= max_n + 1:
        return msgs
    tail = list(msgs[-max_n:])
    while tail and isinstance(tail[0], AIMessage):
        tail.pop(0)
    return [msgs[0]] + tail


def normalize_phone(value):
    if not value:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())[-10:]
    return digits if len(digits) == 10 else None


def extract_text(content) -> str:
    """LangChain chunk content str ho ya list[{'type':'text','text':...}], dono se text nikalo."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for p in content:
            if isinstance(p, str):
                out.append(p)
            elif isinstance(p, dict) and p.get("type") == "text":
                out.append(p.get("text", ""))
        return "".join(out)
    return ""


def print_user(number: str, text: str):
    print(f"user: {text}", flush=True)


def print_ai(name: str, text: str):
    print(f"ai: {text}", flush=True)


# =====================================================================
# AUDIO MONITOR
# =====================================================================
class AudioMonitor:
    SILENCE_RMS = 100

    def __init__(self, device_id: str, sample_rate: int = 8000):
        self.device_id = device_id
        self.sample_rate = sample_rate
        self.codec = "unknown"
        self.chunks = 0
        self.total_bytes = 0
        self.silent_chunks = 0
        self.started_at = time.time()
        self.win_start = time.time()
        self.win_bytes = 0
        self.wav = None
        if SAVE_AUDIO_WAV:
            self._open_wav()

    def _open_wav(self):
        self._close_wav()
        path = f"/tmp/{self.device_id}_{int(time.time())}.wav"
        self.wav = wave.open(path, "wb")
        self.wav.setnchannels(1)
        self.wav.setsampwidth(2)
        self.wav.setframerate(self.sample_rate)
        print(f"💾 [AUDIO SAVE] Recording to {path} @ {self.sample_rate} Hz", flush=True)

    def _close_wav(self):
        if self.wav:
            try:
                self.wav.close()
            except Exception:
                pass
            self.wav = None

    def set_format(self, sample_rate: int, codec: str):
        self.sample_rate = sample_rate
        self.codec = codec
        print(f"🎼 [AUDIO FORMAT] Device={self.device_id} | codec={codec} | sample_rate={sample_rate} Hz", flush=True)
        if SAVE_AUDIO_WAV:
            self._open_wav()

    def feed(self, data: bytes):
        self.chunks += 1
        n = len(data)
        self.total_bytes += n
        self.win_bytes += n

        usable = n - (n % 2)
        samples = array("h")
        samples.frombytes(data[:usable])
        if sys.byteorder == "big":
            samples.byteswap()

        count = len(samples)
        if count:
            peak = max(abs(s) for s in samples)
            rms = int((sum(s * s for s in samples) / count) ** 0.5)
        else:
            peak = rms = 0

        is_silent = rms < self.SILENCE_RMS
        if is_silent:
            self.silent_chunks += 1

        if self.wav:
            self.wav.writeframes(data[:usable])

        if AUDIO_LOG_EVERY > 0 and self.chunks == 1:
            print(f"🔬 [AUDIO FIRST CHUNK] {n} bytes | hex[0:32]={data[:32].hex(' ')}", flush=True)

        if AUDIO_LOG_EVERY > 0 and self.chunks % AUDIO_LOG_EVERY == 0:
            bar = "█" * min(30, rms // 200)
            icon = "🔇" if is_silent else "🔊"
            print(
                f"🎙️ #{self.chunks:<5} {n:>4} B | {count:>4} samples | rms={rms:>5} | peak={peak:>5} {icon} {bar}",
                flush=True,
            )

        now = time.time()
        if AUDIO_LOG_EVERY > 0 and now - self.win_start >= 1.0:
            elapsed = now - self.win_start
            bps = self.win_bytes / elapsed
            expected = self.sample_rate * 2
            print(
                f"📊 [AUDIO 1s SUMMARY] {bps:,.0f} B/s (expected ~{expected:,} B/s) | "
                f"total={self.total_bytes:,} B | chunks={self.chunks} | silent={self.silent_chunks}",
                flush=True,
            )
            self.win_start = now
            self.win_bytes = 0

    def close(self):
        dur = time.time() - self.started_at
        print(
            f"🏁 [AUDIO SESSION END] Device={self.device_id} | chunks={self.chunks} | "
            f"bytes={self.total_bytes:,} | silent_chunks={self.silent_chunks} | duration={dur:.1f}s",
            flush=True,
        )
        self._close_wav()


async def resolve_org_name(ctx) -> str:
    if not ctx:
        return "Our Business"
    name = getattr(ctx, "org_name", None) or getattr(ctx, "organization_name", None)
    if name and str(name).strip():
        return str(name).strip()

    if getattr(ctx, "org_id", None):
        org_doc = await mongodb.database["organizations"].find_one({"_id": ctx.org_id})
        if not org_doc:
            try:
                from bson import ObjectId
                org_doc = await mongodb.database["organizations"].find_one({"_id": ObjectId(ctx.org_id)})
            except Exception:
                pass
        if org_doc and org_doc.get("name"):
            return org_doc["name"].strip()
    return "Our Business"


# ============================================================
# PACED PCM SENDER
# ============================================================
class PacedPCMSender:
    """Ordered PCM sender with per-sentence and per-chunk JSON diagnostics.

    Device 'played' means consumed by the ESP32 SCO callback, not acoustic
    confirmation from the speaker.
    """

    def __init__(self, websocket, device_id: str):
        self.ws = websocket
        self.device_id = device_id
        self.serial = 0
        self.active_id = None
        self.busy = False
        self.sent = 0                 # bytes submitted to websocket
        self.played = 0               # bytes reported consumed by device
        self.capacity = 0
        self.rate = 8000
        self.updated = asyncio.Event()
        self.done = asyncio.Event()
        self.completion = None
        self.last_sentence_end_mono = None

    def reset(self):
        self.active_id = None
        self.busy = False
        self.sent = self.played = self.capacity = 0
        self.completion = None
        self.updated.set()
        self.done.set()

    def seconds_ahead(self) -> float:
        return max(0, self.sent - self.played) / max(self.rate * 2, 1)

    def on_device_event(self, payload: dict):
        try:
            stream_id = int(payload.get("playback_id", -1))
            played = int(payload.get("played", 0))
            received = int(payload.get("received", 0))
        except (TypeError, ValueError):
            log_tts("device_feedback_invalid", device_id=self.device_id, payload=payload)
            return

        if stream_id != self.active_id or not self.busy:
            return

        if not (0 <= played <= received <= self.sent):
            log_tts(
                "device_feedback_out_of_range",
                device_id=self.device_id,
                sentence_id=stream_id,
                backend_submitted_bytes=self.sent,
                device_received_bytes=received,
                device_played_bytes=played,
            )
            return

        self.played = max(self.played, played)
        event = payload.get("event")

        if event == "ai_audio_buffer":
            try:
                capacity = int(payload.get("capacity", 0))
            except (TypeError, ValueError):
                return
            if capacity < 2 * TTS_SEND_CHUNK:
                log_tts(
                    "device_buffer_too_small", device_id=self.device_id,
                    sentence_id=stream_id, capacity_bytes=capacity,
                )
                return
            self.capacity = capacity
            log_tts(
                "device_buffer_ready", device_id=self.device_id,
                sentence_id=stream_id, capacity_bytes=capacity,
            )
        elif event == "ai_audio_played":
            self.completion = payload
            self.done.set()
            log_tts(
                "device_playback_ack", device_id=self.device_id,
                sentence_id=stream_id, received_bytes=received,
                played_bytes=played, dropped_bytes=payload.get("dropped"),
                ok=payload.get("ok"),
            )
        else:
            log_tts(
                "device_audio_progress", device_id=self.device_id,
                sentence_id=stream_id, device_event=event,
                received_bytes=received, played_bytes=played,
                backend_submitted_bytes=self.sent,
                bytes_in_flight=max(0, self.sent - self.played),
            )

        self.updated.set()

    async def _wait_for_update(self):
        await asyncio.wait_for(self.updated.wait(), TTS_FEEDBACK_TIMEOUT_SEC)

    async def send(self, pcm: bytes, rate: int, text: str = "") -> bool:
        pcm = pcm[:len(pcm) & ~1]  # complete PCM16 samples only
        if not pcm:
            log_tts("tts_sentence_empty", device_id=self.device_id, text=text)
            return False
        if self.busy:
            log_tts(
                "tts_sender_busy", device_id=self.device_id,
                active_sentence_id=self.active_id, text=text,
            )
            return False

        self.serial = (self.serial + 1) & 0xFFFFFFFF
        if not self.serial:
            self.serial = 1
        stream_id = self.serial
        self.active_id = stream_id
        self.busy = True
        self.sent = self.played = self.capacity = 0
        self.rate = rate
        self.completion = None
        self.updated.clear()
        self.done.clear()

        started = time.monotonic()
        inter_sentence_gap_ms = None
        if self.last_sentence_end_mono is not None:
            inter_sentence_gap_ms = (started - self.last_sentence_end_mono) * 1000

        total_chunks = (len(pcm) + TTS_SEND_CHUNK - 1) // TTS_SEND_CHUNK
        attempted_chunks = sent_chunks = failed_chunks = 0
        chunk_send_ms_total = credit_wait_ms_total = 0.0
        max_chunk_gap_ms = 0.0
        previous_chunk_end = None
        last_error = None
        window = 0

        log_tts(
            "tts_sentence_start", device_id=self.device_id,
            sentence_id=stream_id, text=text, sample_rate=rate,
            pcm_bytes=len(pcm), chunk_size_bytes=TTS_SEND_CHUNK,
            total_chunks=total_chunks,
            expected_audio_ms=round(len(pcm) / max(rate * 2, 1) * 1000, 2),
            inter_sentence_gap_ms=(round(inter_sentence_gap_ms, 2)
                                    if inter_sentence_gap_ms is not None else None),
        )

        try:
            await self.ws.send_text(json.dumps({
                "event": "ai_audio_start", "playback_id": stream_id,
                "sample_rate": rate, "total_bytes": len(pcm),
            }))

            buffer_wait_start = time.monotonic()
            while not self.capacity:
                self.updated.clear()
                if self.done.is_set():
                    raise RuntimeError("Hardware rejected playback start")
                await self._wait_for_update()

            window = min(
                self.capacity - 2 * TTS_SEND_CHUNK,
                int(rate * 2 * TTS_BUFFER_TARGET_SEC),
            ) & ~1
            if window < TTS_SEND_CHUNK:
                raise RuntimeError(f"Hardware buffer/window too small: {window}")

            log_tts(
                "tts_buffer_wait_complete", device_id=self.device_id,
                sentence_id=stream_id,
                wait_ms=round((time.monotonic() - buffer_wait_start) * 1000, 2),
                device_capacity_bytes=self.capacity, send_window_bytes=window,
            )

            for offset in range(0, len(pcm), TTS_SEND_CHUNK):
                chunk = pcm[offset:offset + TTS_SEND_CHUNK]
                chunk_index = offset // TTS_SEND_CHUNK + 1
                credit_wait_start = time.monotonic()

                while self.sent - self.played + len(chunk) > window:
                    self.updated.clear()
                    if self.done.is_set():
                        raise RuntimeError("Hardware aborted PCM stream")
                    await self._wait_for_update()

                credit_wait_ms = (time.monotonic() - credit_wait_start) * 1000
                credit_wait_ms_total += credit_wait_ms
                if self.done.is_set():
                    raise RuntimeError("Hardware completed before all PCM was sent")

                attempted_chunks += 1
                send_started = time.monotonic()
                gap_ms = 0.0
                if previous_chunk_end is not None:
                    gap_ms = (send_started - previous_chunk_end) * 1000
                    max_chunk_gap_ms = max(max_chunk_gap_ms, gap_ms)

                # Existing protocol counts bytes in-flight before awaiting send.
                self.sent += len(chunk)
                try:
                    await self.ws.send_bytes(chunk)
                    send_finished = time.monotonic()
                    previous_chunk_end = send_finished
                    send_ms = (send_finished - send_started) * 1000
                    chunk_send_ms_total += send_ms
                    sent_chunks += 1
                    log_tts(
                        "tts_chunk_sent", device_id=self.device_id,
                        sentence_id=stream_id, chunk_index=chunk_index,
                        total_chunks=total_chunks, chunk_bytes=len(chunk),
                        cumulative_backend_sent_bytes=self.sent,
                        device_played_bytes=self.played,
                        bytes_in_flight=max(0, self.sent - self.played),
                        send_ms=round(send_ms, 2),
                        credit_wait_ms=round(credit_wait_ms, 2),
                        gap_from_previous_chunk_ms=round(gap_ms, 2),
                        backend_send_status="ok",
                    )
                except Exception as exc:
                    failed_chunks += 1
                    last_error = str(exc)
                    log_tts(
                        "tts_chunk_send_failed", device_id=self.device_id,
                        sentence_id=stream_id, chunk_index=chunk_index,
                        total_chunks=total_chunks, chunk_bytes=len(chunk),
                        cumulative_backend_submitted_bytes=self.sent,
                        error=last_error,
                    )
                    raise

            await self.ws.send_text(json.dumps({
                "event": "ai_audio_end", "playback_id": stream_id,
            }))

            ack_wait_start = time.monotonic()
            await asyncio.wait_for(self.done.wait(), TTS_COMPLETION_TIMEOUT_SEC)
            ack_wait_ms = (time.monotonic() - ack_wait_start) * 1000
            result = self.completion or {}
            received = int(result.get("received", -1))
            played = int(result.get("played", -1))
            dropped = int(result.get("dropped", -1))
            complete = (
                result.get("ok") is True and received == len(pcm)
                and played == len(pcm) and dropped == 0
                and sent_chunks == total_chunks
            )

            log_tts(
                "tts_sentence_summary", device_id=self.device_id,
                sentence_id=stream_id, text=text, sample_rate=rate,
                pcm_bytes=len(pcm), chunk_size_bytes=TTS_SEND_CHUNK,
                total_chunks=total_chunks, attempted_chunks=attempted_chunks,
                backend_sent_chunks=sent_chunks,
                backend_failed_chunks=failed_chunks,
                backend_unsent_chunks=max(0, total_chunks - sent_chunks),
                backend_submitted_bytes=self.sent,
                esp_received_bytes=received, esp_played_bytes=played,
                esp_dropped_bytes=dropped,
                chunk_send_total_ms=round(chunk_send_ms_total, 2),
                average_chunk_send_ms=round(chunk_send_ms_total / max(sent_chunks, 1), 2),
                total_credit_wait_ms=round(credit_wait_ms_total, 2),
                max_chunk_gap_ms=round(max_chunk_gap_ms, 2),
                completion_ack_wait_ms=round(ack_wait_ms, 2),
                playback_elapsed_ms=round((time.monotonic() - started) * 1000, 2),
                inter_sentence_gap_ms=(round(inter_sentence_gap_ms, 2)
                                        if inter_sentence_gap_ms is not None else None),
                status="ok" if complete else "incomplete",
            )

            logger.info(
                "[TTS STREAM CHECK] device=%s id=%s expected=%d sent_chunks=%d/%d "
                "received=%s played=%s dropped=%s ok=%s",
                self.device_id, stream_id, len(pcm), sent_chunks, total_chunks,
                result.get("received"), result.get("played"),
                result.get("dropped"), result.get("ok"),
            )
            if not complete:
                raise RuntimeError(f"Incomplete hardware playback: {result}")

            logger.info(
                "TTS PLAYED device=%s id=%s bytes=%s elapsed=%.2fs text=%r",
                self.device_id, stream_id, len(pcm),
                time.monotonic() - started, text[:60],
            )
            return True

        except asyncio.CancelledError:
            log_tts(
                "tts_sentence_cancelled", device_id=self.device_id,
                sentence_id=stream_id, text=text,
                total_chunks=total_chunks, attempted_chunks=attempted_chunks,
                backend_sent_chunks=sent_chunks,
                backend_failed_chunks=failed_chunks,
                backend_unsent_chunks=max(0, total_chunks - sent_chunks),
                backend_submitted_bytes=self.sent,
            )
            raise
        except Exception as exc:
            last_error = str(exc)
            log_tts(
                "tts_sentence_failed", device_id=self.device_id,
                sentence_id=stream_id, text=text, total_chunks=total_chunks,
                attempted_chunks=attempted_chunks, backend_sent_chunks=sent_chunks,
                backend_failed_chunks=failed_chunks,
                backend_unsent_chunks=max(0, total_chunks - sent_chunks),
                backend_submitted_bytes=self.sent, device_played_bytes=self.played,
                elapsed_ms=round((time.monotonic() - started) * 1000, 2),
                error=last_error,
            )
            logger.exception(
                "TTS playback failed: device=%s id=%s sent=%s played=%s",
                self.device_id, stream_id, self.sent, self.played,
            )
            try:
                await asyncio.wait_for(self.ws.send_text(json.dumps({
                    "event": "ai_audio_cancel", "playback_id": stream_id,
                    "reason": "playback feedback failure",
                })), timeout=2.0)
            except Exception:
                pass
            return False
        finally:
            self.last_sentence_end_mono = time.monotonic()
            if self.active_id == stream_id:
                self.busy = False
                self.active_id = None


async def hardware_voice_websocket(websocket, device_id: str):
    """Run the hardware voice session on a WebRTC link."""
    await websocket.accept()
    print("\n==================================================", flush=True)
    print(f"🔌 [WEBRTC SESSION CREATED] Device ID: {device_id}", flush=True)
    print("==================================================\n", flush=True)
    logger.info("WebRTC session created; waiting for device events | device_id=%s", device_id)

    ctx = None
    session_id = None
    graph = None
    system_prompt = ""
    messages = []
    conversation_repo = ConversationRepository()


    audio_monitor = AudioMonitor(device_id)
    stt_transcriber = SpeechTranscriber(device_id)
    pacer = PacedPCMSender(websocket, device_id)

    device_sample_rate = 8000
    sco_ready = False
    call_is_active = False
    pending_greeting_text = None
    pending_greeting_speaker = DEFAULT_VOICE_ID

    customer_number = "unknown"
    owner_number = "unknown"
    ai_display_name = "AI"
    turn_no = 0

    turn_lock = asyncio.Lock()

    bg_tasks: set = set()
    current_turn_task: asyncio.Task | None = None

    def run_in_background(coro):
        task = asyncio.create_task(coro)
        bg_tasks.add(task)
        task.add_done_callback(bg_tasks.discard)
        return task

    # ---------------- TTS pipeline ----------------
    tts_generation = 0
    tts_queue: asyncio.Queue = asyncio.Queue()
    pcm_queue: asyncio.Queue = asyncio.Queue(maxsize=4)
    tts_tasks: list = []
    tts_gate_epoch = 0
    tts_gate_release_task: asyncio.Task | None = None

    def tts_gate_on():
        nonlocal tts_gate_epoch, tts_gate_release_task
        tts_gate_epoch += 1
        if tts_gate_release_task and not tts_gate_release_task.done():
            tts_gate_release_task.cancel()
        tts_gate_release_task = None
        stt_transcriber.set_tts_playing(True)

    def tts_gate_off_later(delay: float):
        nonlocal tts_gate_release_task
        epoch = tts_gate_epoch

        async def _release():
            try:
                await asyncio.sleep(max(0.0, delay))
                if epoch == tts_gate_epoch:
                    stt_transcriber.set_tts_playing(False)
            except asyncio.CancelledError:
                pass

        tts_gate_release_task = asyncio.create_task(_release())

    def tts_gate_off_now():
        nonlocal tts_gate_epoch, tts_gate_release_task
        tts_gate_epoch += 1
        if tts_gate_release_task and not tts_gate_release_task.done():
            tts_gate_release_task.cancel()
        tts_gate_release_task = None
        stt_transcriber.set_tts_playing(False)

    async def synth_worker():
        while True:
            text, speaker, rate, generation = await tts_queue.get()
            synth_started = time.monotonic()
            log_tts(
                "tts_synthesis_start", device_id=device_id,
                generation=generation, text=text, sample_rate=rate,
                tts_queue_size=tts_queue.qsize(),
            )
            try:
                if generation != tts_generation:
                    log_tts(
                        "tts_synthesis_skipped_stale", device_id=device_id,
                        generation=generation, current_generation=tts_generation,
                        text=text,
                    )
                    continue

                pcm = await synthesize_tts_pcm(
                    text, sample_rate=rate, speaker=speaker
                )
                synthesis_ms = (time.monotonic() - synth_started) * 1000

                if generation != tts_generation:
                    log_tts(
                        "tts_synthesis_dropped_stale", device_id=device_id,
                        generation=generation, current_generation=tts_generation,
                        text=text, synthesis_ms=round(synthesis_ms, 2),
                        pcm_bytes=len(pcm or b""),
                    )
                    continue

                if pcm:
                    pcm_bytes = len(pcm)
                    expected_audio_ms = pcm_bytes / max(rate * 2, 1) * 1000
                    log_tts(
                        "tts_synthesis_complete", device_id=device_id,
                        generation=generation, text=text, sample_rate=rate,
                        pcm_bytes=pcm_bytes,
                        total_chunks=(pcm_bytes + TTS_SEND_CHUNK - 1) // TTS_SEND_CHUNK,
                        synthesis_ms=round(synthesis_ms, 2),
                        expected_audio_ms=round(expected_audio_ms, 2),
                        realtime_factor=round(synthesis_ms / max(expected_audio_ms, 1), 3),
                    )
                    await pcm_queue.put((pcm, rate, text, generation))
                    log_tts(
                        "tts_pcm_queued", device_id=device_id,
                        generation=generation, text=text, pcm_bytes=pcm_bytes,
                        pcm_queue_size=pcm_queue.qsize(),
                    )
                else:
                    log_tts(
                        "tts_synthesis_empty", device_id=device_id,
                        generation=generation, text=text,
                        synthesis_ms=round(synthesis_ms, 2),
                    )
                    print(
                        f"⚠️ [TTS] Empty/failed audio for device={device_id} "
                        f"| speaker={speaker} | '{text[:40]}'", flush=True,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as tts_err:
                log_tts(
                    "tts_synthesis_failed", device_id=device_id,
                    generation=generation, text=text,
                    elapsed_ms=round((time.monotonic() - synth_started) * 1000, 2),
                    error=str(tts_err),
                )
                logger.error(f"TTS synth worker error: {tts_err}", exc_info=True)
            finally:
                tts_queue.task_done()

    async def play_worker():
        nonlocal tts_generation
        while True:
            pcm, rate, text, generation = await pcm_queue.get()
            play_started = time.monotonic()
            try:
                if generation != tts_generation:
                    log_tts(
                        "tts_pcm_skipped_stale", device_id=device_id,
                        generation=generation, current_generation=tts_generation,
                        text=text, pcm_bytes=len(pcm),
                    )
                    continue

                log_tts(
                    "tts_playback_start", device_id=device_id,
                    generation=generation, text=text, pcm_bytes=len(pcm),
                    sample_rate=rate, pcm_queue_size=pcm_queue.qsize(),
                )
                tts_gate_on()
                sent_ok = await pacer.send(pcm, rate, text)
                log_tts(
                    "tts_playback_worker_complete", device_id=device_id,
                    generation=generation, text=text, pcm_bytes=len(pcm),
                    success=sent_ok,
                    elapsed_ms=round((time.monotonic() - play_started) * 1000, 2),
                )

                if not sent_ok and generation == tts_generation:
                    old_generation = tts_generation
                    tts_generation += 1
                    log_tts(
                        "tts_generation_invalidated", device_id=device_id,
                        old_generation=old_generation,
                        new_generation=tts_generation,
                        reason="playback_failed",
                    )
                    clear_tts_queue()

                if generation == tts_generation and not pcm_queue.empty():
                    # Keep STT gated while another synthesized sentence is ready.
                    pass
                else:
                    tts_gate_off_now()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                tts_gate_off_now()
                log_tts(
                    "tts_play_worker_exception", device_id=device_id,
                    generation=generation, text=text, error=str(exc),
                )
                logger.exception("TTS play worker failed: device=%s", device_id)
            finally:
                pcm_queue.task_done()

    def start_tts_workers():
        tts_tasks.append(asyncio.create_task(synth_worker()))
        tts_tasks.append(asyncio.create_task(play_worker()))

    async def stop_tts_workers():
        for t in tts_tasks:
            if not t.done():
                t.cancel()
        for t in tts_tasks:
            try:
                await asyncio.wait_for(t, timeout=1.5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                logger.warning(f"tts worker cancel wait error: {e}")
        tts_tasks.clear()

    def _drain(q: asyncio.Queue, queue_name: str):
        dropped_items = 0
        while True:
            try:
                item = q.get_nowait()
            except asyncio.QueueEmpty:
                break
            dropped_items += 1
            try:
                if queue_name == "tts_queue":
                    text, speaker, rate, generation = item
                    pcm_bytes = None
                else:
                    pcm, rate, text, generation = item
                    pcm_bytes = len(pcm)
                log_tts(
                    "tts_queue_item_dropped", device_id=device_id,
                    queue=queue_name, generation=generation,
                    text=str(text)[:160], pcm_bytes=pcm_bytes,
                    reason="queue_cleared",
                )
            except Exception:
                logger.exception("Could not log dropped item from %s", queue_name)
            finally:
                q.task_done()
        return dropped_items

    def clear_tts_queue():
        dropped_tts = _drain(tts_queue, "tts_queue")
        dropped_pcm = _drain(pcm_queue, "pcm_queue")
        log_tts(
            "tts_queue_clear_summary", device_id=device_id,
            dropped_tts_items=dropped_tts, dropped_pcm_items=dropped_pcm,
        )

    async def cancel_tts_playback(reason: str = "new user speech"):
        nonlocal tts_generation
        old_generation = tts_generation
        tts_generation += 1
        generation = tts_generation
        tts_gate_off_now()

        log_tts(
            "tts_cancel_requested", device_id=device_id,
            old_generation=old_generation, generation=generation,
            reason=reason, tts_queue_size=tts_queue.qsize(),
            pcm_queue_size=pcm_queue.qsize(),
        )
        print(
            f"🛑 [TTS CANCEL] device={device_id} gen={generation} reason={reason}",
            flush=True,
        )

        try:
            await websocket.send_text(json.dumps({
                "event": "ai_audio_cancel",
                "generation": generation,
                "reason": reason,
            }))
        except Exception:
            pass

        await stop_tts_workers()
        clear_tts_queue()
        websocket.clear_pending_audio()
        pacer.reset()
        start_tts_workers()

    async def restart_tts_workers():
        await cancel_tts_playback(reason="call reset")

    start_tts_workers()

    def speak(text: str, speaker: str):
        text = (text or "").strip()
        if not text:
            return
        generation = tts_generation
        log_tts(
            "tts_sentence_queued", device_id=device_id,
            generation=generation, text=text, text_chars=len(text),
            sample_rate=device_sample_rate,
            tts_queue_size=tts_queue.qsize(), pcm_queue_size=pcm_queue.qsize(),
        )
        tts_queue.put_nowait(
            (text, speaker, device_sample_rate, generation)
        )

    async def cancel_active_turn():
        nonlocal current_turn_task
        task = current_turn_task
        if task is not None and not task.done() and task is not asyncio.current_task():
            print("🛑 [TURN CANCEL] Cancelling previous LLM turn", flush=True)
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                logger.warning(f"Previous turn cancel error: {e}")
        current_turn_task = None

    async def submit_user_turn(user_query: str):
        nonlocal current_turn_task
        await cancel_active_turn()
        await cancel_tts_playback(reason="new user speech")
        current_turn_task = asyncio.create_task(run_agent_turn(user_query))

    def reset_call_state(keep_sco_state: bool = False):
        nonlocal sco_ready, pending_greeting_text, pending_greeting_speaker
        nonlocal device_sample_rate, ctx, graph, messages, session_id
        nonlocal customer_number, owner_number, ai_display_name, turn_no

        if not keep_sco_state:
            sco_ready = False
            device_sample_rate = 8000
            try:
                stt_transcriber.reset()
            except Exception:
                pass

        pending_greeting_text = None
        pending_greeting_speaker = DEFAULT_VOICE_ID
        ctx = None
        graph = None
        messages = []
        session_id = None
        customer_number = "unknown"
        owner_number = "unknown"
        ai_display_name = "AI"
        turn_no = 0

    # =================================================================
    # start_call
    # =================================================================
    async def start_call(payload: dict, send_greeting: bool = True) -> bool:
        nonlocal ctx, graph, messages, session_id, system_prompt
        nonlocal customer_number, owner_number, ai_display_name
        nonlocal pending_greeting_text, pending_greeting_speaker

        did_number = payload.get("did_number") or None
        caller_phone = payload.get("caller_phone") or None

        session_id = (
            f"SESSION_{device_id}_{caller_phone}"
            if caller_phone
            else f"SESSION_{device_id}"
        )

        print(f"📞 [CALL START] Device={device_id} | DID={did_number or 'from-device-lookup'} | Caller={caller_phone or 'unknown'} | Session={session_id}", flush=True)
        logger.info(f"📞 Call Start on Device {device_id} | DID={did_number} | Caller={caller_phone}")

        resolver = SessionContextResolver()
        try:
            ctx = await resolver.resolve(
                did_number=did_number,
                caller_phone=caller_phone,
                device_id=device_id,
            )
        except RuntimeError as resolve_err:
            logger.error(f"❌ [CONTEXT ERROR] {resolve_err}")
            print(f"❌ [CONTEXT ERROR] {resolve_err}", flush=True)
            print(
                f"   ➡️  Fix: POST /api/v1/organization/link-device/<org_id>  body: {{\"device_id\": \"{device_id}\"}}",
                flush=True,
            )
            ctx = None
            try:
                await websocket.send_text(json.dumps({
                    "event": "error",
                    "code": "device_not_linked",
                    "message": (
                        f"Device '{device_id}' is not linked to any organization. "
                        f"Use POST /api/v1/organization/link-device/<org_id> to link it."
                    ),
                }))
            except Exception:
                pass
            return False

        org_name = await resolve_org_name(ctx)

        ai_emp = getattr(ctx, "ai_employee", {}) or {}
        plat_cfg = getattr(ctx, "platform_config", {}) or {}
        biz_type = getattr(ctx, "business_type", "general")
        ai_display_name = ai_emp.get("name") or "AI"

        print(f"🏢 [CONTEXT RESOLVED] Org='{org_name}' | AI Employee='{ai_emp.get('name')}' | BizType='{biz_type}' | voice_id='{ai_emp.get('voice_id')}'", flush=True)

        _ctx_phone = getattr(ctx, "did_number", None)
        if not _ctx_phone and getattr(ctx, "org_id", None):
            try:
                from bson import ObjectId as _ObjId
                _org_doc = await mongodb.database["organizations"].find_one(
                    {"_id": _ObjId(ctx.org_id)},
                    {"phone": 1, "did_number": 1}
                )
                _ctx_phone = (_org_doc or {}).get("phone") or (_org_doc or {}).get("did_number")
            except Exception:
                pass
        org_number_display = _ctx_phone or "not configured"

        customer_number = normalize_phone(caller_phone) or "unknown"
        owner_number = normalize_phone(org_number_display) or org_number_display

        print("\n" + "=" * 60, flush=True)
        print("📋 [CALL SESSION METADATA]", flush=True)
        print(f"   🏢 org_name:     {org_name}", flush=True)
        print(f"   📞 org_number:   {org_number_display}", flush=True)
        print(f"   📱 device_id:    {device_id}", flush=True)
        print(f"   👤 user_number:  {caller_phone or 'unknown'}", flush=True)
        print("=" * 60 + "\n", flush=True)

        system_prompt = RuntimePromptBuilder.build(
            ai_employee=ai_emp,
            organization_name=org_name,
            platform_config=plat_cfg,
        )

        agent = SparkAgentGraph(business_type=biz_type)
        graph = agent.build()

        existing_conv = await conversation_repo.get_by_session_id(session_id)
        messages = [SystemMessage(content=system_prompt)]

        if existing_conv and existing_conv.get("messages"):
            for m in existing_conv["messages"][-MAX_HISTORY_MESSAGES:]:
                if m.get("role") == "user":
                    messages.append(HumanMessage(content=m.get("content", "")))
                elif m.get("role") == "assistant":
                    messages.append(AIMessage(content=m.get("content", "")))
            while len(messages) > 1 and isinstance(messages[1], AIMessage):
                messages.pop(1)

        voice_id = ai_emp.get("voice_id", DEFAULT_VOICE_ID)
        greeting_text = f"Namaste! Main {ai_emp.get('name', 'Assistant')} bol raha hu {org_name} se. Bataiye kaise help karu?"

        out_msg = {
            "event": "call_ready",
            "session_id": session_id,
            "greeting": greeting_text,
            "ai_name": ai_emp.get("name"),
            "voice_id": voice_id,
        }
        print(f"📤 [WEBSOCKET OUTGOING] Sending call_ready to Device={device_id}: {out_msg}", flush=True)
        try:
            await websocket.send_text(json.dumps(out_msg))
        except Exception:
            pass

        if send_greeting:
            print_ai(ai_display_name, greeting_text)
            if sco_ready:
                print("📤 [GREETING] SCO already ready, turant bhej rahe hain", flush=True)
                speak(greeting_text, voice_id)
            else:
                pending_greeting_text = greeting_text
                pending_greeting_speaker = voice_id
                print("⏳ [GREETING QUEUED] SCO abhi ready nahi hai, audio_format ka wait kar rahe hain", flush=True)

        return True

    # =================================================================
    # run_agent_turn
    # =================================================================
    async def run_agent_turn(user_query: str):
        nonlocal messages, turn_no

        async with turn_lock:
            if not user_query or not graph or not ctx:
                return

            messages.append(HumanMessage(content=user_query))
            messages = trim_history(messages, MAX_HISTORY_MESSAGES)

            # Har turn ka alag thread_id: cancelled turn ka adhura checkpoint next turn ko kharab nahi karega
            turn_no += 1
            thread_id = f"{session_id}_t{turn_no}"

            ai_reply_content = ""
            sentence_buf = ""
            pending = ""
            spoken_any = False
            turn_t0 = time.monotonic()

            ai_emp = getattr(ctx, "ai_employee", {}) or {}
            voice_id = ai_emp.get("voice_id", DEFAULT_VOICE_ID)

            try:
                async for event in graph.astream_events(
                    {
                        "messages": messages,
                        "owner_id": getattr(ctx, "owner_id", None),
                        "org_id": getattr(ctx, "org_id", None),
                        "business_type": getattr(ctx, "business_type", "general"),
                        "business_type_id": getattr(ctx, "business_type_id", None),
                        "ai_employee_id": getattr(ctx, "ai_employee_id", None),
                        "ai_employee": ai_emp,
                        "platform_config": getattr(ctx, "platform_config", {}),
                    },
                    config={"configurable": {"thread_id": thread_id}},
                    version="v2",
                ):
                    if DEBUG_EVENTS:
                        print("EVT:", event.get("event"), event.get("name"), flush=True)

                    if event.get("event") != "on_chat_model_stream":
                        continue

                    chunk = event.get("data", {}).get("chunk")
                    content = extract_text(getattr(chunk, "content", ""))
                    if not content:
                        continue

                    ai_reply_content += content
                    sentence_buf += content

                    if SEND_STREAM_CHUNKS:
                        try:
                            await websocket.send_text(json.dumps({
                                "event": "ai_stream_chunk",
                                "chunk": content,
                            }))
                        except Exception:
                            pass

                    if sco_ready:
                        sentences, sentence_buf = pop_sentences(sentence_buf)
                        for s in sentences:
                            pending = f"{pending} {s}".strip()
                            if len(pending) >= MIN_SENT_CHARS:
                                if not spoken_any:
                                    print(f"⏱️ [LATENCY] first sentence ready in {(time.monotonic() - turn_t0) * 1000:.0f} ms after transcript", flush=True)
                                    spoken_any = True
                                speak(pending, voice_id)
                                pending = ""

            except asyncio.CancelledError:
                if messages and isinstance(messages[-1], HumanMessage) and messages[-1].content == user_query:
                    messages.pop()
                print(f"🛑 [LLM TURN CANCELLED] '{user_query[:60]}'", flush=True)
                raise
            except Exception as llm_err:
                logger.error(f"❌ [LLM ERROR] session={session_id}: {llm_err}", exc_info=True)
                print(f"❌ [LLM ERROR] {llm_err}", flush=True)
                return

            # ---------- FALLBACK: stream se kuch nahi aaya to graph state se final reply lo ----------
            if not ai_reply_content:
                print("⚠️ [LLM EMPTY] stream se text nahi mila -> graph state se try kar rahe hain", flush=True)
                try:
                    snap = await graph.aget_state({"configurable": {"thread_id": thread_id}})
                    msgs_state = (snap.values or {}).get("messages", []) if snap else []
                    for m in reversed(msgs_state):
                        if isinstance(m, AIMessage):
                            txt = extract_text(m.content).strip()
                            if txt:
                                ai_reply_content = txt
                                # poora reply ek saath bolo (streaming nahi hui thi)
                                sentence_buf = ""
                                pending = ""
                                if sco_ready:
                                    for s in [x for x in _SENT_SPLIT.split(txt) if x.strip()]:
                                        speak(s, voice_id)
                                else:
                                    print("⚠️ [TTS SKIPPED] SCO ready nahi hai", flush=True)
                            break
                except Exception as e:
                    logger.error(f"❌ [FALLBACK ERROR] {e}", exc_info=True)

                if not ai_reply_content:
                    print("❌ [LLM EMPTY] graph ne koi reply nahi diya (logs upar dekho)", flush=True)
                    return
            else:
                tail = f"{pending} {sentence_buf}".strip()
                if tail:
                    if sco_ready:
                        speak(tail, voice_id)
                    else:
                        print("⚠️ [TTS SKIPPED] SCO abhi ready nahi hai, reply audio nahi bhej rahe", flush=True)

            # ---------- CONVERSATION PRINT ----------
            print_ai(ai_display_name, ai_reply_content)

            messages.append(AIMessage(content=ai_reply_content))

            async def _save():
                try:
                    await conversation_repo.save_message(
                        session_id=session_id,
                        owner_id=getattr(ctx, "owner_id", None),
                        org_id=getattr(ctx, "org_id", None),
                        employee_id=getattr(ctx, "ai_employee_id", None),
                        user_message=user_query,
                        assistant_reply=ai_reply_content,
                        cart=[],
                        customer_id=getattr(ctx, "customer_id", None),
                    )
                except Exception as save_err:
                    logger.error(f"Failed to save conversation to DB: {save_err}")

            run_in_background(_save())

            try:
                await websocket.send_text(json.dumps({
                    "event": "ai_response_complete",
                    "full_text": ai_reply_content,
                    "voice_id": voice_id,
                }))
            except Exception:
                pass

    # =================================================================
    # Live STT callback
    # =================================================================
    async def handle_live_transcription(transcribed_text: str):
        transcribed_text = (transcribed_text or "").strip()
        if not transcribed_text:
            return

        # This bundle defaults to half-duplex hardware playback.
        # A late STT result from before TTS must not cancel the current audio.
        if pacer.busy and not TTS_ALLOW_BARGE_IN:
            logger.info("Ignoring late STT while AI playback is active: %s", device_id)
            return

        if not call_is_active:
            print(
                f"🗑️ [STT STALE] Ignoring transcript outside active call: "
                f"'{transcribed_text[:60]}'",
                flush=True,
            )
            return

        if len(transcribed_text) < MIN_TRANSCRIPT_CHARS:
            print(f"🔇 [STT IGNORED] bahut chhota transcript: '{transcribed_text}'", flush=True)
            return

        # ---------- CONVERSATION PRINT ----------
        print_user(customer_number, transcribed_text)
        logger.info(f"🗣️ Speech Transcribed | Device={device_id} | Text='{transcribed_text}'")

        if not (graph and ctx):
            print(
                "⚠️ [NO CTX] Active call transcript arrived before context; "
                "dropping instead of creating a ghost session",
                flush=True,
            )
            return

        try:
            await submit_user_turn(transcribed_text)
        except asyncio.CancelledError:
            raise
        except Exception as turn_err:
            logger.error(f"❌ [TURN ERROR] {turn_err}", exc_info=True)

    # =================================================================
    # MAIN LOOP
    # =================================================================
    try:
        while True:
            raw_msg = await websocket.receive()

            if raw_msg.get("type") == "websocket.disconnect":
                logger.warning("Device disconnected: id=%s code=%s reason=%s",
                               device_id, raw_msg.get("code"), raw_msg.get("reason"))
                break

            # ---------------- JSON control / events ----------------
            if raw_msg.get("text") is not None:
                raw_text = raw_msg["text"]
                if DEBUG_EVENTS:
                    print(f"[DEVICE EVENT] {device_id}: {raw_text}", flush=True)

                try:
                    payload = json.loads(raw_text)
                except Exception as parse_err:
                    print(f"⚠️ [WEBSOCKET ERROR] JSON parse error: {parse_err} | Text: {raw_text}", flush=True)
                    logger.error(f"Failed to parse WebSocket JSON payload: {parse_err}")
                    continue

                event_type = payload.get("event")
                if event_type in ("ai_audio_buffer", "ai_audio_played"):
                    pacer.on_device_event(payload)
                    continue
                logger.info("[DEVICE EVENT] device=%s event=%s", device_id, event_type)

                try:
                    # ---------------- device_ready ----------------
                    if event_type == "device_ready":
                        print(f"🟢 [DEVICE READY ACK] Device={device_id} is connected & ready", flush=True)
                        logger.info(f"🟢 Device Ready | device_id={device_id}")

                        _org_repo = OrganizationRepository()
                        _org_for_device = await _org_repo.get_by_device_id(device_id)

                        if _org_for_device:
                            print(f"✅ [DEVICE REGISTERED] Device={device_id} -> Org='{_org_for_device.get('name', 'unknown')}'", flush=True)
                        else:
                            from datetime import datetime, timezone as _tz
                            _devices_col = mongodb.database["spark_devices"]
                            _existing = await _devices_col.find_one({"device_id": device_id})
                            if not _existing:
                                await _devices_col.insert_one({
                                    "device_id": device_id,
                                    "status": "unregistered",
                                    "org_id": None,
                                    "first_seen": datetime.now(_tz.utc),
                                    "last_seen": datetime.now(_tz.utc),
                                })
                                print(f"📝 [DEVICE AUTO-SAVED] Device={device_id} saved to 'spark_devices' (unregistered)", flush=True)
                                logger.warning(f"New unregistered device saved: {device_id} — assign org via dashboard")
                            else:
                                await _devices_col.update_one(
                                    {"device_id": device_id},
                                    {"$set": {"last_seen": datetime.now(_tz.utc)}}
                                )
                                print(f"⚠️ [DEVICE UNREGISTERED] Device={device_id} known but not assigned to any org!", flush=True)

                        out_msg = {
                            "event": "server_ready",
                            "status": "connected",
                            "device_id": device_id,
                            "registered": _org_for_device is not None,
                        }
                        print(f"📤 [WEBSOCKET OUTGOING] Sending server_ready to Device={device_id}: {out_msg}", flush=True)
                        await websocket.send_text(json.dumps(out_msg))

                    # ---------------- audio_format ----------------
                    elif event_type == "audio_format":
                        s_rate = int(payload.get("sample_rate", 8000))
                        codec_name = str(payload.get("codec", "unknown"))

                        # WebRTC incoming track is already resampled to WEBRTC_SAMPLE_RATE.
                        if isinstance(websocket, WebRTCHardwareLink):
                            s_rate = WEBRTC_SAMPLE_RATE
                            codec_name = "webrtc-pcm-s16le"

                        audio_monitor.set_format(
                            sample_rate=s_rate,
                            codec=codec_name,
                        )
                        stt_transcriber.set_sample_rate(s_rate)
                        device_sample_rate = s_rate

                        sco_ready = True
                        print(f"✅ [SCO READY] Device={device_id} | codec={codec_name} | rate={s_rate} | audio channel open", flush=True)

                        if pending_greeting_text:
                            queued_text = pending_greeting_text
                            queued_speaker = pending_greeting_speaker
                            pending_greeting_text = None
                            print(f"📤 [QUEUED GREETING] Ab SCO ready hai, greeting bhej rahe hain: '{queued_text[:50]}'", flush=True)
                            speak(queued_text, queued_speaker)

                    # ---------------- ESP32 status events ----------------
                    elif event_type in ["phone_bluetooth_connected", "call_incoming", "call_answered", "call_audio_started", "call_audio_stopped"]:
                        print(f"ℹ️ [ESP32 STATUS EVENT] Type={event_type} | Device={device_id}", flush=True)

                    # ---------------- call_started ----------------
                    elif event_type == "call_started":
                        call_is_active = True
                        stt_transcriber.reset()
                        reset_call_state(keep_sco_state=True)
                        if not await start_call(payload):
                            call_is_active = False

                    # ---------------- user_text ----------------
                    elif event_type == "user_text":
                        user_query = payload.get("text", "").strip()
                        if not user_query or not graph or not ctx:
                            print(f"⚠️ [USER TEXT SKIPPED] Query='{user_query}' | Graph Ready={graph is not None} | Ctx Ready={ctx is not None}", flush=True)
                            continue

                        print_user(customer_number, user_query)
                        await submit_user_turn(user_query)

                    # ---------------- call_ended ----------------
                    elif event_type == "call_ended":
                        print(f"🔴 [CALL ENDED EVENT] Device={device_id}", flush=True)
                        logger.info(f"🔴 Call Ended by Hardware | device_id={device_id}")

                        call_is_active = False
                        # Invalidate in-flight Deepgram work before any await.
                        stt_transcriber.reset()
                        await cancel_active_turn()
                        await restart_tts_workers()
                        try:
                            audio_monitor.close()
                        except Exception:
                            pass
                        audio_monitor = AudioMonitor(device_id)
                        reset_call_state(keep_sco_state=False)

                    else:
                        print(f"❓ [UNHANDLED HARDWARE EVENT] Type='{event_type}' | Device={device_id}", flush=True)
                        logger.warning(f"Unhandled hardware event: {event_type} | device_id={device_id}")

                except asyncio.CancelledError:
                    raise
                except Exception as event_err:
                    logger.error(f"❌ Error processing event '{event_type}': {event_err}", exc_info=True)
                    print(f"❌ [EVENT ERROR] {event_type}: {event_err}", flush=True)

            # ---------------- Binary audio (customer voice) ----------------
            elif raw_msg.get("bytes") is not None:
                audio_bytes = raw_msg["bytes"]


                try:
                    audio_monitor.feed(audio_bytes)
                except Exception as audio_err:
                    print(f"⚠️ [AUDIO MONITOR ERROR] {audio_err}", flush=True)

                try:
                    stt_transcriber.feed(audio_bytes, handle_live_transcription)
                except Exception as stt_err:
                    print(f"⚠️ [STT TRANSCRIBER ERROR] {stt_err}", flush=True)

    except (WebSocketDisconnect, RuntimeError) as disc_err:
        print("\n==================================================", flush=True)
        print(f"🔴 [WEBRTC DISCONNECTED] Device ID: {device_id} | reason={disc_err}", flush=True)
        print("==================================================\n", flush=True)
        logger.info(f"🔌 Hardware WebSocket Disconnected: {device_id}")
    except asyncio.CancelledError:
        logger.info(f"🔌 WebSocket handler cancelled: {device_id}")
    except Exception as exc:
        logger.error(f"❌ Error in Hardware Voice Socket: {exc}", exc_info=True)
    finally:
        call_is_active = False
        try:
            tts_gate_off_now()
        except Exception:
            pass

        try:
            await cancel_active_turn()
        except Exception:
            pass

        try:
            await stop_tts_workers()
        except Exception:
            pass

        try:
            await stt_transcriber.close()
        except Exception:
            pass

        try:
            audio_monitor.close()
        except Exception:
            pass

        try:
            await websocket.close()
        except Exception:
            pass


# ============================================================
# WEBRTC LINK  (ESP32 offer -> this backend)
# ============================================================
WEBRTC_SAMPLE_RATE = 8000
_WEBRTC_PEERS: set = set()
_DEVICE_LINKS: dict[str, "WebRTCHardwareLink"] = {}


class WebRTCPCMTrack(MediaStreamTrack):
    """Outbound PCM paced at 20 ms; timestamps survive playback cancellation."""

    kind = "audio"

    def __init__(self, sample_rate: int = WEBRTC_SAMPLE_RATE):
        super().__init__()
        if sample_rate != 8000:
            raise ValueError("This hardware transport requires 8000 Hz PCM")
        self.sample_rate = sample_rate
        self._queue: asyncio.Queue = asyncio.Queue()
        self._buffer = bytearray()
        self._pts = 0
        self._next_frame_at = None
        self._report_started = None
        self._report_frames = 0

    def clear_pending(self):
        """Discard unsent samples. Already transmitted RTP cannot be recalled."""
        dropped = len(self._buffer)
        self._buffer.clear()
        while True:
            try:
                dropped += len(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return dropped

    def stop(self):
        self.clear_pending()
        super().stop()

    async def push_pcm(self, data: bytes):
        if self.readyState != "live":
            raise MediaStreamError
        data = data[:len(data) & ~1]
        if data:
            self._queue.put_nowait(bytes(data))

    async def recv(self) -> AudioFrame:
        if self.readyState != "live":
            raise MediaStreamError
        loop = asyncio.get_running_loop()
        samples = self.sample_rate // 50
        duration = samples / self.sample_rate
        need = samples * 2
        now = loop.time()
        if self._next_frame_at is None:
            self._next_frame_at = now
        wait = self._next_frame_at - now
        if wait > 0:
            await asyncio.sleep(wait)
        if self.readyState != "live":
            raise MediaStreamError
        now = loop.time()
        # Preserve normal cadence, but never burst to catch up after a stall.
        if now - self._next_frame_at >= duration:
            self._next_frame_at = now
        self._next_frame_at += duration

        while len(self._buffer) < need:
            try:
                self._buffer.extend(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        take = min(need, len(self._buffer))
        pcm = bytes(self._buffer[:take])
        del self._buffer[:take]
        if take < need:
            pcm += b"\x00" * (need - take)

        frame = AudioFrame(format="s16", layout="mono", samples=samples)
        frame.sample_rate = self.sample_rate
        frame.planes[0].update(pcm)
        frame.pts = self._pts
        frame.time_base = Fraction(1, self.sample_rate)
        self._pts += samples

        if self._report_started is None:
            self._report_started = now
        self._report_frames += 1
        elapsed = now - self._report_started
        if elapsed >= 5.0:
            logger.info(
                "[RTC TX PACE] frames=%d elapsed=%.2fs fps=%.1f target=50",
                self._report_frames, elapsed,
                self._report_frames / elapsed,
            )
            self._report_started = now
            self._report_frames = 0
        return frame


class WebRTCHardwareLink:
    """Same send/receive shape the voice session used for the old WebSocket."""

    def __init__(self, pc, outgoing: WebRTCPCMTrack, device_id: str):
        self.pc = pc
        self.outgoing = outgoing
        self.device_id = device_id
        self.incoming: asyncio.Queue = asyncio.Queue()
        self.channel = None
        self.pending_text: list[str] = []
        self.closed = False
        self._audio_tasks: set = set()

    async def accept(self):
        return None

    def set_data_channel(self, channel):
        if self.channel is channel:
            return
        if self.channel is not None:
            logger.warning("Ignoring extra data channel: device=%s label=%s",
                           self.device_id, channel.label)
            return
        self.channel = channel

        @channel.on("open")
        def on_open():
            logger.info("WebRTC data channel open: %s", channel.label)
            self._flush_pending()

        @channel.on("close")
        def on_close():
            logger.warning("WebRTC data channel closed for device=%s", self.device_id)
            if not self.closed:
                self.incoming.put_nowait({
                    "type": "websocket.disconnect",
                    "code": 1000,
                    "reason": "WebRTC data channel closed",
                })

        if channel.readyState == "open":
            on_open()

        @channel.on("message")
        def on_message(message):
            if isinstance(message, bytes):
                logger.warning("Ignoring binary data-channel message (%d bytes)", len(message))
                return
            self.incoming.put_nowait({"text": message})


    async def feed_audio_track(self, track):
        resampler = AudioResampler(
            format="s16",
            layout="mono",
            rate=WEBRTC_SAMPLE_RATE,
        )

        frame_count = 0
        total_pcm_bytes = 0

        try:
            while not self.closed:
                frame = await track.recv()
                frames = resampler.resample(frame) or []

                if not isinstance(frames, list):
                    frames = [frames]

                for out_frame in frames:
                    pcm = bytes(out_frame.planes[0])[
                        :out_frame.samples * 2
                    ]

                    if not pcm:
                        continue

                    frame_count += 1
                    total_pcm_bytes += len(pcm)

                    self.incoming.put_nowait({"bytes": pcm})

                    if frame_count % 100 == 0:
                        logger.info(
                            "[RTC RX AUDIO] device=%s "
                            "frames=%d pcm_bytes=%d "
                            "last_frame_bytes=%d",
                            self.device_id,
                            frame_count,
                            total_pcm_bytes,
                            len(pcm),
                        )

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self.closed:
                logger.exception(
                    "WebRTC incoming audio ended: device=%s",
                    self.device_id,
                )
                self.incoming.put_nowait({
                    "type": "websocket.disconnect",
                    "code": 1000,
                    "reason": "WebRTC audio track ended",
                })


    def clear_pending_audio(self):
        dropped = self.outgoing.clear_pending()
        if dropped:
            logger.info("Discarded unsent PCM: device=%s bytes=%d",
                        self.device_id, dropped)
        return dropped

    async def receive(self):
        return await self.incoming.get()

    async def send_text(self, text: str):
        if self.closed:
            raise RuntimeError("WebRTC session is closed")
        try:
            event = json.loads(text).get("event")
        except (ValueError, AttributeError):
            event = None
        if event in ("ai_audio_cancel", "ai_audio_start"):
            self.clear_pending_audio()
        if self.channel and self.channel.readyState == "open":
            self.channel.send(text)
            return
        self.pending_text.append(text)
        if len(self.pending_text) > 256:
            self.pending_text = self.pending_text[-256:]

    async def send_bytes(self, data: bytes):
        if self.closed:
            raise RuntimeError("WebRTC session is closed")
        await self.outgoing.push_pcm(data)

    async def close(self):
        if self.closed:
            return
        self.closed = True
        for task in list(self._audio_tasks):
            task.cancel()
        self.outgoing.stop()
        try:
            self.incoming.put_nowait({
                "type": "websocket.disconnect",
                "code": 1000,
                "reason": "WebRTC link closed",
            })
        except Exception:
            pass
        if self.pc.connectionState != "closed":
            await self.pc.close()
        _WEBRTC_PEERS.discard(self.pc)
        if _DEVICE_LINKS.get(self.device_id) is self:
            _DEVICE_LINKS.pop(self.device_id, None)

    def _flush_pending(self):
        if not self.channel or self.channel.readyState != "open":
            return
        for item in self.pending_text:
            try:
                self.channel.send(item)
            except Exception:
                logger.exception("Failed to flush queued WebRTC control message")
        self.pending_text.clear()


async def _attach_outgoing_audio(pc: RTCPeerConnection, track: WebRTCPCMTrack) -> None:
    """Send AI audio on the offer's existing audio section."""
    for transceiver in pc.getTransceivers():
        if transceiver.kind != "audio":
            continue
        # The offer is sendrecv. aiortc starts the answer transceiver as recvonly
        # until we explicitly send as well.
        transceiver.direction = "sendrecv"
        result = transceiver.sender.replaceTrack(track)
        if asyncio.iscoroutine(result):
            await result
        return
    pc.addTrack(track)


def _sdp_for_esp(sdp: str, preferred_ip: str | None = None) -> str:
    """Keep the answer in the shape the ESP32 peer parser accepts.

    The board stores one SHA-256 fingerprint and a small candidate list.
    Advertise the IPv4 address it used for signaling when that candidate exists.
    """
    def build(only_ip: str | None) -> str:
        kept = []
        for line in sdp.splitlines():
            if line.startswith("a=fingerprint:") and not line.startswith("a=fingerprint:sha-256"):
                continue
            if line.startswith("a=candidate:"):
                parts = line.split()
                if len(parts) < 5 or ":" in parts[4]:
                    continue
                if only_ip and parts[4] != only_ip:
                    continue
            kept.append(line)
        text = "\r\n".join(kept)
        if text and not text.endswith("\r\n"):
            text += "\r\n"
        return text

    chosen = build(preferred_ip)
    if preferred_ip and "a=candidate:" not in chosen:
        chosen = build(None)
    return chosen


def _prefer_pcma(pc) -> None:
    try:
        capabilities = RTCRtpSender.getCapabilities("audio")
    except Exception:
        return
    preferred = [
        codec for codec in capabilities.codecs
        if str(getattr(codec, "mimeType", "")).lower() in ("audio/pcma", "audio/g711a")
        or str(getattr(codec, "name", "")).upper() == "PCMA"
    ]
    if not preferred:
        logger.warning("aiortc has no PCMA codec; the ESP32 answer may not match")
        return
    for transceiver in pc.getTransceivers():
        if transceiver.kind != "audio":
            continue
        try:
            transceiver.setCodecPreferences(preferred)
        except Exception:
            logger.exception("Could not pin the audio answer to PCMA")


@router.post("/webrtc/offer/{device_id}")
async def hardware_voice_webrtc_offer(request: Request, device_id: str):
    """
    ESP32 signaling endpoint.

    POST {"type": "offer", "sdp": "<offer SDP>"}
    Returns {"type": "answer", "sdp": "<answer SDP>"}
    """
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Request body must be JSON") from exc

    if body.get("type") != "offer" or not isinstance(body.get("sdp"), str):
        raise HTTPException(
            status_code=400,
            detail='Expected JSON {"type": "offer", "sdp": "..."}',
        )

    offer_sdp = body["sdp"]
    log_sdp_transport("OFFER", offer_sdp)
    if "m=audio" not in offer_sdp:
        raise HTTPException(status_code=400, detail="SDP offer has no audio section")
    if "m=application" not in offer_sdp:
        raise HTTPException(
            status_code=400,
            detail="SDP offer has no data channel (m=application)",
        )

    pc = RTCPeerConnection()
    _WEBRTC_PEERS.add(pc)
    outgoing = WebRTCPCMTrack(WEBRTC_SAMPLE_RATE)
    link = WebRTCHardwareLink(pc, outgoing, device_id)
    previous = _DEVICE_LINKS.pop(device_id, None)
    if previous is not None:
        logger.info("Replacing the existing WebRTC session for device=%s", device_id)
        await previous.close()
    _DEVICE_LINKS[device_id] = link

    @pc.on("datachannel")
    def on_datachannel(channel):
        logger.info("WebRTC data channel received: %s", channel.label)
        link.set_data_channel(channel)

    @pc.on("track")
    def on_track(track):
        logger.info("WebRTC track received: device=%s kind=%s", device_id, track.kind)
        if track.kind == "audio":
            task = asyncio.create_task(link.feed_audio_track(track))
            link._audio_tasks.add(task)
            task.add_done_callback(link._audio_tasks.discard)

    @pc.on("connectionstatechange")
    def on_connectionstatechange():
        logger.info("WebRTC peer state: device=%s state=%s", device_id, pc.connectionState)
        if pc.connectionState in ("failed", "closed"):
            asyncio.create_task(link.close())

    try:
        await pc.setRemoteDescription(RTCSessionDescription(sdp=offer_sdp, type="offer"))
 

        control_channel = pc.createDataChannel(
            "control",
            ordered=True,
        )
        link.set_data_channel(control_channel)

        logger.info(
            "WebRTC control channel created locally: device=%s",
            device_id,
        )

        await _attach_outgoing_audio(pc, outgoing)
        _prefer_pcma(pc)

        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        deadline = time.monotonic() + 8.0
        while pc.iceGatheringState != "complete" and time.monotonic() < deadline:
            await asyncio.sleep(0.05)

        signaled_host = (request.headers.get("host") or "").split(":")[0].strip("[]")
        answer_sdp = _sdp_for_esp(
            pc.localDescription.sdp if pc.localDescription else "",
            signaled_host or None,
        )
        log_sdp_transport("ANSWER", answer_sdp)
        if "a=candidate:" not in answer_sdp:
            raise RuntimeError("Answer SDP has no ICE candidates")
        if "a=sendrecv" not in answer_sdp:
            raise RuntimeError("Answer SDP is not sendrecv")
        if "PCMA" not in answer_sdp and "pcma" not in answer_sdp:
            logger.warning("Answer SDP has no PCMA codec; the ESP32 expects G.711 A-law")
        logger.info(
            "WebRTC answer ready: device=%s bytes=%d ice=%s",
            device_id, len(answer_sdp), pc.iceGatheringState,
        )

        session = asyncio.create_task(hardware_voice_websocket(link, device_id))

        def _session_done(task):
            _WEBRTC_PEERS.discard(pc)
            if task.cancelled():
                return
            exc = task.exception()
            if exc is not None:
                logger.error(
                    "WebRTC voice session crashed: device=%s error=%s",
                    device_id, exc, exc_info=exc,
                )
                asyncio.create_task(link.close())

        session.add_done_callback(_session_done)
        return {"type": pc.localDescription.type, "sdp": answer_sdp}
    except HTTPException:
        _WEBRTC_PEERS.discard(pc)
        await link.close()
        raise
    except Exception as exc:
        _WEBRTC_PEERS.discard(pc)
        await link.close()
        logger.exception("WebRTC negotiation failed for device=%s", device_id)
        raise HTTPException(status_code=500, detail="WebRTC negotiation failed") from exc


async def close_hardware_webrtc_peers():
    peers = list(_WEBRTC_PEERS)
    if peers:
        await asyncio.gather(*(pc.close() for pc in peers), return_exceptions=True)
    _WEBRTC_PEERS.clear()