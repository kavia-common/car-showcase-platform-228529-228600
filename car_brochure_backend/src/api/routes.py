from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, delete, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.auth import require_admin
from src.api.db import get_db
from src.api.schemas import (
    AdminListResponse,
    CarCreate,
    CarDetailResponse,
    CarImageCreate,
    CarImageOut,
    CarImageUpdate,
    CarListItem,
    CarListResponse,
    CarOut,
    CarUpdate,
    CompareRequest,
    CompareResponse,
    DeleteResponse,
    InquiryOut,
    InquiryUpdate,
    LeadCreateRequest,
    LeadCreateResponse,
    PageMeta,
    TrimCreate,
    TrimFeatureCreate,
    TrimFeatureOut,
    TrimFeatureUpdate,
    TrimOut,
    TrimSpecCreate,
    TrimSpecOut,
    TrimSpecUpdate,
    TrimUpdate,
)

router = APIRouter()

# --- Table definitions (lightweight) ---
# We intentionally avoid ORM models for speed; we use SQLAlchemy Core text columns via reflection-free Table.
# Since schema is stable/known, we query using textual column names via table(...) and column(...).
from sqlalchemy import column, table  # noqa: E402

cars_t = table(
    "cars",
    column("id"),
    column("make"),
    column("model"),
    column("year"),
    column("body_type"),
    column("msrp_base_cents"),
    column("description"),
    column("is_active"),
    column("created_at"),
    column("updated_at"),
)
trims_t = table(
    "trims",
    column("id"),
    column("car_id"),
    column("name"),
    column("msrp_cents"),
    column("is_default"),
    column("created_at"),
    column("updated_at"),
)
car_images_t = table(
    "car_images",
    column("id"),
    column("car_id"),
    column("trim_id"),
    column("url"),
    column("alt_text"),
    column("kind"),
    column("sort_order"),
    column("is_primary"),
    column("created_at"),
)
trim_specs_t = table(
    "trim_specs",
    column("id"),
    column("trim_id"),
    column("category"),
    column("name"),
    column("value"),
    column("unit"),
    column("sort_order"),
    column("created_at"),
)
trim_features_t = table(
    "trim_features",
    column("id"),
    column("trim_id"),
    column("feature_group"),
    column("description"),
    column("sort_order"),
    column("created_at"),
)
inquiries_t = table(
    "inquiries",
    column("id"),
    column("car_id"),
    column("trim_id"),
    column("full_name"),
    column("email"),
    column("phone"),
    column("message"),
    column("preferred_contact_method"),
    column("status"),
    column("source"),
    column("created_at"),
)


def _page_meta(limit: int, offset: int, total: int) -> PageMeta:
    return PageMeta(limit=limit, offset=offset, total=total)


