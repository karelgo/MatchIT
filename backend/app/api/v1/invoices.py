import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, load_match, viewer_role
from app.models import Contract, ContractStatus, Invoice, InvoiceStatus
from app.schemas.api import InvoiceCreateRequest, InvoiceResponse
from app.services.payments import PaymentError, compute_invoice
from app.services.vat import assess_vat

router = APIRouter(tags=["invoices"])


async def _load_contract(db: DbSession, contract_id: uuid.UUID) -> Contract:
    contract = await db.scalar(select(Contract).where(Contract.id == contract_id))
    if contract is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contract not found")
    return contract


async def _contract_party(db: DbSession, contract: Contract, user) -> str:
    match = await load_match(db, contract.match_id)
    return viewer_role(match, user)


def _to_response(invoice: Invoice) -> InvoiceResponse:
    return InvoiceResponse(
        id=invoice.id,
        contract_id=invoice.contract_id,
        status=invoice.status.value,
        period_start=invoice.period_start,
        period_end=invoice.period_end,
        hours=float(invoice.hours),
        hourly_rate=float(invoice.hourly_rate),
        currency=invoice.currency,
        subtotal=float(invoice.subtotal),
        vat_rate_percent=float(invoice.vat_rate_percent),
        vat_amount=float(invoice.vat_amount),
        vat_treatment=invoice.vat_treatment,
        vat_note=invoice.vat_note,
        total=float(invoice.total),
        commission_rate_percent=float(invoice.commission_rate_percent),
        commission_amount=float(invoice.commission_amount),
        specialist_payout=float(invoice.specialist_payout),
        created_at=invoice.created_at,
    )


@router.post("/contracts/{contract_id}/invoices", response_model=InvoiceResponse)
async def submit_hours(
    contract_id: uuid.UUID,
    body: InvoiceCreateRequest,
    user: CurrentUser,
    db: DbSession,
    request: Request,
):
    """The specialist bills a period. VAT and commission are computed here."""
    contract = await _load_contract(db, contract_id)
    if await _contract_party(db, contract, user) != "specialist":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the specialist invoices")
    if contract.status != ContractStatus.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "contract is not active")
    if body.period_end < body.period_start:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "period_end must not precede period_start"
        )

    duplicate = await db.scalar(
        select(Invoice).where(
            Invoice.contract_id == contract.id, Invoice.period_start == body.period_start
        )
    )
    if duplicate is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "this period is already invoiced")

    match = await load_match(db, contract.match_id)
    vat = assess_vat(match.specialist.country, match.assignment.company.country)
    commission_rate = Decimal(str(request.app.state.settings.platform_commission_percent))
    amounts = compute_invoice(
        hours=Decimal(str(body.hours)),
        hourly_rate=Decimal(str(contract.hourly_rate)),
        vat=vat,
        commission_rate_percent=commission_rate,
    )

    invoice = Invoice(
        contract_id=contract.id,
        status=InvoiceStatus.ISSUED,
        period_start=body.period_start,
        period_end=body.period_end,
        hours=Decimal(str(body.hours)),
        hourly_rate=Decimal(str(contract.hourly_rate)),
        currency=contract.currency,
        subtotal=amounts.subtotal,
        vat_rate_percent=vat.rate_percent,
        vat_amount=amounts.vat_amount,
        vat_treatment=vat.treatment,
        vat_note=vat.note,
        total=amounts.total,
        commission_rate_percent=commission_rate,
        commission_amount=amounts.commission_amount,
        specialist_payout=amounts.specialist_payout,
    )
    db.add(invoice)
    await db.commit()
    return _to_response(invoice)


@router.get("/contracts/{contract_id}/invoices", response_model=list[InvoiceResponse])
async def list_invoices(contract_id: uuid.UUID, user: CurrentUser, db: DbSession):
    contract = await _load_contract(db, contract_id)
    await _contract_party(db, contract, user)  # raises 404 for non-parties
    invoices = await db.scalars(
        select(Invoice)
        .where(Invoice.contract_id == contract.id)
        .order_by(Invoice.period_start.desc())
    )
    return [_to_response(i) for i in invoices]


@router.post("/invoices/{invoice_id}/pay", response_model=InvoiceResponse)
async def pay_into_escrow(
    invoice_id: uuid.UUID, user: CurrentUser, db: DbSession, request: Request
):
    """The company funds the invoice; the money is held, not yet paid out."""
    invoice = await db.scalar(select(Invoice).where(Invoice.id == invoice_id))
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invoice not found")
    contract = await _load_contract(db, invoice.contract_id)
    if await _contract_party(db, contract, user) != "company":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the company pays")
    if invoice.status != InvoiceStatus.ISSUED:
        raise HTTPException(status.HTTP_409_CONFLICT, f"invoice is {invoice.status.value}")

    try:
        charge = await request.app.state.payment_provider.hold_in_escrow(
            amount=Decimal(str(invoice.total)),
            currency=invoice.currency,
            reference=str(invoice.id),
        )
    except PaymentError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error

    invoice.status = InvoiceStatus.IN_ESCROW
    invoice.payment_reference = charge.reference
    await db.commit()
    return _to_response(invoice)


@router.post("/invoices/{invoice_id}/release", response_model=InvoiceResponse)
async def release_from_escrow(
    invoice_id: uuid.UUID, user: CurrentUser, db: DbSession, request: Request
):
    """The company accepts the work; the payout leaves escrow, less commission."""
    invoice = await db.scalar(select(Invoice).where(Invoice.id == invoice_id))
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invoice not found")
    contract = await _load_contract(db, invoice.contract_id)
    if await _contract_party(db, contract, user) != "company":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the company releases escrow")
    if invoice.status != InvoiceStatus.IN_ESCROW:
        raise HTTPException(status.HTTP_409_CONFLICT, f"invoice is {invoice.status.value}")

    try:
        await request.app.state.payment_provider.release(
            reference=invoice.payment_reference,
            payout=Decimal(str(invoice.specialist_payout)),
        )
    except PaymentError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error

    invoice.status = InvoiceStatus.RELEASED
    await db.commit()
    return _to_response(invoice)
