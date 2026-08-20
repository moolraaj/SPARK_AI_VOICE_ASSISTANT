from langchain_openai import ChatOpenAI

from app.core.config import MODEL_NAME
from app.ai.tools.tool_mapping import TOOL_REGISTRY


class LLMToolCaller:

    def __init__(self):

        self.llm = ChatOpenAI(
            model=MODEL_NAME,
            temperature=0.2,
        )

    def get_llm(
        self,
        business_type: str,
    ):

        business_type = business_type.upper().strip()

        tools = TOOL_REGISTRY.get(business_type)

        if not tools:
            raise ValueError(
                f"No tools available for business type: "
                f"{business_type}"
            )

        return self.llm.bind_tools(tools)