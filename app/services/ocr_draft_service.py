"""Create draft expenses from OCR (one bill per file, minimal prefill)."""
import os
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import (
    Expense,
    ExpenseStatus,
    MainCategory,
    OCRBatch,
    OCRBill,
    TransactionType,
    UploadMethod,
)
from app.services.ocr_service import OCRProcessor
from app.utils.dedup import find_expense_by_file_hash
from app.utils.expense_helpers import attach_files_to_expense
from app.utils.ocr_categories import (
    default_bill_name,
    detect_main_category,
    detect_sub_category,
)

ocr_processor = OCRProcessor()


def _persist_ocr_bill(
    db: Session,
    user_id: int,
    file_info: dict,
    extracted: dict,
    batch_id: Optional[int],
    main_category: MainCategory,
    sub_category: Optional[str],
) -> OCRBill:
    ocr_bill = OCRBill(
        user_id=user_id,
        batch_id=batch_id,
        original_file_data=file_info["file_data"],
        original_file_name=file_info["file_name"],
        original_file_size=file_info["file_size"],
        original_mime_type=file_info["mime_type"],
        bill_number=extracted.get("bill_number"),
        bill_date=extracted.get("bill_date"),
        vendor_name=extracted.get("vendor_name"),
        vendor_gst=extracted.get("vendor_gst"),
        subtotal=extracted.get("subtotal"),
        total_amount=extracted.get("total_amount"),
        tax_amount=extracted.get("tax_amount"),
        tax_breakdown=extracted.get("tax_breakdown") or None,
        ride_distance=extracted.get("ride_distance"),
        ride_duration=extracted.get("ride_duration"),
        ride_type=extracted.get("ride_type"),
        pickup_location=extracted.get("pickup_location"),
        dropoff_location=extracted.get("dropoff_location"),
        restaurant_name=extracted.get("restaurant_name"),
        items_list=extracted.get("items_list"),
        payment_method=extracted.get("payment_method"),
        customer_name=extracted.get("customer_name"),
        raw_text=extracted.get("raw_text"),
        confidence_score=extracted.get("confidence_score"),
        detected_main_category=main_category,
        detected_sub_category=sub_category,
    )
    db.add(ocr_bill)
    db.flush()
    return ocr_bill


def build_prefill_dict(
    extracted: dict,
    file_name: str,
    bill_index: int,
    main_category: MainCategory,
    sub_category: Optional[str],
) -> dict:
    amount = extracted.get("total_amount")
    needs_review = amount is None or amount <= 0
    if needs_review:
        amount = 1.0

    return {
        "bill_name": default_bill_name(extracted, file_name, bill_index),
        "bill_amount": float(amount),
        "bill_date": extracted.get("bill_date") or datetime.utcnow(),
        "transaction_type": TransactionType.EXPENSE.value,
        "main_category": main_category.value,
        "sub_category": sub_category,
        "description": None,
        "file_name": file_name,
        "amount_needs_review": needs_review,
    }


def create_manual_upload_draft(
    db: Session,
    user_id: int,
    file_info: dict,
    batch_id: Optional[int],
    bill_index: int,
) -> Tuple[Expense, dict, bool]:
    """Draft from file only (no OCR)."""
    file_hash = file_info.get("file_hash")
    if file_hash:
        existing = find_expense_by_file_hash(db, user_id, file_hash)
        if existing:
            prefill = {
                "bill_name": existing.bill_name,
                "bill_amount": existing.bill_amount,
                "bill_date": existing.bill_date,
                "transaction_type": existing.transaction_type.value,
                "main_category": existing.main_category.value,
                "sub_category": existing.sub_category,
                "description": existing.description,
                "file_name": file_info["file_name"],
                "amount_needs_review": False,
            }
            return existing, prefill, True

    main_category = MainCategory.MISCELLANEOUS
    prefill = {
        "bill_name": default_bill_name({}, file_info["file_name"], bill_index),
        "bill_amount": 1.0,
        "bill_date": datetime.utcnow(),
        "transaction_type": TransactionType.EXPENSE.value,
        "main_category": main_category.value,
        "sub_category": None,
        "description": None,
        "file_name": file_info["file_name"],
        "amount_needs_review": True,
    }

    expense = Expense(
        user_id=user_id,
        bill_name=prefill["bill_name"],
        bill_amount=prefill["bill_amount"],
        bill_date=prefill["bill_date"],
        transaction_type=TransactionType.EXPENSE,
        main_category=main_category,
        sub_category=None,
        description=None,
        tax_amount=0.0,
        discount_amount=0.0,
        upload_method=UploadMethod.MANUAL,
        status=ExpenseStatus.DRAFT,
    )
    db.add(expense)
    db.flush()
    attach_files_to_expense(db, expense, [file_info])
    ocr_bill = OCRBill(
        user_id=user_id,
        batch_id=batch_id,
        expense_id=expense.id,
        original_file_data=file_info["file_data"],
        original_file_name=file_info["file_name"],
        original_file_size=file_info["file_size"],
        original_mime_type=file_info["mime_type"],
        detected_main_category=main_category,
    )
    db.add(ocr_bill)
    db.flush()
    return expense, prefill, False