def _not_found(entity: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{entity} not found")


def _integrity_error_to_http(e: IntegrityError) -> HTTPException:
    # Keep it simple and safe; do not leak DB internals.
    msg = str(e.orig).lower() if getattr(e, "orig", None) else "integrity error"
    if "unique" in msg or "duplicate" in msg:
        return HTTPException(status_code=409, detail="Conflict: record already exists")
    return HTTPException(status_code=400, detail="Invalid data")


def _fetch_car_detail(db: Session, car_id: int, public_only: bool = True) -> CarDetailResponse:
    car_stmt = select(cars_t).where(cars_t.c.id == car_id)  # type: ignore[attr-defined]
    if public_only:
        car_stmt = car_stmt.where(cars_t.c.is_active.is_(True))  # type: ignore[attr-defined]

    car_row = db.execute(car_stmt).mappings().first()
    if not car_row:
        raise _not_found("Car")

    car = CarOut(**car_row)

    images = (
        db.execute(
            select(car_images_t)
            .where(car_images_t.c.car_id == car_id)  # type: ignore[attr-defined]
            .order_by(car_images_t.c.is_primary.desc(), car_images_t.c.sort_order.asc(), car_images_t.c.id.asc())  # type: ignore[attr-defined]
        )
        .mappings()
        .all()
    )
    images_out = [CarImageOut(**r) for r in images]

    trims = (
        db.execute(
            select(trims_t)
            .where(trims_t.c.car_id == car_id)  # type: ignore[attr-defined]
            .order_by(trims_t.c.is_default.desc(), trims_t.c.msrp_cents.asc(), trims_t.c.id.asc())  # type: ignore[attr-defined]
        )
        .mappings()
        .all()
    )
    trims_out = [TrimOut(**r) for r in trims]
    default_trim_id = None
    for t in trims_out:
        if t.is_default:
            default_trim_id = t.id
            break

    trim_ids = [t.id for t in trims_out]
    specs_by_trim: dict[str, list[TrimSpecOut]] = {}
    features_by_trim: dict[str, list[TrimFeatureOut]] = {}

    if trim_ids:
        specs_rows = (
            db.execute(
                select(trim_specs_t)
                .where(trim_specs_t.c.trim_id.in_(trim_ids))  # type: ignore[attr-defined]
                .order_by(
                    trim_specs_t.c.trim_id.asc(),  # type: ignore[attr-defined]
                    trim_specs_t.c.category.asc(),  # type: ignore[attr-defined]
                    trim_specs_t.c.sort_order.asc(),  # type: ignore[attr-defined]
                    trim_specs_t.c.id.asc(),  # type: ignore[attr-defined]
                )
            )
            .mappings()
            .all()
        )
        for r in specs_rows:
            k = str(r["trim_id"])
            specs_by_trim.setdefault(k, []).append(TrimSpecOut(**r))

        features_rows = (
            db.execute(
                select(trim_features_t)
                .where(trim_features_t.c.trim_id.in_(trim_ids))  # type: ignore[attr-defined]
                .order_by(
                    trim_features_t.c.trim_id.asc(),  # type: ignore[attr-defined]
                    trim_features_t.c.feature_group.asc(),  # type: ignore[attr-defined]
                    trim_features_t.c.sort_order.asc(),  # type: ignore[attr-defined]
                    trim_features_t.c.id.asc(),  # type: ignore[attr-defined]
                )
            )
            .mappings()
            .all()
        )
        for r in features_rows:
            k = str(r["trim_id"])
            features_by_trim.setdefault(k, []).append(TrimFeatureOut(**r))

    return CarDetailResponse(
        car=car,
        images=images_out,
        trims=trims_out,
        default_trim_id=default_trim_id,
        specs_by_trim=specs_by_trim,
        features_by_trim=features_by_trim,
    )


# -------------------- Public endpoints --------------------

@router.get(
    "/catalog/cars",
    response_model=CarListResponse,
    tags=["public"],
    summary="List cars",
    description="Public catalog listing with search, filtering, sorting, and pagination.",
    operation_id="list_cars",
)
def list_cars(
    q: Optional[str] = Query(None, description="Search make/model (ILIKE)."),
    make: Optional[str] = Query(None, description="Filter by make."),
    model: Optional[str] = Query(None, description="Filter by model."),
    body_type: Optional[str] = Query(None, description="Filter by body type."),
    year: Optional[int] = Query(None, ge=1886, le=2100, description="Filter by year."),
    min_price_cents: Optional[int] = Query(None, ge=0, description="Min base MSRP (cents)."),
    max_price_cents: Optional[int] = Query(None, ge=0, description="Max base MSRP (cents)."),
    sort: str = Query(
        "relevance",
        description="Sort order: relevance|price_asc|price_desc|year_desc|year_asc|make_model",
    ),
    limit: int = Query(20, ge=1, le=100, description="Page size."),
    offset: int = Query(0, ge=0, description="Pagination offset."),
    db: Session = Depends(get_db),
) -> CarListResponse:
    filters = [cars_t.c.is_active.is_(True)]  # type: ignore[attr-defined]

    if q:
        like = f"%{q.strip()}%"
        filters.append(or_(cars_t.c.make.ilike(like), cars_t.c.model.ilike(like)))  # type: ignore[attr-defined]
    if make:
        filters.append(cars_t.c.make == make)  # type: ignore[attr-defined]
    if model:
        filters.append(cars_t.c.model == model)  # type: ignore[attr-defined]
    if body_type:
        filters.append(cars_t.c.body_type == body_type)  # type: ignore[attr-defined]
    if year is not None:
        filters.append(cars_t.c.year == year)  # type: ignore[attr-defined]
    if min_price_cents is not None:
        filters.append(cars_t.c.msrp_base_cents >= min_price_cents)  # type: ignore[attr-defined]
    if max_price_cents is not None:
        filters.append(cars_t.c.msrp_base_cents <= max_price_cents)  # type: ignore[attr-defined]

    where_clause = and_(*filters)

    total = db.execute(select(func.count()).select_from(cars_t).where(where_clause)).scalar_one()

    # Primary image subquery (per car)
    primary_img_subq = (
        select(car_images_t.c.car_id, func.min(car_images_t.c.url).label("primary_url"))  # type: ignore[attr-defined]
        .where(and_(car_images_t.c.is_primary.is_(True), car_images_t.c.car_id == cars_t.c.id))  # type: ignore[attr-defined]
        .group_by(car_images_t.c.car_id)  # type: ignore[attr-defined]
        .subquery()
    )

    stmt = (
        select(
            cars_t.c.id,
            cars_t.c.make,
            cars_t.c.model,
            cars_t.c.year,
            cars_t.c.body_type,
            cars_t.c.msrp_base_cents,
            cars_t.c.description,
            primary_img_subq.c.primary_url,  # type: ignore[attr-defined]
        )
        .select_from(cars_t.outerjoin(primary_img_subq, primary_img_subq.c.car_id == cars_t.c.id))  # type: ignore[attr-defined]
        .where(where_clause)
        .limit(limit)
        .offset(offset)
    )

    # Sorting
    if sort == "price_asc":
        stmt = stmt.order_by(cars_t.c.msrp_base_cents.asc(), cars_t.c.make.asc(), cars_t.c.model.asc())  # type: ignore[attr-defined]
    elif sort == "price_desc":
        stmt = stmt.order_by(cars_t.c.msrp_base_cents.desc(), cars_t.c.make.asc(), cars_t.c.model.asc())  # type: ignore[attr-defined]
    elif sort == "year_desc":
        stmt = stmt.order_by(cars_t.c.year.desc(), cars_t.c.make.asc(), cars_t.c.model.asc())  # type: ignore[attr-defined]
    elif sort == "year_asc":
        stmt = stmt.order_by(cars_t.c.year.asc(), cars_t.c.make.asc(), cars_t.c.model.asc())  # type: ignore[attr-defined]
    elif sort == "make_model":
        stmt = stmt.order_by(cars_t.c.make.asc(), cars_t.c.model.asc(), cars_t.c.year.desc())  # type: ignore[attr-defined]
    else:
        # "relevance" fallback: make/model alphabetical is acceptable without full text ranking.
        stmt = stmt.order_by(cars_t.c.make.asc(), cars_t.c.model.asc(), cars_t.c.year.desc())  # type: ignore[attr-defined]

    rows = db.execute(stmt).mappings().all()

    items: list[CarListItem] = []
    for r in rows:
        items.append(
            CarListItem(
                id=r["id"],
                make=r["make"],
                model=r["model"],
                year=r["year"],
                body_type=r["body_type"],
                msrp_base_cents=r["msrp_base_cents"],
                description=r["description"],
                primary_image_url=r.get("primary_url"),
            )
        )

    return CarListResponse(meta=_page_meta(limit, offset, total), items=items)


@router.get(
    "/catalog/cars/{car_id}",
    response_model=CarDetailResponse,
    tags=["public"],
    summary="Car detail",
    description="Get car detail including images, trims, specs, and features.",
    operation_id="get_car_detail",
)
def get_car_detail(car_id: int, db: Session = Depends(get_db)) -> CarDetailResponse:
    return _fetch_car_detail(db, car_id=car_id, public_only=True)


@router.post(
    "/catalog/compare",
    response_model=CompareResponse,
    tags=["public"],
    summary="Compare cars",
    description="Compare 2-4 cars (returns per-car detail payloads).",
    operation_id="compare_cars",
)
def compare_cars(payload: CompareRequest, db: Session = Depends(get_db)) -> CompareResponse:
    # Deduplicate while preserving order
    seen = set()
    car_ids: list[int] = []
    for cid in payload.car_ids:
        if cid not in seen:
            seen.add(cid)
            car_ids.append(cid)
    if len(car_ids) < 2:
        raise HTTPException(status_code=400, detail="Provide at least two distinct car_ids")

    cars = [_fetch_car_detail(db, car_id=cid, public_only=True) for cid in car_ids]
    return CompareResponse(cars=cars)


@router.post(
    "/leads",
    response_model=LeadCreateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["public"],
    summary="Submit lead",
    description="Create an inquiry/lead (optionally tied to a car/trim).",
    operation_id="create_lead",
)
def create_lead(payload: LeadCreateRequest, db: Session = Depends(get_db)) -> LeadCreateResponse:
    # Validate referenced car/trim if provided (do not require active for leads).
    if payload.trim_id is not None:
        trim_exists = db.execute(select(func.count()).select_from(trims_t).where(trims_t.c.id == payload.trim_id)).scalar_one()  # type: ignore[attr-defined]
        if trim_exists == 0:
            raise _not_found("Trim")

    if payload.car_id is not None:
        car_exists = db.execute(select(func.count()).select_from(cars_t).where(cars_t.c.id == payload.car_id)).scalar_one()  # type: ignore[attr-defined]
        if car_exists == 0:
            raise _not_found("Car")

    stmt = (
        insert(inquiries_t)
        .values(
            car_id=payload.car_id,
            trim_id=payload.trim_id,
            full_name=payload.full_name,
            email=str(payload.email),
            phone=payload.phone,
            message=payload.message,
            preferred_contact_method=payload.preferred_contact_method,
            status="new",
            source=payload.source,
        )
        .returning(inquiries_t.c.id, inquiries_t.c.status)  # type: ignore[attr-defined]
    )

    row = db.execute(stmt).mappings().first()
    db.commit()
    assert row is not None
    return LeadCreateResponse(id=row["id"], status=row["status"])


# -------------------- Admin endpoints (HTTP Basic) --------------------

admin = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@admin.get(
    "/cars",
    response_model=CarListResponse,
    summary="Admin list cars",
    description="List cars including inactive ones. Supports same filters as public list.",
    operation_id="admin_list_cars",
)
def admin_list_cars(
    q: Optional[str] = Query(None),
    make: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    body_type: Optional[str] = Query(None),
    year: Optional[int] = Query(None, ge=1886, le=2100),
    is_active: Optional[bool] = Query(None, description="Filter by active flag."),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> CarListResponse:
    filters = []
    if q:
        like = f"%{q.strip()}%"
        filters.append(or_(cars_t.c.make.ilike(like), cars_t.c.model.ilike(like)))  # type: ignore[attr-defined]
    if make:
        filters.append(cars_t.c.make == make)  # type: ignore[attr-defined]
    if model:
        filters.append(cars_t.c.model == model)  # type: ignore[attr-defined]
    if body_type:
        filters.append(cars_t.c.body_type == body_type)  # type: ignore[attr-defined]
    if year is not None:
        filters.append(cars_t.c.year == year)  # type: ignore[attr-defined]
    if is_active is not None:
        filters.append(cars_t.c.is_active.is_(is_active))  # type: ignore[attr-defined]

    where_clause = and_(*filters) if filters else True  # type: ignore[arg-type]

    total = db.execute(select(func.count()).select_from(cars_t).where(where_clause)).scalar_one()

    stmt = (
        select(
            cars_t.c.id,
            cars_t.c.make,
            cars_t.c.model,
            cars_t.c.year,
            cars_t.c.body_type,
            cars_t.c.msrp_base_cents,
            cars_t.c.description,
        )
        .where(where_clause)
        .order_by(cars_t.c.updated_at.desc(), cars_t.c.id.desc())  # type: ignore[attr-defined]
        .limit(limit)
        .offset(offset)
    )

    rows = db.execute(stmt).mappings().all()
    items = [
        CarListItem(
            id=r["id"],
            make=r["make"],
            model=r["model"],
            year=r["year"],
            body_type=r["body_type"],
            msrp_base_cents=r["msrp_base_cents"],
            description=r["description"],
            primary_image_url=None,
        )
        for r in rows
    ]
    return CarListResponse(meta=_page_meta(limit, offset, total), items=items)


@admin.post(
    "/cars",
    response_model=CarOut,
    status_code=status.HTTP_201_CREATED,
    summary="Admin create car",
    operation_id="admin_create_car",
)
def admin_create_car(payload: CarCreate, db: Session = Depends(get_db)) -> CarOut:
    try:
        row = (
            db.execute(
                insert(cars_t)
                .values(
                    make=payload.make,
                    model=payload.model,
                    year=payload.year,
                    body_type=payload.body_type,
                    msrp_base_cents=payload.msrp_base_cents,
                    description=payload.description,
                    is_active=payload.is_active,
                )
                .returning(cars_t)
            )
            .mappings()
            .first()
        )
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise _integrity_error_to_http(e) from e

    assert row is not None
    return CarOut(**row)


@admin.patch(
    "/cars/{car_id}",
    response_model=CarOut,
    summary="Admin update car",
    operation_id="admin_update_car",
)
def admin_update_car(car_id: int, payload: CarUpdate, db: Session = Depends(get_db)) -> CarOut:
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=400, detail="No fields provided")

    try:
        row = (
            db.execute(
                update(cars_t)
                .where(cars_t.c.id == car_id)  # type: ignore[attr-defined]
                .values(**values)
                .returning(cars_t)
            )
            .mappings()
            .first()
        )
        if not row:
            db.rollback()
            raise _not_found("Car")
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise _integrity_error_to_http(e) from e

    return CarOut(**row)


@admin.delete(
    "/cars/{car_id}",
    response_model=DeleteResponse,
    summary="Admin delete car",
    description="Deletes a car (cascades trims/images/specs/features).",
    operation_id="admin_delete_car",
)
def admin_delete_car(car_id: int, db: Session = Depends(get_db)) -> DeleteResponse:
    row = db.execute(delete(cars_t).where(cars_t.c.id == car_id).returning(cars_t.c.id)).first()  # type: ignore[attr-defined]
    if not row:
        db.rollback()
        raise _not_found("Car")
    db.commit()
    return DeleteResponse(deleted_id=row[0])


@admin.post(
    "/trims",
    response_model=TrimOut,
    status_code=status.HTTP_201_CREATED,
    summary="Admin create trim",
    operation_id="admin_create_trim",
)
def admin_create_trim(payload: TrimCreate, db: Session = Depends(get_db)) -> TrimOut:
    # Ensure car exists
    car_exists = db.execute(select(func.count()).select_from(cars_t).where(cars_t.c.id == payload.car_id)).scalar_one()  # type: ignore[attr-defined]
    if car_exists == 0:
        raise _not_found("Car")

    try:
        row = (
            db.execute(
                insert(trims_t)
                .values(
                    car_id=payload.car_id,
                    name=payload.name,
                    msrp_cents=payload.msrp_cents,
                    is_default=payload.is_default,
                )
                .returning(trims_t)
            )
            .mappings()
            .first()
        )
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise _integrity_error_to_http(e) from e

    assert row is not None
    return TrimOut(**row)


@admin.patch(
    "/trims/{trim_id}",
    response_model=TrimOut,
    summary="Admin update trim",
    operation_id="admin_update_trim",
)
def admin_update_trim(trim_id: int, payload: TrimUpdate, db: Session = Depends(get_db)) -> TrimOut:
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=400, detail="No fields provided")

    try:
        row = (
            db.execute(
                update(trims_t)
                .where(trims_t.c.id == trim_id)  # type: ignore[attr-defined]
                .values(**values)
                .returning(trims_t)
            )
            .mappings()
            .first()
        )
        if not row:
            db.rollback()
            raise _not_found("Trim")
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise _integrity_error_to_http(e) from e

    return TrimOut(**row)


