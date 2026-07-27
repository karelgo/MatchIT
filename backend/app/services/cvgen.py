"""AI-generated CV from the evidence-backed skill graph.

The model writes the structured content; the document itself is rendered here,
deterministically — layout is not something to re-roll a model for.
"""

import json

from app.ai.llm import ChatModel
from app.ai.prompts import CV_GENERATOR_SYSTEM_PROMPT
from app.ai.schemas import GeneratedCV
from app.models import SpecialistProfile, User


def _cv_payload(user: User, profile: SpecialistProfile) -> dict:
    """The profile as the CV writer sees it.

    The specialist's own name belongs on their own CV, so unlike the interviewer
    projection this includes it. Rate does not — a CV is not a price list.
    """
    return {
        "name": user.full_name,
        "headline": profile.headline,
        "bio": profile.bio,
        "years_experience": profile.years_experience,
        "skills": [
            {
                "name": s["name"],
                "level": s.get("level"),
                "years": s.get("years"),
                "source": s.get("source", "self_reported"),
                "evidence": s.get("evidence"),
            }
            for s in profile.skills
        ],
        "certifications": profile.certifications,
        "languages": profile.languages,
        "links": {
            "github": profile.github_url,
            "linkedin": profile.linkedin_url,
            "website": profile.website_url,
        },
    }


def render_markdown(name: str, cv: GeneratedCV) -> str:
    lines = [f"# {name}", "", f"**{cv.headline}**", "", cv.summary, ""]
    for section in cv.sections:
        lines.append(f"## {section.heading}")
        lines.append("")
        lines.extend(f"- {bullet}" for bullet in section.bullets)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


class CVGeneratorService:
    def __init__(self, chat_model: ChatModel):
        self._chat = chat_model

    async def generate(self, user: User, profile: SpecialistProfile) -> GeneratedCV:
        return await self._chat.complete_structured(
            system=CV_GENERATOR_SYSTEM_PROMPT,
            user=json.dumps(_cv_payload(user, profile), ensure_ascii=False, indent=2),
            schema=GeneratedCV,
            max_tokens=3072,
        )
