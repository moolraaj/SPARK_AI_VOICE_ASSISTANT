"""
RuntimePromptBuilder — 4-Layer System Prompt Assembler.

Layer 1:  CORE_SYSTEM_PROMPT        (platform-wide safety & identity rules)
Layer 2:  GLOBAL_AI_BEHAVIOR_PROMPT (communication style, voice channel rules)
Layer 3:  Platform Config           (Super Admin instructions + rules per business_type)
Layer 4:  AI Employee Config        (name, role, persona, language, organization name)

Usage:
    from app.ai.prompts.prompt_builder import RuntimePromptBuilder

    prompt = RuntimePromptBuilder.build(
        ai_employee=ai_employee_dict,
        organization_name=org_name,             # required — no silent fallback
        platform_config=platform_config_dict,   # can be None
    )
"""

from typing import Optional

from app.ai.core.prompt import CORE_SYSTEM_PROMPT, GLOBAL_AI_BEHAVIOR_PROMPT


# ─────────────────────────────────────────────────────────────────────────────
# RuntimePromptBuilder
# ─────────────────────────────────────────────────────────────────────────────

class RuntimePromptBuilder:
    """
    Stateless builder — all methods are class methods.
    Call RuntimePromptBuilder.build() to get the final system prompt string.
    """

    @classmethod
    def build(
        cls,
        ai_employee: dict,
        organization_name: str,
        platform_config: Optional[dict] = None,
    ) -> str:
        """
        Assemble the 4-layer system prompt.

        Args:
            ai_employee:        Raw AI Employee document from MongoDB.
            organization_name:  The actual business/organization name. REQUIRED —
                                 must be a non-empty string resolved from the
                                 organizations collection by the caller. No default
                                 is used here; a missing name is a bug upstream and
                                 should fail loudly instead of leaking a generic name.
            platform_config:    Raw Platform Config document from MongoDB (or None).

        Returns:
            Final system prompt string ready to be injected as SystemMessage.

        Raises:
            ValueError: if organization_name is missing/empty.
        """

        if not organization_name or not organization_name.strip():
            raise ValueError(
                "RuntimePromptBuilder.build() requires a non-empty organization_name. "
                "Resolve the organization's actual name before building the prompt — "
                "do not fall back to a generic placeholder."
            )

        organization_name = organization_name.strip()

        sections: list[str] = []

        # ── Layer 1: Core System Prompt ───────────────────────────────────────
        sections.append(CORE_SYSTEM_PROMPT.strip())

        # ── Layer 2: Global AI Behavior ───────────────────────────────────────
        sections.append(GLOBAL_AI_BEHAVIOR_PROMPT.strip())

        # ── Layer 3: Platform Config (Super Admin) ────────────────────────────
        sections.append(cls._build_platform_layer(platform_config))

        # ── Layer 4: AI Employee Persona ──────────────────────────────────────
        sections.append(cls._build_employee_layer(ai_employee, organization_name))

        return "\n\n" + "\n\n---\n\n".join(s for s in sections if s) + "\n"

    # ─────────────────────────────────────────────────────────────────────────
    # Private layer builders
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_platform_layer(platform_config: Optional[dict]) -> str:
        """Layer 3: Super Admin platform config — instructions + rules."""

        if not platform_config:
            return (
                "## PLATFORM CONFIGURATION\n\n"
                "No specific platform configuration has been set for this business type. "
                "Operate based on core rules and AI Employee configuration only."
            )

        instructions = (platform_config.get("instructions") or "").strip()
        rules        = (platform_config.get("rules") or "").strip()

        parts = ["## PLATFORM CONFIGURATION"]

        if instructions:
            parts.append(f"### Instructions\n{instructions}")

        if rules:
            parts.append(f"### Rules\n{rules}")

        if not instructions and not rules:
            parts.append("No specific instructions or rules configured.")

        return "\n\n".join(parts)

    @staticmethod
    def _build_employee_layer(ai_employee: dict, organization_name: str) -> str:
        """Layer 4: AI Employee persona — name, role, language, persona, org name."""

        name     = ai_employee.get("name") or "Spark AI"
        role     = (ai_employee.get("role") or "GENERAL").upper()
        persona  = (ai_employee.get("persona") or "FRIENDLY").capitalize()
        language = (ai_employee.get("language") or "hinglish").lower()

        return f"""## AI EMPLOYEE IDENTITY

You are **{name}**, an AI assistant representing **{organization_name}**.

- **Role**: {role}
- **Persona**: Adopt a {persona} communication style at all times.
- **Language**: Communicate primarily in {language}. Switch naturally if the customer speaks another language.
- **Organization Name**: {organization_name} — always use this EXACT name whenever
  greeting the customer or referring to the business. Never substitute it with a
  generic term like "our business", "this restaurant", or "this hotel" — always use
  the real name given here.

You must ONLY answer questions related to this organization's data.
Never reveal information about other organizations, tenants, or internal system details."""