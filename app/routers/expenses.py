from datetime import datetime
from io import BytesIO
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import ExpenseFilters, PaginationParams, get_default_user
from app.models import (
    Expense,
    ExpenseFile,
    ExpenseStatus,
    MainCategory,
    TransactionType,
    UploadMethod,
    User,
)
from app.models import OCRBill
from app.schemas import (
    ExpenseApproval,
    ExpenseDetailResponse,
    ExpenseFileResponse,
    ExpenseResponse,
    ExpenseSubmit,
    ExpenseUpdate,
    MultiBillDraftResponse,
)
from app.services.ocr_draft_service import process_multi_file_drafts, to_multi_bill_response
from app.services.expense_service import ExpenseService
from app.services.wallet_service import WalletService
from app.utils.expense_helpers import (
    attach_files_to_expense,
    build_expense_detail_response,
    build_expense_response,
    expense_file_to_response,
    parse_payment_method,
)
from app.utils.date_parser import parse_bill_date
from app.utils.dedup import find_expense_by_file_hash
from app.utils.file_upload import process_multiple_files, process_single_file
from app.utils.transaction_parser import parse_transaction_type

router = APIRouter(prefix="/expenses", tags=["expenses"])


def _load_expense(db: Session, expense_id: int, user_id: int) -> Expense:
    expense = (
        db.query(Expense)
        .options(joinedload(Expense.files))
        .filter(Expense.id == expense_id, Expense.user_id == user_id)
        .first()
    )
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    return expense


