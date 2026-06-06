"""
Quotations Router — Create, manage, generate PDF, email client.
Most powerful endpoint: POST /quotations handles full package cost calculation,
PDF generation, Azure upload, and optional email delivery in one call.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models import (
    Agent, Quotation, QuotationActivity, QuotationItem,
    QuotationStatus, User, UserRole,
)
from app.schemas import (
    MessageResponse, PackagePriceRequest, PackagePriceResponse,
    QuotationCreate, QuotationResponse, QuotationUpdate,
)
from app.services import email_service
from app.services.auth_service import get_current_agent, get_current_admin, get_current_user
from app.services.blob_service import blob_service

from app.services.pdf_service import pdf_service
from app.services.pricing_service import pricing_engine

router = APIRouter(prefix="/quotations", tags=["Quotations"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_quote_number() -> str:
    """QT-2024-XXXX format."""
    year = date.today().year
    suffix = uuid.uuid4().hex[:6].upper()
    return f"QT-{year}-{suffix}"


async def _load_quotation(quotation_id: UUID, db: AsyncSession) -> Quotation:
    result = await db.execute(
        select(Quotation)
        .options(
            selectinload(Quotation.items),
            selectinload(Quotation.activities),
            selectinload(Quotation.agent_user).selectinload(User.agent_profile),
        )
        .where(Quotation.id == quotation_id)
    )
    q = result.scalar_one_or_none()
    if not q:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quotation not found")
    return q


def _quotation_to_response(q: Quotation) -> QuotationResponse:
    data = QuotationResponse.model_validate(q)
    if q.agent_user:
        data.agent_name = q.agent_user.full_name
        if q.agent_user.agent_profile:
            data.agency_name = q.agent_user.agent_profile.agency_name
    return data


def _check_access(quotation: Quotation, user: User) -> None:
    """Agents can only see their own quotations; admins see all."""
    if user.role == UserRole.AGENT and quotation.agent_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this quotation")


# ── Background task: upload PDF + send email ──────────────────────────────────

async def _finalize_quotation_bg(
    quotation_id: UUID,
    client_email: Optional[str],
    db_factory,
) -> None:
    """Background: generate PDF → upload to Azure → optionally email client."""
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            q = await _load_quotation(quotation_id, db)
            q_dict = _quotation_to_response(q).model_dump()

            # Generate PDF
            pdf_bytes = pdf_service.generate(q_dict)
            blob_name = pdf_service.build_blob_name(q.quote_number)

            # Upload to Azure Blob
            if settings.PDF_AUTO_UPLOAD:
                pdf_url = await blob_service.upload_pdf(pdf_bytes, blob_name)
                q.pdf_url = pdf_url
                q.pdf_blob_name = blob_name
                db.add(q)
                await db.commit()

            # Send email if client email provided
            if client_email:
                email_service.send_quotation(
                    to_email=client_email,
                    client_name=q.client_name,
                    quote_number=q.quote_number,
                    package_label=q.package_label,
                    total_cost=float(q.total_cost),
                    pdf_bytes=pdf_bytes,
                    pdf_url=q.pdf_url,
                    agency_name=q.agent_user.agent_profile.agency_name if q.agent_user.agent_profile else "WanderKashmir",
                )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(f"BG quotation finalize failed: {exc}")


# ── Package price preview (no DB write) ───────────────────────────────────────

@router.post("/price-preview", response_model=PackagePriceResponse)
async def preview_package_price(
    payload: PackagePriceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_agent),
):
    """
    Live price calculation used by the package builder.
    Returns hotel + vehicle + activity costs with agent markup + GST.
    No database write — purely a calculation endpoint.
    """
    result = await pricing_engine.calculate_package_price(
        db=db,
        nights=payload.nights,
        num_days=payload.days,
        hotel_selections=[{"room_type_id": str(s["room_type_id"]), "meal_plan": s.get("meal_plan", "CP")} for s in payload.hotel_selections],
        vehicle_id=payload.vehicle_id,
        activity_ids=payload.activity_ids,
        agent_user=current_user,
        travel_date=payload.travel_date,
        num_adults=payload.num_adults,
        num_children=payload.num_children,
    )
    return PackagePriceResponse(**result)


# ── Create Quotation ──────────────────────────────────────────────────────────

@router.post("", response_model=QuotationResponse, status_code=status.HTTP_201_CREATED)
async def create_quotation(
    payload: QuotationCreate,
    background_tasks: BackgroundTasks,
    send_email: bool = Query(False, description="Email the quotation PDF to the client"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_agent),
):
    """
    Create a quotation. Calculates total from items, stores to DB,
    then generates PDF and uploads to Azure in the background.
    """
    # Calculate totals from submitted items
    base_cost = Decimal("0")
    for item in payload.items:
        base_cost += Decimal(str(item.total_price))
    for act in payload.activities:
        base_cost += Decimal(str(act.total_price))

    markup_amount = await pricing_engine.apply_agent_markup(db, base_cost, current_user)
    subtotal = base_cost + markup_amount
    gst_amount = pricing_engine.calculate_gst(subtotal)
    total_cost = subtotal + gst_amount

    valid_until = (date.today() + timedelta(days=settings.QUOTATION_VALID_DAYS)).isoformat()

    quotation = Quotation(
        quote_number=_generate_quote_number(),
        agent_user_id=current_user.id,
        client_name=payload.client_name,
        client_email=payload.client_email,
        client_phone=payload.client_phone,
        package_label=payload.package_label,
        nights=payload.nights,
        days=payload.days,
        num_adults=payload.num_adults,
        num_children=payload.num_children,
        travel_date=payload.travel_date,
        base_cost=base_cost,
        markup_amount=markup_amount,
        gst_amount=gst_amount,
        total_cost=total_cost,
        gst_rate=Decimal(str(settings.DEFAULT_GST_RATE)),
        status=QuotationStatus.DRAFT,
        valid_until=valid_until,
        notes=payload.notes,
        full_snapshot=payload.full_snapshot,
    )
    db.add(quotation)
    await db.flush()

    # Line items
    for item in payload.items:
        db.add(QuotationItem(**item.model_dump(), quotation_id=quotation.id))
    for act in payload.activities:
        db.add(QuotationActivity(**act.model_dump(), quotation_id=quotation.id))

    await db.flush()
    await db.refresh(quotation)

    # PDF generation + email in background
    background_tasks.add_task(
        _finalize_quotation_bg,
        quotation.id,
        payload.client_email if send_email else None,
        None,
    )

    return _quotation_to_response(await _load_quotation(quotation.id, db))


# ── List Quotations ───────────────────────────────────────────────────────────

@router.get("", response_model=list[QuotationResponse])
async def list_quotations(
    status_filter: Optional[QuotationStatus] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = (
        select(Quotation)
        .options(
            selectinload(Quotation.items),
            selectinload(Quotation.activities),
            selectinload(Quotation.agent_user).selectinload(User.agent_profile),
        )
        .order_by(Quotation.created_at.desc())
    )
    # Agents only see their own
    if current_user.role == UserRole.AGENT:
        q = q.where(Quotation.agent_user_id == current_user.id)
    if status_filter:
        q = q.where(Quotation.status == status_filter)

    offset = (page - 1) * page_size
    q = q.offset(offset).limit(page_size)
    result = await db.execute(q)
    return [_quotation_to_response(qt) for qt in result.scalars().all()]


# ── Get Single Quotation ──────────────────────────────────────────────────────

@router.get("/{quotation_id}", response_model=QuotationResponse)
async def get_quotation(
    quotation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = await _load_quotation(quotation_id, db)
    _check_access(q, current_user)
    return _quotation_to_response(q)


# ── Update Quotation ──────────────────────────────────────────────────────────

@router.patch("/{quotation_id}", response_model=QuotationResponse)
async def update_quotation(
    quotation_id: UUID,
    payload: QuotationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = await _load_quotation(quotation_id, db)
    _check_access(q, current_user)
    if q.status == QuotationStatus.CONFIRMED and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Confirmed quotations cannot be edited")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(q, field, value)
    db.add(q)
    await db.flush()
    return _quotation_to_response(await _load_quotation(quotation_id, db))


# ── Download PDF ──────────────────────────────────────────────────────────────

@router.get("/{quotation_id}/pdf")
async def download_quotation_pdf(
    quotation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate and stream the quotation PDF."""
    q = await _load_quotation(quotation_id, db)
    _check_access(q, current_user)

    q_dict = _quotation_to_response(q).model_dump()
    pdf_bytes = pdf_service.generate(q_dict)

    filename = f"Kashmir_Quote_{q.quote_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Send Email ────────────────────────────────────────────────────────────────

