"""AI Concierge intake: natural language -> structured assignment.

The intake is conversational: the first extraction returns clarifying questions,
the company answers, and re-extraction runs over the accumulated transcript until
the assignment converges.
"""

from app.ai.llm import ChatModel
from app.ai.prompts import INTAKE_SYSTEM_PROMPT
from app.ai.schemas import AssignmentRequirements

COMPANY_ROLE = "company"
CONCIERGE_ROLE = "concierge"

_SPEAKER_LABELS = {COMPANY_ROLE: "Company", CONCIERGE_ROLE: "Concierge"}


def build_transcript(history: list[dict]) -> str:
    """Render the intake dialogue as the prompt input.

    Each entry is {"role": "company"|"concierge", "content": str}; unknown roles
    are rejected loudly rather than silently mislabelled in the prompt.
    """
    lines = []
    for message in history:
        label = _SPEAKER_LABELS.get(message["role"])
        if label is None:
            raise ValueError(f"unknown intake role: {message['role']!r}")
        lines.append(f"{label}: {message['content'].strip()}")
    return "\n\n".join(lines)


class IntakeService:
    def __init__(self, chat_model: ChatModel):
        self._chat = chat_model

    async def extract(self, description: str) -> AssignmentRequirements:
        """Extract structured requirements from the company's first statement."""
        return await self._chat.complete_structured(
            system=INTAKE_SYSTEM_PROMPT,
            user=description.strip(),
            schema=AssignmentRequirements,
        )

    async def refine(self, history: list[dict]) -> AssignmentRequirements:
        """Re-extract over the full intake conversation."""
        return await self._chat.complete_structured(
            system=INTAKE_SYSTEM_PROMPT,
            user=build_transcript(history),
            schema=AssignmentRequirements,
        )