@admin.delete(
    "/trims/{trim_id}",
    response_model=DeleteResponse,
    summary="Admin delete trim",
    operation_id="admin_delete_trim",
)
def admin_delete_trim(trim_id: int, db: Session = Depends(get_db)) -> DeleteResponse:
    row = db.execute(delete(trims_t).where(trims_t.c.id == trim_id).returning(trims_t.c.id)).first()  # type: ignore[attr-defined]
    if not row:
        db.rollback()
        raise _not_found("Trim")
    db.commit()
    return DeleteResponse(deleted_id=row[0])


@admin.post(
    "/images",
    response_model=CarImageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Admin create car image",
    operation_id="admin_create_image",
)
def admin_create_image(payload: CarImageCreate, db: Session = Depends(get_db)) -> CarImageOut:
    # Ensure car exists
    car_exists = db.execute(select(func.count()).select_from(cars_t).where(cars_t.c.id == payload.car_id)).scalar_one()  # type: ignore[attr-defined]
    if car_exists == 0:
        raise _not_found("Car")

    if payload.trim_id is not None:
        trim_exists = db.execute(select(func.count()).select_from(trims_t).where(trims_t.c.id == payload.trim_id)).scalar_one()  # type: ignore[attr-defined]
        if trim_exists == 0:
            raise _not_found("Trim")

    try:
        row = (
            db.execute(
                insert(car_images_t)
                .values(
                    car_id=payload.car_id,
                    trim_id=payload.trim_id,
                    url=payload.url,
                    alt_text=payload.alt_text,
                    kind=payload.kind,
                    sort_order=payload.sort_order,
                    is_primary=payload.is_primary,
                )
                .returning(car_images_t)
            )
            .mappings()
            .first()
        )
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise _integrity_error_to_http(e) from e

    assert row is not None
    return CarImageOut(**row)