@router.post("/{quotation_id}/send-email", response_model=MessageResponse)
async def send_quotation_email(
    quotation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = await _load_quotation(quotation_id, db)
    _check_access(q, current_user)

    if not q.client_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quotation has no client email")

    q_dict = _quotation_to_response(q).model_dump()
    pdf_bytes = pdf_service.generate(q_dict)
    agency = q.agent_user.agent_profile.agency_name if q.agent_user.agent_profile else "WanderKashmir"

    sent = email_service.send_quotation(
        to_email=q.client_email,
        client_name=q.client_name,
        quote_number=q.quote_number,
        package_label=q.package_label,
        total_cost=float(q.total_cost),
        pdf_bytes=pdf_bytes,
        pdf_url=q.pdf_url,
        agency_name=agency,
    )
    if not sent:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Failed to send email")

    # Update status to sent
    if q.status == QuotationStatus.DRAFT:
        q.status = QuotationStatus.SENT
        db.add(q)

    return MessageResponse(message=f"Quotation emailed to {q.client_email}")


# ── Admin: stats ──────────────────────────────────────────────────────────────

@router.get("/admin/stats", tags=["Admin"])
async def quotation_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    total = await db.execute(select(func.count()).select_from(Quotation))
    confirmed = await db.execute(select(func.count()).where(Quotation.status == QuotationStatus.CONFIRMED))
    total_revenue = await db.execute(select(func.sum(Quotation.total_cost)).where(Quotation.status == QuotationStatus.CONFIRMED))
    return {
        "total_quotations": total.scalar_one(),
        "confirmed_quotations": confirmed.scalar_one(),
        "total_revenue": float(total_revenue.scalar_one() or 0),
    }