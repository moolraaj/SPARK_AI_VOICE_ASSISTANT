from enum import Enum

class CommonIntent(str, Enum):

    GREETING_CIVILITY = "GREETING_CIVILITY"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


COMMON_INTENTS = {
    "GREETING_CIVILITY": {
        "description": (
            "Customer is greeting the AI employee, expressing courtesy, "
            "thanking the assistant, or saying goodbye."
        ),
        "examples": [
            "Hello",
            "Good morning",
            "Hello sir, kaise ho?",
            "Namaste",
            "Thank you",
            "Thanks",
            "Bye"
        ],
        "entities": []
    },

    "OUT_OF_SCOPE": {
        "description": (
            "Customer request is unrelated to the services supported "
            "by the current business."
        ),
        "examples": [
            "Tell me about Bitcoin.",
            "What's the capital of France?"
        ],
        "entities": []
    }
}