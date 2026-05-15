import hashlib
import os
import tempfile
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_default_user
from app.models import (
    Expense,
    ExpenseStatus,
    MainCategory,
    OCRBatch,
    OCRBill,
    TransactionType,
    UploadMethod,
    User,
)
from app.schemas import (
    BatchUploadResponse,
    BillDraftItem,
    BillPrefillData,
    ExpenseResponse,
    MultiBillDraftResponse,
    OCRBatchStatusResponse,
    OCRBillResponse,
)
from app.services.ocr_draft_service import process_multi_file_drafts, to_multi_bill_response
from app.utils.ocr_categories import detect_main_category, detect_sub_category
from app.services.ocr_batch_service import process_ocr_batch
from app.services.ocr_service import OCRProcessor
from app.services.wallet_service import WalletService
from app.utils.expense_helpers import (
    attach_files_to_expense,
    build_expense_response,
    parse_payment_method,
)
from app.utils.dedup import find_expense_by_file_hash
from app.utils.file_upload import process_multiple_files, process_single_file

router = APIRouter(prefix="/ocr", tags=["ocr"])
ocr_processor = OCRProcessor()


def _build_ocr_description(data: dict) -> str:
    vendor = data.get("restaurant_name") or data.get("vendor_name") or "Bill"
    parts = [vendor]
    if data.get("ride_type"):
        parts.append(data["ride_type"])
    if data.get("bill_number"):
        parts.append(f"Invoice {data['bill_number']}")
    if data.get("ride_distance"):
        parts.append(f"{data['ride_distance']} km")
    if data.get("ride_duration"):
        parts.append(f"{data['ride_duration']} min")
    if data.get("pickup_location"):
        parts.append(f"From: {data['pickup_location'][:60]}")
    if data.get("dropoff_location"):
        parts.append(f"To: {data['dropoff_location'][:60]}")
    if data.get("customer_name"):
        parts.append(f"Customer: {data['customer_name']}")
    if data.get("table_number"):
        parts.append(f"Table #{data['table_number']}")
    if data.get("payment_method"):
        parts.append(f"Paid via {data['payment_method']}")
    if data.get("tax_amount"):
        parts.append(f"GST {data['tax_amount']}")
    tax_bd = data.get("tax_breakdown") or {}
    if tax_bd:
        parts.append(
            "Tax: " + ", ".join(f"{k.upper()} {v}" for k, v in tax_bd.items())
        )
    items = data.get("items_list") or []
    if items:
        parts.append("Items: " + ", ".join(i.get("name", "") for i in items[:5]))
    return " | ".join(parts)


_detect_sub_category = detect_sub_category
_detect_main_category = detect_main_category