@router.post("/manual", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
async def create_manual_expense(
    bill_name: str = Form(...),
    bill_amount: float = Form(...),
    bill_date: str = Form(..., description="e.g. 15/05/2026, 2026-05-15, ISO"),
    transaction_type: str = Form(..., description="expense, out, income, in"),
    main_category: MainCategory = Form(...),
    sub_category: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    payment_method: Optional[str] = Form(None),
    vendor_name: Optional[str] = Form(None),
    bill_number: Optional[str] = Form(None),
    tax_amount: Optional[float] = Form(0.0),
    discount_amount: Optional[float] = Form(0.0),
    files: List[UploadFile] = File(default=[]),
    save_as_draft: bool = Form(False),
    force_duplicate: bool = Query(
        False,
        description="If true, allow uploading a file that was already used on another expense",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Create expense with one or more file uploads (images, PDFs, or mixed)."""
    if bill_amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")

    parsed_date = parse_bill_date(bill_date)
    parsed_txn = parse_transaction_type(transaction_type)

    processed_files = await process_multiple_files(files) if files else []
    if not force_duplicate and processed_files:
        for pf in processed_files:
            h = pf.get("file_hash")
            if not h:
                continue
            existing = find_expense_by_file_hash(db, current_user.id, h)
            if existing:
                return build_expense_response(existing, is_duplicate=True)
    expense_status = ExpenseStatus.DRAFT if save_as_draft else ExpenseStatus.PENDING

    expense = Expense(
        user_id=current_user.id,
        bill_name=bill_name,
        bill_amount=bill_amount,
        bill_date=parsed_date,
        transaction_type=parsed_txn,
        main_category=main_category,
        sub_category=sub_category,
        description=description,
        payment_method=parse_payment_method(payment_method),
        vendor_name=vendor_name,
        bill_number=bill_number,
        tax_amount=tax_amount or 0.0,
        discount_amount=discount_amount or 0.0,
        upload_method=UploadMethod.MANUAL,
        status=expense_status,
    )
    db.add(expense)
    db.flush()

    if processed_files:
        attach_files_to_expense(db, expense, processed_files)

    db.commit()
    db.refresh(expense)
    expense = _load_expense(db, expense.id, current_user.id)
    return build_expense_response(expense)


@router.post("/upload-drafts", response_model=MultiBillDraftResponse)
async def upload_files_as_drafts(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Upload multiple files without OCR — one DRAFT per file (filename + date prefilled)."""
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")

    file_infos = await process_multiple_files(files)
    for fi in file_infos:
        fi["is_primary"] = True
        fi["file_extension"] = fi["file_name"].rsplit(".", 1)[-1].lower()

    result = process_multi_file_drafts(
        db, current_user.id, file_infos, use_ocr=False
    )
    return to_multi_bill_response(result)


@router.get("/drafts", response_model=List[ExpenseResponse])
async def list_draft_expenses(
    batch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """All draft bills; optional filter by OCR batch_id."""
    if batch_id is not None:
        expense_ids = [
            row[0]
            for row in db.query(OCRBill.expense_id)
            .filter(
                OCRBill.batch_id == batch_id,
                OCRBill.user_id == current_user.id,
                OCRBill.expense_id.isnot(None),
            )
            .all()
        ]
        if not expense_ids:
            return []
        rows = (
            db.query(Expense)
            .options(joinedload(Expense.files))
            .filter(
                Expense.id.in_(expense_ids),
                Expense.user_id == current_user.id,
                Expense.status == ExpenseStatus.DRAFT,
            )
            .order_by(Expense.id.asc())
            .all()
        )
        return [build_expense_response(e) for e in rows]

    rows = ExpenseService(db).get_draft_expenses(current_user.id)
    return [build_expense_response(e) for e in rows]


@router.get("/{expense_id}/details", response_model=ExpenseDetailResponse)
async def get_expense_with_ocr_details(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Full bill details including OCR tax, ride, items (after save / for detail screen)."""
    expense = _load_expense(db, expense_id, current_user.id)
    ocr_bill = (
        db.query(OCRBill)
        .filter(OCRBill.expense_id == expense_id, OCRBill.user_id == current_user.id)
        .first()
    )
    return build_expense_detail_response(expense, ocr_bill)


@router.post("/{expense_id}/submit", response_model=ExpenseResponse)
async def submit_draft_expense(
    expense_id: int,
    body: ExpenseSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Save Bill N: apply main fields + optional tax; move draft → pending or approved."""
    expense = ExpenseService(db).submit_draft(expense_id, current_user.id, body)
    return build_expense_response(_load_expense(db, expense.id, current_user.id))


@router.get("", response_model=List[ExpenseResponse])
async def list_expenses(
    pagination: PaginationParams = Depends(),
    filters: ExpenseFilters = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    service = ExpenseService(db)
    expenses, _ = service.get_user_expenses(
        user_id=current_user.id,
        status=filters.status,
        main_category=filters.main_category,
        transaction_type=filters.transaction_type,
        start_date=filters.start_date,
        end_date=filters.end_date,
        search_term=filters.search,
        skip=pagination.skip,
        limit=pagination.limit,
    )
    return [build_expense_response(e) for e in expenses]


@router.get("/{expense_id}", response_model=ExpenseResponse)
async def get_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    return build_expense_response(_load_expense(db, expense_id, current_user.id))


@router.patch("/{expense_id}", response_model=ExpenseResponse)
async def update_expense(
    expense_id: int,
    body: ExpenseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    service = ExpenseService(db)
    expense = service.update_expense(expense_id, current_user.id, body)
    return build_expense_response(_load_expense(db, expense.id, current_user.id))


@router.post("/{expense_id}/approve", response_model=ExpenseResponse)
async def approve_expense(
    expense_id: int,
    body: ExpenseApproval,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    service = ExpenseService(db)
    expense = service.update_expense_status(
        expense_id,
        current_user.id,
        body.status,
        rejection_reason=body.rejection_reason,
    )
    return build_expense_response(_load_expense(db, expense.id, current_user.id))


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    ExpenseService(db).delete_expense(expense_id, current_user.id)
    return None


@router.post("/{expense_id}/files", response_model=List[ExpenseFileResponse])
async def add_files_to_expense(
    expense_id: int,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    expense = _load_expense(db, expense_id, current_user.id)
    if expense.status == ExpenseStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Cannot add files to approved expense")

    processed_files = await process_multiple_files(files)
    for file_data in processed_files:
        file_data["is_primary"] = False
        db.add(
            ExpenseFile(
                expense_id=expense.id,
                file_data=file_data["file_data"],
                file_name=file_data["file_name"],
                file_size=file_data["file_size"],
                mime_type=file_data["mime_type"],
                file_hash=file_data.get("file_hash"),
                thumbnail_data=file_data.get("thumbnail_data"),
                is_primary=False,
            )
        )
    db.commit()
    expense = _load_expense(db, expense_id, current_user.id)
    return [expense_file_to_response(expense_id, f) for f in expense.files]


@router.get("/{expense_id}/files", response_model=List[ExpenseFileResponse])
async def get_expense_files(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    expense = _load_expense(db, expense_id, current_user.id)
    return [expense_file_to_response(expense_id, f) for f in expense.files]


@router.get("/{expense_id}/files/{file_id}")
async def download_expense_file_by_id(
    expense_id: int,
    file_id: int,
    download: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    expense_file = (
        db.query(ExpenseFile)
        .join(Expense)
        .filter(
            ExpenseFile.id == file_id,
            ExpenseFile.expense_id == expense_id,
            Expense.user_id == current_user.id,
        )
        .first()
    )
    if not expense_file:
        raise HTTPException(status_code=404, detail="File not found")

    disposition = "attachment" if download else "inline"
    headers = {"Content-Disposition": f'{disposition}; filename="{expense_file.file_name}"'}
    return StreamingResponse(
        BytesIO(expense_file.file_data),
        media_type=expense_file.mime_type,
        headers=headers,
    )


@router.get("/{expense_id}/files/{file_id}/thumbnail")
async def get_expense_file_thumbnail(
    expense_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    expense_file = (
        db.query(ExpenseFile)
        .join(Expense)
        .filter(
            ExpenseFile.id == file_id,
            ExpenseFile.expense_id == expense_id,
            Expense.user_id == current_user.id,
        )
        .first()
    )
    if not expense_file or not expense_file.thumbnail_data:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return StreamingResponse(
        BytesIO(expense_file.thumbnail_data),
        media_type="image/jpeg",
        headers={"Content-Disposition": "inline"},
    )


@router.delete("/{expense_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense_file(
    expense_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    expense_file = (
        db.query(ExpenseFile)
        .join(Expense)
        .filter(
            ExpenseFile.id == file_id,
            ExpenseFile.expense_id == expense_id,
            Expense.user_id == current_user.id,
        )
        .first()
    )
    if not expense_file:
        raise HTTPException(status_code=404, detail="File not found")
    if expense_file.expense.status == ExpenseStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Cannot delete files from approved expense")
    db.delete(expense_file)
    db.commit()
    return None


# Legacy single-file endpoints (backward compatibility)
@router.get("/{expense_id}/file")
async def download_expense_file_legacy(
    expense_id: int,
    download: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    expense = _load_expense(db, expense_id, current_user.id)
    if expense.files:
        primary = next((f for f in expense.files if f.is_primary), expense.files[0])
        data, name, mime = primary.file_data, primary.file_name, primary.mime_type
    elif expense.file_data:
        data, name, mime = expense.file_data, expense.file_name, expense.mime_type
    else:
        raise HTTPException(status_code=404, detail="File not found")

    disposition = "attachment" if download else "inline"
    headers = {"Content-Disposition": f'{disposition}; filename="{name}"'}
    return StreamingResponse(BytesIO(data), media_type=mime or "application/octet-stream", headers=headers)


@router.get("/{expense_id}/thumbnail")
async def get_expense_thumbnail_legacy(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    expense = _load_expense(db, expense_id, current_user.id)
    thumb = None
    if expense.files:
        primary = next((f for f in expense.files if f.is_primary), expense.files[0])
        thumb = primary.thumbnail_data
    elif expense.thumbnail_data:
        thumb = expense.thumbnail_data
    if not thumb:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return StreamingResponse(
        BytesIO(thumb),
        media_type="image/jpeg",
        headers={"Content-Disposition": "inline"},
    )