@admin.patch(
    "/images/{image_id}",
    response_model=CarImageOut,
    summary="Admin update car image",
    operation_id="admin_update_image",
)
def admin_update_image(image_id: int, payload: CarImageUpdate, db: Session = Depends(get_db)) -> CarImageOut:
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=400, detail="No fields provided")

    if "trim_id" in values and values["trim_id"] is not None:
        trim_exists = db.execute(select(func.count()).select_from(trims_t).where(trims_t.c.id == values["trim_id"])).scalar_one()  # type: ignore[attr-defined]
        if trim_exists == 0:
            raise _not_found("Trim")

    try:
        row = (
            db.execute(
                update(car_images_t)
                .where(car_images_t.c.id == image_id)  # type: ignore[attr-defined]
                .values(**values)
                .returning(car_images_t)
            )
            .mappings()
            .first()
        )
        if not row:
            db.rollback()
            raise _not_found("Image")
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise _integrity_error_to_http(e) from e

    return CarImageOut(**row)


@admin.delete(
    "/images/{image_id}",
    response_model=DeleteResponse,
    summary="Admin delete car image",
    operation_id="admin_delete_image",
)
def admin_delete_image(image_id: int, db: Session = Depends(get_db)) -> DeleteResponse:
    row = db.execute(delete(car_images_t).where(car_images_t.c.id == image_id).returning(car_images_t.c.id)).first()  # type: ignore[attr-defined]
    if not row:
        db.rollback()
        raise _not_found("Image")
    db.commit()
    return DeleteResponse(deleted_id=row[0])


