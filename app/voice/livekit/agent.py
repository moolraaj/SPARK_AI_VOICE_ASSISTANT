import logging
import re
import time

from livekit.agents import Agent

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.ai.graph.graph import RestaurantAgentGraph
from app.ai.prompts.restaurant_prompt import build_system_prompt


logger = logging.getLogger("restaurant-voice-agent")

# Sentence-boundary detector — end mark ke turant baad TTS ko chunk bhejne ke liye.
# Hindi/Urdu "।" bhi cover kiya hai.
_SENTENCE_END_RE = re.compile(r"[.!?।]\s*$")


class RestaurantVoiceAgent(Agent):
    """
    Voice agent — Deepgram STT → LangGraph (streamed) → Sarvam TTS.

    IMPORTANT: LLM tokens ko astream_events se stream karke, sentence-boundary
    par turant TTS ko bhej diya jaata hai. Poore graph output ka wait NAHI
    kiya jaata — isse audio pehle sentence ke baad hi shuru ho jaata hai,
    instead of poora reply generate hone tak silence.
    """

    def __init__(
        self,
        owner_id: str,
        ai_employee_id: str,
        employee_data: dict,
        session_id: str,
    ) -> None:

        system_prompt = build_system_prompt(employee_data)
        super().__init__(instructions=system_prompt)

        # Build LangGraph once per call
        self._graph      = RestaurantAgentGraph().build()
        self._owner_id   = owner_id
        self._emp_id     = ai_employee_id
        self._emp_data   = employee_data
        self._session_id = session_id
        self._messages   = [SystemMessage(content=system_prompt)]

        logger.info(
            "RestaurantVoiceAgent ready | session=%s | employee=%s",
            session_id, ai_employee_id,
        )

    # ── Greet customer when call connects — LLM generates the greeting ────────
    async def on_enter(self) -> None:
        await self._greet_via_llm()

    async def _greet_via_llm(self) -> None:
        """
        Jaise hi call pick hoti hai, LangGraph ko ek special call-start
        message bhejte hain. LLM employee ke persona ke hisaab se
        greeting generate karta hai — hardcoded text nahi.
        """
        logger.info("Call connected — generating LLM greeting | session=%s", self._session_id)

        # Special marker: LangGraph ko batata hai ki call abhi shuru hui hai
        start_message = HumanMessage(content="[CALL_START] Greet the customer naturally.")
        self._messages.append(start_message)

        buffer = ""
        spoke_anything = False
        full_parts: list[str] = []

        try:
            async for event in self._graph.astream_events(
                {
                    "messages":       self._messages,
                    "owner_id":       self._owner_id,
                    "business_type":  self._emp_data.get("business_type", "RESTAURANT"),
                    "ai_employee_id": self._emp_id,
                    "ai_employee":    self._emp_data,
                },
                config={"configurable": {"thread_id": self._session_id}},
                version="v2",
            ):
                if event.get("event") == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    content = getattr(chunk, "content", "")

                    if isinstance(content, str) and content:
                        buffer += content
                        full_parts.append(content)

                        if _SENTENCE_END_RE.search(buffer) and len(buffer.strip()) > 1:
                            self.session.say(buffer.strip(), add_to_chat_ctx=False)
                            spoke_anything = True
                            buffer = ""

            if buffer.strip():
                self.session.say(buffer.strip(), add_to_chat_ctx=False)
                spoke_anything = True

            greeting_text = "".join(full_parts).strip()

            if not greeting_text:
                # Fallback if LLM returned nothing
                greeting_text = (
                    self._emp_data.get("greeting_message", "")
                    or f"Namaste! Main {self._emp_data.get('name', 'AI Assistant')} bol raha hoon. Kya main aapki madad kar sakta hoon?"
                )
                if not spoke_anything:
                    self.session.say(greeting_text, add_to_chat_ctx=False)

            # Add AI greeting to history so conversation context is maintained
            self._messages.append(AIMessage(content=greeting_text))
            logger.info("Greeting spoken: %s", greeting_text[:80])

        except Exception as exc:
            logger.error("Greeting error: %s", exc)
            fallback = (
                self._emp_data.get("greeting_message", "")
                or "Namaste! Aapki call aa gayi hai. Kya main aapki madad kar sakta hoon?"
            )
            self.session.say(fallback, add_to_chat_ctx=False)

    # ── Called every time customer finishes speaking ─────────────────────────
    # NOTE: correct LiveKit Agents hook name is `on_user_turn_completed`,
    # not `on_user_turn`. Confirm your installed `livekit-agents` version
    # (`pip show livekit-agents`) matches this signature — if the SDK
    # expects (chat_ctx, new_message) instead, adjust the params below
    # to match, but keep the streaming body as-is.
    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        """
        LiveKit 1.6.x SDK signature:
            turn_ctx   : llm.ChatContext
            new_message: llm.ChatMessage   ← user ka transcribed text

        user_text = new_message.text_content  ← correct way
        (NOT getattr(ev, 'transcript') — ChatMessage me ye attribute nahi hota)
        """
        user_text: str = (new_message.text_content or "").strip()

        if not user_text:
            return

        logger.info("Customer said: %s", user_text)

        self._messages.append(HumanMessage(content=user_text))

        turn_start = time.perf_counter()
        first_chunk_time = None
        full_reply_parts: list[str] = []
        buffer = ""
        spoke_anything = False

        try:
            async for event in self._graph.astream_events(
                {
                    "messages":       self._messages,
                    "owner_id":       self._owner_id,
                    "business_type":  self._emp_data.get("business_type", "RESTAURANT"),
                    "ai_employee_id": self._emp_id,
                    "ai_employee":    self._emp_data,
                },
                config={"configurable": {"thread_id": self._session_id}},
                version="v2",
            ):
                kind = event.get("event")

                # ── Stream LLM tokens as they arrive ────────────────────
                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    content = getattr(chunk, "content", "")

                    if isinstance(content, str) and content:
                        if first_chunk_time is None:
                            first_chunk_time = time.perf_counter()

                        buffer += content
                        full_reply_parts.append(content)

                        # Sentence complete → turant TTS ko bhejo, poore
                        # response ka wait mat karo.
                        if _SENTENCE_END_RE.search(buffer) and len(buffer.strip()) > 1:
                            self.session.say(buffer.strip(), add_to_chat_ctx=False)
                            spoke_anything = True
                            buffer = ""

                # Tool call chal raha hai — reasoning ke liye, latency
                # tracking me useful (logs se dikh jaayega tool round-trip
                # kitna time le raha hai).
                elif kind == "on_tool_start":
                    logger.info(
                        "Tool call started: %s | args=%s",
                        event.get("name"), event.get("data", {}).get("input"),
                    )

            # Bache hue buffer (agar last chunk sentence-end pe khatam
            # nahi hua) ko bhi bolna zaroori hai.
            if buffer.strip():
                self.session.say(buffer.strip(), add_to_chat_ctx=False)
                spoke_anything = True

            full_reply = "".join(full_reply_parts).strip()

            if not full_reply:
                full_reply = "Maafi chahta hoon, kuch samajh nahi aaya. Dobara bolein please."
                if not spoke_anything:
                    self.session.say(full_reply, add_to_chat_ctx=False)

            self._messages.append(AIMessage(content=full_reply))

            total_ms = (time.perf_counter() - turn_start) * 1000
            ttft_ms = (
                (first_chunk_time - turn_start) * 1000
                if first_chunk_time else total_ms
            )
            logger.info(
                "Turn done | TTFT=%.0fms | total=%.0fms | reply=%s",
                ttft_ms, total_ms, full_reply[:80],
            )

        except Exception as exc:
            logger.error("LangGraph error: %s", exc)
            self.session.say(
                "Maafi, abhi kuch technical problem hai. Thodi der baad try karein.",
                add_to_chat_ctx=False,
            )