@router.post("/scan-drafts", response_model=MultiBillDraftResponse)
async def scan_multiple_as_drafts(
    files: List[UploadFile] = File(...),
    force_rescan: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """
    Scan multiple files → one DRAFT expense per file.
    Returns Bill 1, Bill 2, … with main fields prefilled only (no tax/payment on form).
    Drafts persist if the user leaves without saving.
    """
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")

    allowed = {"jpg", "jpeg", "png", "pdf", "webp"}
    for f in files:
        ext = f.filename.rsplit(".", 1)[-1].lower()
        if ext not in allowed:
            raise HTTPException(status_code=400, detail=f"Unsupported type: .{ext}")

    file_infos = await process_multiple_files(files)
    for i, fi in enumerate(file_infos):
        fi["is_primary"] = True
        fi["file_extension"] = fi["file_name"].rsplit(".", 1)[-1].lower()

    result = process_multi_file_drafts(
        db,
        current_user.id,
        file_infos,
        use_ocr=True,
        force_rescan=force_rescan,
    )
    return to_multi_bill_response(result)


@router.get("/batch/{batch_id}/drafts", response_model=MultiBillDraftResponse)
async def get_batch_drafts(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Reload Bill 1, Bill 2, … for a batch (e.g. user returned later)."""
    batch = (
        db.query(OCRBatch)
        .filter(OCRBatch.id == batch_id, OCRBatch.user_id == current_user.id)
        .first()
    )
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    ocr_bills = (
        db.query(OCRBill)
        .filter(OCRBill.batch_id == batch_id)
        .order_by(OCRBill.id.asc())
        .all()
    )
    bills = []
    for idx, ob in enumerate(ocr_bills, start=1):
        if not ob.expense_id:
            continue
        expense = (
            db.query(Expense)
            .options(joinedload(Expense.files))
            .filter(Expense.id == ob.expense_id, Expense.user_id == current_user.id)
            .first()
        )
        if not expense:
            continue
        file_name = ob.original_file_name or expense.file_name or f"file_{idx}"
        bills.append(
            BillDraftItem(
                bill_index=idx,
                label=f"Bill {idx}",
                expense_id=expense.id,
                is_duplicate=False,
                prefill=BillPrefillData(
                    bill_name=expense.bill_name,
                    bill_amount=expense.bill_amount,
                    bill_date=expense.bill_date,
                    transaction_type=expense.transaction_type.value,
                    main_category=expense.main_category.value,
                    sub_category=expense.sub_category,
                    description=expense.description,
                    file_name=file_name,
                    amount_needs_review=expense.bill_amount <= 1.0 and expense.status.value == "draft",
                ),
            )
        )

    summary = batch.result_summary if isinstance(batch.result_summary, dict) else {}
    return MultiBillDraftResponse(
        batch_id=batch.id,
        bills=bills,
        failed=summary.get("failed_files", []),
        skipped_duplicates=summary.get("skipped_duplicates", []),
        message=f"{len(bills)} draft bill(s) in this batch",
    )


@router.post("/scan", response_model=ExpenseResponse)
async def scan_single_bill(
    file: UploadFile = File(...),
    auto_approve: bool = False,
    force_rescan: bool = Query(
        False,
        description="If true, scan again even when this exact file was uploaded before",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Scan a single bill using OCR. Identical files (same SHA-256) are not scanned twice."""
    allowed_types = ["jpg", "jpeg", "png", "pdf", "webp"]
    file_extension = file.filename.split(".")[-1].lower()
    if file_extension not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed: {allowed_types}",
        )

    file_info = await process_single_file(file, is_primary=True)
    file_hash = file_info.get("file_hash")
    if not force_rescan and file_hash:
        existing = find_expense_by_file_hash(db, current_user.id, file_hash)
        if existing:
            return build_expense_response(existing, is_duplicate=True)

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as tmp:
            tmp.write(file_info["file_data"])
            tmp_path = tmp.name

        extracted_data = await ocr_processor.extract_bill_data(tmp_path, file_extension)
        if not extracted_data.get("total_amount"):
            raise HTTPException(status_code=400, detail="Could not extract bill amount from image")

        main_category = _detect_main_category(
            extracted_data.get("vendor_name"),
            extracted_data.get("restaurant_name"),
        )
        sub_category = _detect_sub_category(
            extracted_data.get("vendor_name"), main_category
        )

        ocr_bill = OCRBill(
            user_id=current_user.id,
            original_file_data=file_info["file_data"],
            original_file_name=file_info["file_name"],
            original_file_size=file_info["file_size"],
            original_mime_type=file_info["mime_type"],
            bill_number=extracted_data.get("bill_number"),
            bill_date=extracted_data.get("bill_date"),
            vendor_name=extracted_data.get("vendor_name"),
            total_amount=extracted_data.get("total_amount"),
            tax_amount=extracted_data.get("tax_amount"),
            tax_breakdown=extracted_data.get("tax_breakdown") or None,
            ride_distance=extracted_data.get("ride_distance"),
            ride_duration=extracted_data.get("ride_duration"),
            ride_type=extracted_data.get("ride_type"),
            pickup_location=extracted_data.get("pickup_location"),
            dropoff_location=extracted_data.get("dropoff_location"),
            restaurant_name=extracted_data.get("restaurant_name"),
            items_list=extracted_data.get("items_list"),
            raw_text=extracted_data.get("raw_text"),
            confidence_score=extracted_data.get("confidence_score"),
            detected_main_category=main_category,
        )
        db.add(ocr_bill)
        db.flush()

        vendor = extracted_data.get("restaurant_name") or extracted_data.get("vendor_name") or "Unknown Vendor"
        trip_label = extracted_data.get("ride_type") or "Trip"
        bill_suffix = extracted_data.get("bill_number") or (
            extracted_data.get("bill_date").strftime("%d %b %Y")
            if extracted_data.get("bill_date")
            else "OCR"
        )
        expense = Expense(
            user_id=current_user.id,
            bill_name=f"{vendor} — {trip_label} ({bill_suffix})",
            bill_amount=extracted_data["total_amount"],
            bill_date=extracted_data.get("bill_date") or datetime.utcnow(),
            transaction_type=TransactionType.EXPENSE,
            main_category=main_category,
            sub_category=sub_category,
            description=_build_ocr_description(extracted_data),
            vendor_name=extracted_data.get("vendor_name"),
            bill_number=extracted_data.get("bill_number"),
            tax_amount=extracted_data.get("tax_amount") or 0,
            payment_method=parse_payment_method(extracted_data.get("payment_method")),
            upload_method=UploadMethod.OCR,
            status=ExpenseStatus.APPROVED if auto_approve else ExpenseStatus.PENDING,
        )
        db.add(expense)
        db.flush()

        attach_files_to_expense(db, expense, [file_info])
        ocr_bill.expense_id = expense.id

        if auto_approve:
            expense.approved_at = datetime.utcnow()
            WalletService(db).update_wallet_balance(current_user.id, expense)

        db.commit()
        expense = (
            db.query(Expense)
            .options(joinedload(Expense.files))
            .filter(Expense.id == expense.id)
            .first()
        )
        return build_expense_response(expense)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/scan-batch")
async def scan_multiple_bills(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    auto_approve: bool = False,
    force_rescan: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Upload multiple bills for batch OCR (processed in background)."""
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")

    batch = OCRBatch(
        user_id=current_user.id,
        total_files=len(files),
        status="processing",
        batch_name=f"Batch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    file_payloads = []
    for upload in files:
        content = await upload.read()
        ext = upload.filename.rsplit(".", 1)[-1].lower()
        mime = upload.content_type or "application/octet-stream"
        file_payloads.append(
            {
                "filename": upload.filename,
                "content": content,
                "mime_type": mime,
                "file_hash": hashlib.sha256(content).hexdigest(),
            }
        )

    background_tasks.add_task(
        process_ocr_batch,
        batch.id,
        file_payloads,
        current_user.id,
        auto_approve,
        force_rescan,
    )

    return BatchUploadResponse(
        batch_id=batch.id,
        total_files=batch.total_files,
        processed_files=0,
        status=batch.status,
        message=f"Processing {len(files)} files in background",
        status_url=f"/ocr/batch/{batch.id}/status",
    )


@router.get("/batch/{batch_id}/status", response_model=OCRBatchStatusResponse)
async def get_batch_status(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    batch = (
        db.query(OCRBatch)
        .filter(OCRBatch.id == batch_id, OCRBatch.user_id == current_user.id)
        .first()
    )
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    ocr_bills = db.query(OCRBill).filter(OCRBill.batch_id == batch_id).all()
    expense_ids = [b.expense_id for b in ocr_bills if b.expense_id]
    expenses = []
    if expense_ids:
        rows = (
            db.query(Expense)
            .options(joinedload(Expense.files))
            .filter(Expense.id.in_(expense_ids))
            .all()
        )
        expenses = [build_expense_response(e) for e in rows]

    summary = batch.result_summary if isinstance(batch.result_summary, dict) else {}
    return OCRBatchStatusResponse(
        batch_id=batch.id,
        status=batch.status,
        total_files=batch.total_files,
        processed_files=batch.processed_files,
        batch_name=batch.batch_name,
        created_at=batch.created_at,
        completed_at=batch.completed_at,
        expenses=expenses,
        failed_files=summary.get("failed_files", []),
        skipped_duplicates=summary.get("skipped_duplicates", []),
    )


@router.get("/bills", response_model=List[OCRBillResponse])
async def get_ocr_bills(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    return db.query(OCRBill).filter(OCRBill.user_id == current_user.id).all()


@router.get("/bills/{bill_id}", response_model=OCRBillResponse)
async def get_ocr_bill(
    bill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    bill = (
        db.query(OCRBill)
        .filter(OCRBill.id == bill_id, OCRBill.user_id == current_user.id)
        .first()
    )
    if not bill:
        raise HTTPException(status_code=404, detail="OCR bill not found")
    return bill
