"""Turn CVs and public code into an evidence-backed skill graph.

Self-reported skills are a claim; these are the same claim with a citation. The
profile keeps both, and every skill records where it came from, so the matching
engine and the trust score can eventually treat evidence differently from
assertion without losing what the specialist told us.
"""

import json

from app.ai.llm import ChatModel
from app.ai.prompts import CV_EXTRACTION_SYSTEM_PROMPT, GITHUB_EXTRACTION_SYSTEM_PROMPT
from app.ai.schemas import CVExtraction, EvidencedSkill, GitHubExtraction, SkillSource
from app.services.github import GitHubClient, Repository


class NothingToAnalyse(Exception):
    """The account exists but has no original public repositories."""


# A skill backed by evidence replaces a self-reported one; between two evidenced
# sources the more direct wins. Interview outcomes rank highest because a person
# defended the claim in conversation.
SOURCE_RANK = {
    SkillSource.SELF_REPORTED: 0,
    SkillSource.GITHUB: 1,
    SkillSource.CV: 2,
    SkillSource.CERTIFICATION: 3,
    SkillSource.INTERVIEW: 4,
}


def merge_skills(
    existing: list[dict], incoming: list[EvidencedSkill], source: SkillSource
) -> list[dict]:
    """Merge extracted skills into a profile's skill list.

    Existing entries are keyed by canonical name. A new entry wins only if its
    source outranks what is already recorded, so re-parsing a CV never downgrades
    an interview-verified skill, and enrichment never silently deletes anything.
    """
    merged: dict[str, dict] = {}
    for skill in existing:
        name = skill["name"].strip().lower()
        merged[name] = {**skill, "name": name}
        merged[name].setdefault("source", SkillSource.SELF_REPORTED.value)

    for skill in incoming:
        name = skill.name.strip().lower()
        candidate = {
            "name": name,
            "level": skill.level,
            "years": skill.years,
            "source": source.value,
            "evidence": skill.evidence,
        }
        current = merged.get(name)
        if current is None:
            merged[name] = candidate
            continue
        current_rank = SOURCE_RANK.get(SkillSource(current.get("source", "self_reported")), 0)
        if SOURCE_RANK[source] >= current_rank:
            # keep the higher years figure: a CV may cover work GitHub cannot show
            candidate["years"] = max(candidate["years"], float(current.get("years") or 0))
            merged[name] = candidate

    return sorted(merged.values(), key=lambda s: (-s["level"], s["name"]))


def summarise_repositories(repositories: list[Repository]) -> dict:
    """Project repositories to what the model needs, dropping noise."""
    substantial = [
        repo
        for repo in repositories
        if not repo.is_fork and repo.size_kb > 0
    ]
    return {
        "repository_count": len(repositories),
        "original_repository_count": len(substantial),
        "repositories": [
            {
                "name": repo.name,
                "description": repo.description,
                "language": repo.language,
                "stars": repo.stars,
                "size_kb": repo.size_kb,
                "last_pushed": repo.pushed_at,
                "topics": repo.topics,
            }
            for repo in sorted(substantial, key=lambda r: (-r.stars, -r.size_kb))[:40]
        ],
    }


class EnrichmentService:
    def __init__(self, chat_model: ChatModel, github: GitHubClient):
        self._chat = chat_model
        self._github = github

    async def from_cv(self, cv_text: str) -> CVExtraction:
        return await self._chat.complete_structured(
            system=CV_EXTRACTION_SYSTEM_PROMPT,
            user=cv_text.strip(),
            schema=CVExtraction,
            max_tokens=4096,
        )

    async def from_github(self, username: str) -> tuple[GitHubExtraction, int]:
        """Returns the extraction and how many repositories informed it.

        Raises NothingToAnalyse when the account has no original repositories —
        checked before prompting, because paying for a model call that can only
        answer "nothing here" is pure waste.
        """
        repositories = await self._github.repositories(username)
        payload = summarise_repositories(repositories)
        if payload["original_repository_count"] == 0:
            raise NothingToAnalyse(username)
        extraction = await self._chat.complete_structured(
            system=GITHUB_EXTRACTION_SYSTEM_PROMPT,
            user=json.dumps(payload, ensure_ascii=False, indent=2),
            schema=GitHubExtraction,
            max_tokens=3072,
        )
        return extraction, payload["original_repository_count"]