@admin.post(
    "/specs",
    response_model=TrimSpecOut,
    status_code=status.HTTP_201_CREATED,
    summary="Admin create trim spec",
    operation_id="admin_create_trim_spec",
)
def admin_create_trim_spec(payload: TrimSpecCreate, db: Session = Depends(get_db)) -> TrimSpecOut:
    trim_exists = db.execute(select(func.count()).select_from(trims_t).where(trims_t.c.id == payload.trim_id)).scalar_one()  # type: ignore[attr-defined]
    if trim_exists == 0:
        raise _not_found("Trim")

    try:
        row = (
            db.execute(
                insert(trim_specs_t)
                .values(
                    trim_id=payload.trim_id,
                    category=payload.category,
                    name=payload.name,
                    value=payload.value,
                    unit=payload.unit,
                    sort_order=payload.sort_order,
                )
                .returning(trim_specs_t)
            )
            .mappings()
            .first()
        )
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise _integrity_error_to_http(e) from e

    assert row is not None
    return TrimSpecOut(**row)


@admin.patch(
    "/specs/{spec_id}",
    response_model=TrimSpecOut,
    summary="Admin update trim spec",
    operation_id="admin_update_trim_spec",
)
def admin_update_trim_spec(spec_id: int, payload: TrimSpecUpdate, db: Session = Depends(get_db)) -> TrimSpecOut:
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=400, detail="No fields provided")

    try:
        row = (
            db.execute(
                update(trim_specs_t)
                .where(trim_specs_t.c.id == spec_id)  # type: ignore[attr-defined]
                .values(**values)
                .returning(trim_specs_t)
            )
            .mappings()
            .first()
        )
        if not row:
            db.rollback()
            raise _not_found("Spec")
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise _integrity_error_to_http(e) from e

    return TrimSpecOut(**row)


