"""
Hardware Voice WebSocket Router - v4 (DEBUG + CONVERSATION LOGS).

Changes vs v3:
  1. logging.basicConfig(INFO) -> Sarvam / STT logger.info lines ab terminal me dikhengi.
  2. Terminal par clean conversation print:  👤 USER: ...  /  🤖 AI: ...
  3. extract_text(): LLM chunk content str ya list dono handle.
  4. Fallback: agar stream se text nahi mila to graph state se final AI reply utha ke bolta hai.
  5. Har turn ke liye alag thread_id (checkpoint corrupt / duplicate history problem khatam).
  6. Bahut chhote transcripts (<3 chars) ignore (noise "hmm" se barge-in nahi hoga).
  7. Device credit / playback IDs replace estimated TTS pacing.
  8. DEBUG_EVENTS=1 env se graph events print kar sakte ho.
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

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.ai.context.session_context_resolver import SessionContextResolver
from app.ai.prompts.prompt_builder import RuntimePromptBuilder
from app.ai.graph.graph import SparkAgentGraph
from app.modules.conversations.conversation_repository import ConversationRepository
from app.modules.organizations.organization_repository import OrganizationRepository
from app.database.mongodb import mongodb
from app.voice.telephony.sarvam_stt import SpeechTranscriber, synthesize_tts_pcm

# Logger ko INFO pe laao, warna [SARVAM TTS] / [SPEECH RECOGNITION] lines dikhti hi nahi
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

router = APIRouter(tags=["Hardware Voice WebSocket"])

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
    print(f"\n👤 USER ({number}): {text}", flush=True)


def print_ai(name: str, text: str):
    print(f"🤖 AI   ({name}): {text}\n", flush=True)


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
    """Single-stream PCM sender with device credit and correlated completion.

    'played' means consumed by the ESP32 SCO callback, not acoustic confirmation.
    Requires the hardware.ino supplied with this bundle.
    """

    def __init__(self, websocket: WebSocket, device_id: str):
        self.ws = websocket
        self.device_id = device_id
        self.serial = 0
        self.active_id = None
        self.busy = False
        self.sent = 0
        self.played = 0
        self.capacity = 0
        self.rate = 8000
        self.updated = asyncio.Event()
        self.done = asyncio.Event()
        self.completion = None

    def reset(self):
        self.active_id = None
        self.busy = False
        self.sent = self.played = self.capacity = 0
        self.completion = None
        self.updated.set()

    def seconds_ahead(self) -> float:
        return max(0, self.sent - self.played) / (self.rate * 2)

    def on_device_event(self, payload: dict):
        try:
            stream_id = int(payload.get("playback_id", -1))
            played = int(payload.get("played", 0))
            received = int(payload.get("received", 0))
        except (TypeError, ValueError):
            return
        if stream_id != self.active_id or not self.busy:
            return
        if not (0 <= played <= received <= self.sent):
            return
        self.played = max(self.played, played)
        if payload.get("event") == "ai_audio_buffer":
            try:
                capacity = int(payload.get("capacity", 0))
            except (TypeError, ValueError):
                return
            if capacity < 2 * TTS_SEND_CHUNK:
                return
            self.capacity = capacity
        elif payload.get("event") == "ai_audio_played":
            self.completion = payload
            self.done.set()
        self.updated.set()

    async def _wait_for_update(self):
        await asyncio.wait_for(self.updated.wait(), TTS_FEEDBACK_TIMEOUT_SEC)

    async def send(self, pcm: bytes, rate: int, text: str = "") -> bool:
        pcm = pcm[:len(pcm) & ~1]
        if not pcm:
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
        try:
            await self.ws.send_text(json.dumps({
                "event": "ai_audio_start", "playback_id": stream_id,
                "sample_rate": rate, "total_bytes": len(pcm),
            }))
            while not self.capacity:
                self.updated.clear()
                if self.done.is_set():
                    raise RuntimeError("Hardware rejected playback start")
                await self._wait_for_update()

            # Reserve two packet slots; all in-flight bytes count against credit.
            window = min(self.capacity - 2 * TTS_SEND_CHUNK,
                         int(rate * 2 * TTS_BUFFER_TARGET_SEC)) & ~1
            if window < TTS_SEND_CHUNK:
                raise RuntimeError("Hardware buffer is too small")
            for offset in range(0, len(pcm), TTS_SEND_CHUNK):
                chunk = pcm[offset:offset + TTS_SEND_CHUNK]
                while self.sent - self.played + len(chunk) > window:
                    self.updated.clear()
                    if self.done.is_set():
                        raise RuntimeError("Hardware aborted PCM stream")
                    await self._wait_for_update()
                if self.done.is_set():
                    raise RuntimeError("Hardware completed before all PCM was sent")
                # Record before await: an acknowledgement can arrive during send.
                self.sent += len(chunk)
                await self.ws.send_bytes(chunk)

            await self.ws.send_text(json.dumps({
                "event": "ai_audio_end", "playback_id": stream_id,
            }))
            await asyncio.wait_for(self.done.wait(), TTS_COMPLETION_TIMEOUT_SEC)
            result = self.completion or {}
            if (result.get("ok") is not True or
                    int(result.get("played", -1)) != len(pcm) or
                    int(result.get("received", -1)) != len(pcm) or
                    int(result.get("dropped", -1)) != 0):
                raise RuntimeError(f"Incomplete hardware playback: {result}")
            logger.info("TTS PLAYED device=%s id=%s bytes=%s elapsed=%.2fs text=%r",
                        self.device_id, stream_id, len(pcm),
                        time.monotonic() - started, text[:60])
            return True
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("TTS playback failed: device=%s id=%s sent=%s played=%s",
                             self.device_id, stream_id, self.sent, self.played)
            try:
                await asyncio.wait_for(self.ws.send_text(json.dumps({
                    "event": "ai_audio_cancel", "playback_id": stream_id,
                    "reason": "playback feedback failure",
                })), timeout=2.0)
            except Exception:
                pass
            return False
        finally:
            if self.active_id == stream_id:
                self.busy = False
                self.active_id = None


@router.websocket("/ws/voice/{device_id}")
async def hardware_voice_websocket(websocket: WebSocket, device_id: str):
    """Direct WebSocket connection for physical hardware devices."""
    await websocket.accept()
    print("\n==================================================", flush=True)
    print(f"🔌 [WEBSOCKET CONNECTED] Device ID: {device_id}", flush=True)
    print("==================================================\n", flush=True)
    logger.info(f"🔌 Hardware WebSocket connected | device_id={device_id}")

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
            try:
                if generation != tts_generation:
                    continue

                t0 = time.monotonic()
                pcm = await synthesize_tts_pcm(text, sample_rate=rate, speaker=speaker)

                if generation != tts_generation:
                    print(f"🗑️ [TTS STALE] Dropping synthesized audio | gen={generation} current={tts_generation}", flush=True)
                    continue

                if pcm:
                    print(f"⏱️ [TTS SYNTH] {(time.monotonic() - t0) * 1000:.0f} ms | gen={generation} | '{text[:40]}'", flush=True)
                    await pcm_queue.put((pcm, rate, text, generation))
                else:
                    print(f"⚠️ [TTS] Empty/failed audio for device={device_id} | speaker={speaker} | '{text[:40]}'", flush=True)
            except asyncio.CancelledError:
                raise
            except Exception as tts_err:
                logger.error(f"TTS synth worker error: {tts_err}", exc_info=True)
            finally:
                try:
                    tts_queue.task_done()
                except Exception:
                    pass

    async def play_worker():
        nonlocal tts_generation
        while True:
            pcm, rate, text, generation = await pcm_queue.get()
            try:
                if generation != tts_generation:
                    continue
                tts_gate_on()
                sent_ok = await pacer.send(pcm, rate, text)
                if not sent_ok and generation == tts_generation:
                    # Invalidate also the sentence currently being synthesized.
                    tts_generation += 1
                    clear_tts_queue()
                if generation == tts_generation and not pcm_queue.empty():
                    # Keep the gate closed across ready consecutive sentences.
                    pass
                else:
                    tts_gate_off_now()
            except asyncio.CancelledError:
                raise
            except Exception:
                tts_gate_off_now()
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

    def _drain(q: asyncio.Queue):
        while not q.empty():
            try:
                q.get_nowait()
                q.task_done()
            except (asyncio.QueueEmpty, ValueError):
                break

    def clear_tts_queue():
        _drain(tts_queue)
        _drain(pcm_queue)

    async def cancel_tts_playback(reason: str = "new user speech"):
        nonlocal tts_generation
        tts_generation += 1
        generation = tts_generation
        tts_gate_off_now()

        print(f"🛑 [TTS CANCEL] device={device_id} gen={generation} reason={reason}", flush=True)

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
        pacer.reset()
        start_tts_workers()

    async def restart_tts_workers():
        await cancel_tts_playback(reason="call reset")

    start_tts_workers()

    def speak(text: str, speaker: str):
        text = (text or "").strip()
        if not text:
            return
        tts_queue.put_nowait(
            (text, speaker, device_sample_rate, tts_generation)
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
                if DEBUG_EVENTS:
                    print(f"[DEVICE EVENT TYPE] {event_type}", flush=True)

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
                        audio_monitor.set_format(sample_rate=s_rate, codec=codec_name)
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
        print(f"🔴 [WEBSOCKET DISCONNECTED] Device ID: {device_id} | reason={disc_err}", flush=True)
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