"""
SparkVoiceAgent — Dynamic, multi-tenant voice agent.

- business_type ke basis par SparkAgentGraph dynamically build hota hai.
- RestaurantVoiceAgent sirf backward-compat alias hai.
"""

import logging
import re
import time

from livekit.agents import Agent

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.ai.graph.graph import SparkAgentGraph


logger = logging.getLogger("global-voice-agent")

# Sentence-boundary detector — end mark ke turant baad TTS ko chunk bhejne ke liye.
# Hindi/Urdu "।" bhi cover kiya hai.
_SENTENCE_END_RE = re.compile(r"[.!?।]\s*$")


class SparkVoiceAgent(Agent):
    """
    Dynamic Voice agent — Deepgram STT → LangGraph (streamed) → Sarvam TTS.

    - business_type se SparkAgentGraph build hota hai (RESTAURANT, HOTEL, etc.)
    - org_name RuntimePromptBuilder ko pass hota hai taaki correct org name show ho.

    IMPORTANT: LLM tokens ko astream_events se stream karke, sentence-boundary
    par turant TTS ko bhej diya jaata hai. Poore graph output ka wait NAHI
    kiya jaata — isse audio pehle sentence ke baad hi shuru ho jaata hai,
    instead of poora reply generate hone tak silence.

    NOTE (FIXED): LangGraph ka MemorySaver checkpointer already thread_id
    ke against poori conversation history maintain karta hai. Isliye har
    call pe humein sirf NAYA message bhejna hai — poori history dobara
    bhejna checkpoint ke saath merge/duplicate ho jaata hai aur context
    turn-by-turn balloon karta hai, jisse latency badhti jaati hai.
    """

    def __init__(
        self,
        owner_id: str,
        ai_employee_id: str,
        employee_data: dict,
        session_id: str,
        org_name: str = "",
    ) -> None:

        system_prompt = employee_data.get("greeting_message") or f"Namaste! Main {employee_data.get('name', 'Spark AI')} bol raha hoon."
        super().__init__(instructions=system_prompt)

        # Dynamically build graph based on business_type from employee_data
        business_type = (employee_data.get("business_type") or "RESTAURANT").upper().strip()

        self._graph      = SparkAgentGraph(business_type=business_type).build()
        self._owner_id   = owner_id
        self._emp_id     = ai_employee_id
        self._emp_data   = employee_data
        self._session_id = session_id
        self._org_name   = org_name
        self._business_type = business_type

        # NOTE: Ab yeh sirf LOGGING/debugging ke liye hai.
        self._local_history = [SystemMessage(content=system_prompt)]

        logger.info(
            "SparkVoiceAgent ready | session=%s | employee=%s | business_type=%s | org=%s",
            session_id, ai_employee_id, business_type, org_name,
        )

    # ── Greet customer when call connects ────────────────────────────────────
    async def on_enter(self) -> None:
        greeting = (self._emp_data.get("greeting_message") or "").strip()
        if greeting:
            # Direct TTS — no LLM call needed.
            # This saves ~500-800ms on the very first turn of every call.
            self.session.say(greeting, add_to_chat_ctx=False)
            logger.info("Greeting spoken (direct): %s", greeting[:80])
        else:
            # Fallback: LLM generates the greeting from persona context.
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
        self._local_history.append(start_message)

        buffer = ""
        spoke_anything = False
        full_parts: list[str] = []

        try:
            async for event in self._graph.astream_events(
                {
                    "messages":       [start_message],
                    "owner_id":       self._owner_id,
                    "business_type":  self._business_type,
                    "ai_employee_id": self._emp_id,
                    "ai_employee":    self._emp_data,
                    "org_name":       self._org_name,
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

            # Local history sirf logging ke liye update ho rahi hai
            self._local_history.append(AIMessage(content=greeting_text))
            logger.info("Greeting spoken: %s", greeting_text[:80])

        except Exception as exc:
            logger.error("Greeting error: %s", exc)
            fallback = (
                self._emp_data.get("greeting_message", "")
                or "Namaste! Aapki call aa gayi hai. Kya main aapki madad kar sakta hoon?"
            )
            self.session.say(fallback, add_to_chat_ctx=False)

    # ── Called every time customer finishes speaking ─────────────────────────
    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        """
        LiveKit 1.6.x SDK signature:
            turn_ctx   : llm.ChatContext
            new_message: llm.ChatMessage   ← user ka transcribed text

        user_text = new_message.text_content  ← correct way
        """
        user_text: str = (new_message.text_content or "").strip()

        if not user_text:
            return

        logger.info("Customer said: %s", user_text)

        new_user_message = HumanMessage(content=user_text)
        self._local_history.append(new_user_message)

        turn_start = time.perf_counter()
        first_chunk_time = None
        full_reply_parts: list[str] = []
        buffer = ""
        spoke_anything = False

        try:
            async for event in self._graph.astream_events(
                {
                    "messages":       [new_user_message],
                    "owner_id":       self._owner_id,
                    "business_type":  self._business_type,
                    "ai_employee_id": self._emp_id,
                    "ai_employee":    self._emp_data,
                    "org_name":       self._org_name,
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
                # tracking me useful.
                elif kind == "on_tool_start":
                    logger.info(
                        "Tool call started: %s | args=%s",
                        event.get("name"), event.get("data", {}).get("input"),
                    )

            # Bache hue buffer ko bhi bolna zaroori hai.
            if buffer.strip():
                self.session.say(buffer.strip(), add_to_chat_ctx=False)
                spoke_anything = True

            full_reply = "".join(full_reply_parts).strip()

            if not full_reply:
                full_reply = "Maafi chahta hoon, kuch samajh nahi aaya. Dobara bolein please."
                if not spoke_anything:
                    self.session.say(full_reply, add_to_chat_ctx=False)

            self._local_history.append(AIMessage(content=full_reply))

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


# ── Backward-compatibility alias ─────────────────────────────────────────────
RestaurantVoiceAgent = SparkVoiceAgent