@admin.delete(
    "/specs/{spec_id}",
    response_model=DeleteResponse,
    summary="Admin delete trim spec",
    operation_id="admin_delete_trim_spec",
)
def admin_delete_trim_spec(spec_id: int, db: Session = Depends(get_db)) -> DeleteResponse:
    row = db.execute(delete(trim_specs_t).where(trim_specs_t.c.id == spec_id).returning(trim_specs_t.c.id)).first()  # type: ignore[attr-defined]
    if not row:
        db.rollback()
        raise _not_found("Spec")
    db.commit()
    return DeleteResponse(deleted_id=row[0])


@admin.post(
    "/features",
    response_model=TrimFeatureOut,
    status_code=status.HTTP_201_CREATED,
    summary="Admin create trim feature",
    operation_id="admin_create_trim_feature",
)
def admin_create_trim_feature(payload: TrimFeatureCreate, db: Session = Depends(get_db)) -> TrimFeatureOut:
    trim_exists = db.execute(select(func.count()).select_from(trims_t).where(trims_t.c.id == payload.trim_id)).scalar_one()  # type: ignore[attr-defined]
    if trim_exists == 0:
        raise _not_found("Trim")

    try:
        row = (
            db.execute(
                insert(trim_features_t)
                .values(
                    trim_id=payload.trim_id,
                    feature_group=payload.feature_group,
                    description=payload.description,
                    sort_order=payload.sort_order,
                )
                .returning(trim_features_t)
            )
            .mappings()
            .first()
        )
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise _integrity_error_to_http(e) from e

    assert row is not None
    return TrimFeatureOut(**row)


