"""Contract generation agent."""

import json
from datetime import date

from app.ai.llm import ChatModel
from app.ai.prompts import CONTRACT_SYSTEM_PROMPT
from app.ai.schemas import AssignmentRequirements, ContractDraft
from app.models import CompanyProfile, SpecialistProfile


class ContractTerms:
    """The commercial terms the parties agreed — never inferred by the model."""

    def __init__(
        self,
        *,
        hourly_rate: float,
        currency: str,
        hours_per_week: int,
        start_date: date,
        end_date: date | None,
    ):
        self.hourly_rate = hourly_rate
        self.currency = currency
        self.hours_per_week = hours_per_week
        self.start_date = start_date
        self.end_date = end_date

    def as_dict(self) -> dict:
        return {
            "hourly_rate": self.hourly_rate,
            "currency": self.currency,
            "hours_per_week": self.hours_per_week,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat() if self.end_date else None,
        }


class ContractService:
    def __init__(self, chat_model: ChatModel):
        self._chat = chat_model

    async def draft(
        self,
        requirements: AssignmentRequirements,
        company: CompanyProfile,
        specialist: SpecialistProfile,
        terms: ContractTerms,
    ) -> ContractDraft:
        payload = {
            "assignment": {
                "summary": requirements.summary,
                "roles": [
                    {"title": r.title, "seniority": r.seniority} for r in requirements.roles
                ],
                "must_have_skills": requirements.all_skills()[0],
            },
            "company": {
                "name": company.name,
                "country": company.country,
                "industry": company.industry,
            },
            "specialist": {
                "headline": specialist.headline,
                "country": specialist.country,
            },
            "agreed_terms": terms.as_dict(),
        }
        return await self._chat.complete_structured(
            system=CONTRACT_SYSTEM_PROMPT,
            user=json.dumps(payload, ensure_ascii=False, indent=2),
            schema=ContractDraft,
            max_tokens=4096,
        )
