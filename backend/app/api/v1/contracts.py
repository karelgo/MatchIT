import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import AssignmentRequirements, ContractDraft
from app.api.deps import AuditDep, CurrentUser, DbSession, load_match, viewer_role
from app.models import AuditAction, Contract, ContractStatus, MatchStatus
from app.schemas.api import (
    ContractCreateRequest,
    ContractDraftView,
    ContractResponse,
    EvidencePackResponse,
)
from app.services.contract import ContractService, ContractTerms
from app.services.evidence import EvidencePackService, evidence_pack_markdown

router = APIRouter(tags=["contracts"])


def get_contract_service(request: Request) -> ContractService:
    return request.app.state.contract_service


ContractDep = Annotated[ContractService, Depends(get_contract_service)]


def _to_response(contract: Contract, viewer: str) -> ContractResponse:
    draft = ContractDraft.model_validate(contract.draft)
    signed_by_me = (
        contract.company_signed_at if viewer == "company" else contract.specialist_signed_at
    ) is not None
    return ContractResponse(
        id=contract.id,
        match_id=contract.match_id,
        status=contract.status.value,
        hourly_rate=contract.hourly_rate,
        currency=contract.currency,
        hours_per_week=contract.hours_per_week,
        start_date=contract.start_date,
        end_date=contract.end_date,
        draft=ContractDraftView.model_validate(draft.model_dump()),
        company_signed=contract.company_signed_at is not None,
        specialist_signed=contract.specialist_signed_at is not None,
        signed_by_me=signed_by_me,
        created_at=contract.created_at,
    )


async def _get_contract(db: AsyncSession, match_id: uuid.UUID) -> Contract | None:
    return await db.scalar(select(Contract).where(Contract.match_id == match_id))


@router.post("/matches/{match_id}/contract", response_model=ContractResponse)
async def create_contract(
    match_id: uuid.UUID,
    body: ContractCreateRequest,
    user: CurrentUser,
    db: DbSession,
    contracts: ContractDep,
):
    """Draft the engagement contract. Only the company initiates; idempotent."""
    match = await load_match(db, match_id)
    viewer = viewer_role(match, user)
    if viewer != "company":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the company drafts the contract")
    if match.status != MatchStatus.MUTUAL:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "both parties must accept the match before contracting"
        )
    if body.end_date is not None and body.end_date <= body.start_date:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "end_date must follow start_date")

    existing = await _get_contract(db, match_id)
    if existing is not None:
        return _to_response(existing, viewer)

    requirements = AssignmentRequirements.model_validate(match.assignment.requirements)
    terms = ContractTerms(
        hourly_rate=body.hourly_rate,
        currency=body.currency,
        hours_per_week=body.hours_per_week,
        start_date=body.start_date,
        end_date=body.end_date,
    )
    draft = await contracts.draft(
        requirements, match.assignment.company, match.specialist, terms
    )
    contract = Contract(
        match_id=match_id,
        status=ContractStatus.PENDING_SIGNATURES,
        hourly_rate=body.hourly_rate,
        currency=body.currency,
        hours_per_week=body.hours_per_week,
        start_date=body.start_date,
        end_date=body.end_date,
        draft=draft.model_dump(mode="json"),
    )
    db.add(contract)
    await db.commit()
    return _to_response(contract, viewer)


@router.get("/matches/{match_id}/contract", response_model=ContractResponse)
async def get_contract(match_id: uuid.UUID, user: CurrentUser, db: DbSession):
    match = await load_match(db, match_id)
    viewer = viewer_role(match, user)
    contract = await _get_contract(db, match_id)
    if contract is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no contract for this match")
    return _to_response(contract, viewer)


@router.post("/matches/{match_id}/contract/sign", response_model=ContractResponse)
async def sign_contract(
    match_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    audit: AuditDep,
    request: Request,
):
    """Record this party's signature; the second signature activates the contract."""
    match = await load_match(db, match_id)
    viewer = viewer_role(match, user)
    contract = await _get_contract(db, match_id)
    if contract is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no contract for this match")
    if contract.status not in (ContractStatus.DRAFT, ContractStatus.PENDING_SIGNATURES):
        raise HTTPException(status.HTTP_409_CONFLICT, f"contract is {contract.status.value}")

    now = datetime.now(UTC)
    if viewer == "company":
        if contract.company_signed_at is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "already signed")
        contract.company_signed_at = now
    else:
        if contract.specialist_signed_at is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "already signed")
        contract.specialist_signed_at = now

    if contract.is_fully_signed:
        contract.status = ContractStatus.ACTIVE

    # A signature is the moment the engagement becomes binding, which makes it the
    # single event most worth being able to evidence later. It is also what the
    # engagement evidence pack reads back as its signature trail.
    await audit.record(
        db,
        AuditAction.CONTRACT_SIGNED,
        actor_user_id=user.id,
        target_type="contract",
        target_id=contract.id,
        request=request,
        context={"party": viewer, "activated": contract.is_fully_signed},
    )
    await db.commit()

    counterparty = (
        match.assignment.company.user_id if viewer == "specialist" else match.specialist.user_id
    )
    await request.app.state.notifier.contract_signed(
        db, counterparty, match_id=match_id, is_active=contract.is_fully_signed
    )
    return _to_response(contract, viewer)


@router.get("/matches/{match_id}/evidence-pack", response_model=EvidencePackResponse)
async def evidence_pack(
    match_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    audit: AuditDep,
    request: Request,
):
    """Assemble the engagement evidence pack for this contract.

    Available to both parties, and to both from the moment the contract exists —
    the point of the pack is that it is already in the drawer when someone asks,
    not that it can be assembled afterwards.
    """
    match = await load_match(db, match_id)
    viewer = viewer_role(match, user)
    contract = await _get_contract(db, match_id)
    if contract is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no contract for this match")

    service: EvidencePackService = request.app.state.evidence_service
    pack = await service.build(db, match, contract)
    await audit.record(
        db,
        AuditAction.EVIDENCE_PACK_ISSUED,
        actor_user_id=user.id,
        target_type="contract",
        target_id=contract.id,
        request=request,
        context={"party": viewer},
    )
    await db.commit()
    return EvidencePackResponse(pack=pack, markdown=evidence_pack_markdown(pack))