@admin.patch(
    "/features/{feature_id}",
    response_model=TrimFeatureOut,
    summary="Admin update trim feature",
    operation_id="admin_update_trim_feature",
)
def admin_update_trim_feature(feature_id: int, payload: TrimFeatureUpdate, db: Session = Depends(get_db)) -> TrimFeatureOut:
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=400, detail="No fields provided")

    try:
        row = (
            db.execute(
                update(trim_features_t)
                .where(trim_features_t.c.id == feature_id)  # type: ignore[attr-defined]
                .values(**values)
                .returning(trim_features_t)
            )
            .mappings()
            .first()
        )
        if not row:
            db.rollback()
            raise _not_found("Feature")
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise _integrity_error_to_http(e) from e

    return TrimFeatureOut(**row)


@admin.delete(
    "/features/{feature_id}",
    response_model=DeleteResponse,
    summary="Admin delete trim feature",
    operation_id="admin_delete_trim_feature",
)
def admin_delete_trim_feature(feature_id: int, db: Session = Depends(get_db)) -> DeleteResponse:
    row = db.execute(delete(trim_features_t).where(trim_features_t.c.id == feature_id).returning(trim_features_t.c.id)).first()  # type: ignore[attr-defined]
    if not row:
        db.rollback()
        raise _not_found("Feature")
    db.commit()
    return DeleteResponse(deleted_id=row[0])


@admin.get(
    "/inquiries",
    response_model=AdminListResponse,
    summary="Admin list inquiries",
    description="List lead submissions (inquiries) newest first.",
    operation_id="admin_list_inquiries",
)
def admin_list_inquiries(
    status_filter: Optional[str] = Query(None, description="Filter by inquiry status."),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> AdminListResponse:
    filters = []
    if status_filter:
        filters.append(inquiries_t.c.status == status_filter)  # type: ignore[attr-defined]
    where_clause = and_(*filters) if filters else True  # type: ignore[arg-type]

    total = db.execute(select(func.count()).select_from(inquiries_t).where(where_clause)).scalar_one()

    stmt = (
        select(inquiries_t)
        .where(where_clause)
        .order_by(inquiries_t.c.created_at.desc(), inquiries_t.c.id.desc())  # type: ignore[attr-defined]
        .limit(limit)
        .offset(offset)
    )
    rows = db.execute(stmt).mappings().all()
    items = [InquiryOut(**r).model_dump() for r in rows]
    return AdminListResponse(meta=_page_meta(limit, offset, total), items=items)


@admin.patch(
    "/inquiries/{inquiry_id}",
    response_model=InquiryOut,
    summary="Admin update inquiry",
    operation_id="admin_update_inquiry",
)
def admin_update_inquiry(inquiry_id: int, payload: InquiryUpdate, db: Session = Depends(get_db)) -> InquiryOut:
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=400, detail="No fields provided")

    row = (
        db.execute(
            update(inquiries_t)
            .where(inquiries_t.c.id == inquiry_id)  # type: ignore[attr-defined]
            .values(**values)
            .returning(inquiries_t)
        )
        .mappings()
        .first()
    )
    if not row:
        db.rollback()
        raise _not_found("Inquiry")

    db.commit()
    return InquiryOut(**row)


router.include_router(admin)
