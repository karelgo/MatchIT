"""AI Concierge intake: natural language -> structured assignment."""

from app.ai.llm import ChatModel
from app.ai.prompts import INTAKE_SYSTEM_PROMPT
from app.ai.schemas import AssignmentRequirements


class IntakeService:
    def __init__(self, chat_model: ChatModel):
        self._chat = chat_model

    async def extract(self, description: str) -> AssignmentRequirements:
        """Extract structured requirements from a company's problem statement.

        `description` may span multiple concierge turns (original statement plus
        answers to clarifying questions, concatenated by the caller).
        """
        return await self._chat.complete_structured(
            system=INTAKE_SYSTEM_PROMPT,
            user=description.strip(),
            schema=AssignmentRequirements,
        )