def create_ocr_draft(
    db: Session,
    user_id: int,
    file_info: dict,
    batch_id: Optional[int],
    bill_index: int,
    force_rescan: bool = False,
) -> Tuple[Optional[Expense], dict, bool, Optional[str]]:
    """
    Run OCR, store full data on OCRBill, create DRAFT expense with main fields only.
    Returns (expense, prefill_dict, is_duplicate, error_message).
    """
    file_hash = file_info.get("file_hash")
    if not force_rescan and file_hash:
        existing = find_expense_by_file_hash(db, user_id, file_hash)
        if existing:
            prefill = {
                "bill_name": existing.bill_name,
                "bill_amount": existing.bill_amount,
                "bill_date": existing.bill_date,
                "transaction_type": existing.transaction_type.value,
                "main_category": existing.main_category.value,
                "sub_category": existing.sub_category,
                "description": existing.description,
                "file_name": file_info["file_name"],
                "amount_needs_review": False,
            }
            return existing, prefill, True, None

    ext = file_info.get("file_extension") or file_info["file_name"].rsplit(".", 1)[-1].lower()
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
            tmp.write(file_info["file_data"])
            tmp_path = tmp.name

        extracted = ocr_processor.extract_bill_data_sync(tmp_path, ext)
    except Exception as e:
        return None, {}, False, str(e)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    main_category = detect_main_category(
        extracted.get("vendor_name"),
        extracted.get("restaurant_name"),
    )
    sub_category = detect_sub_category(extracted.get("vendor_name"), main_category)
    prefill = build_prefill_dict(
        extracted, file_info["file_name"], bill_index, main_category, sub_category
    )

    ocr_bill = _persist_ocr_bill(
        db, user_id, file_info, extracted, batch_id, main_category, sub_category
    )

    expense = Expense(
        user_id=user_id,
        bill_name=prefill["bill_name"],
        bill_amount=prefill["bill_amount"],
        bill_date=prefill["bill_date"],
        transaction_type=TransactionType.EXPENSE,
        main_category=main_category,
        sub_category=sub_category,
        description=None,
        tax_amount=0.0,
        discount_amount=0.0,
        upload_method=UploadMethod.OCR,
        status=ExpenseStatus.DRAFT,
    )
    db.add(expense)
    db.flush()
    attach_files_to_expense(db, expense, [file_info])
    ocr_bill.expense_id = expense.id

    return expense, prefill, False, None


def process_multi_file_drafts(
    db: Session,
    user_id: int,
    file_infos: List[dict],
    *,
    use_ocr: bool,
    force_rescan: bool = False,
    batch_name: Optional[str] = None,
) -> Dict[str, Any]:
    batch = OCRBatch(
        user_id=user_id,
        total_files=len(file_infos),
        processed_files=0,
        status="processing",
        batch_name=batch_name or f"Drafts_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
    )
    db.add(batch)
    db.flush()

    bills: List[dict] = []
    failed: List[dict] = []
    skipped: List[dict] = []

    for idx, file_info in enumerate(file_infos, start=1):
        try:
            if use_ocr:
                expense, prefill, is_dup, err = create_ocr_draft(
                    db, user_id, file_info, batch.id, idx, force_rescan
                )
            else:
                expense, prefill, is_dup = create_manual_upload_draft(
                    db, user_id, file_info, batch.id, idx
                )
                err = None

            if err:
                failed.append({"bill_index": idx, "file_name": file_info["file_name"], "error": err})
                continue

            if is_dup:
                skipped.append(
                    {
                        "bill_index": idx,
                        "file_name": file_info["file_name"],
                        "existing_expense_id": expense.id,
                    }
                )

            bills.append(
                {
                    "bill_index": idx,
                    "label": f"Bill {idx}",
                    "expense_id": expense.id,
                    "is_duplicate": is_dup,
                    "prefill": prefill,
                }
            )
            batch.processed_files += 1
        except Exception as e:
            failed.append(
                {"bill_index": idx, "file_name": file_info["file_name"], "error": str(e)}
            )

    batch.status = "completed" if bills else "failed"
    batch.completed_at = datetime.utcnow()
    batch.result_summary = {"failed_files": failed, "skipped_duplicates": skipped}
    db.commit()

    return {
        "batch_id": batch.id,
        "bills": bills,
        "failed": failed,
        "skipped_duplicates": skipped,
    }


def to_multi_bill_response(result: dict):
    from app.schemas import BillDraftItem, BillPrefillData, MultiBillDraftResponse

    bills = [
        BillDraftItem(
            bill_index=b["bill_index"],
            label=b["label"],
            expense_id=b["expense_id"],
            is_duplicate=b["is_duplicate"],
            prefill=BillPrefillData(**b["prefill"]),
        )
        for b in result["bills"]
    ]
    return MultiBillDraftResponse(
        batch_id=result["batch_id"],
        bills=bills,
        failed=result["failed"],
        skipped_duplicates=result["skipped_duplicates"],
        message=f"Created {len(bills)} draft bill(s). Review Bill 1…{len(bills)} and save when ready.",
    )
