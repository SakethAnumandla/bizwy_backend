from typing import List, Optional

from app.models import Expense, ExpenseFile, OCRBill, PaymentMethod
from app.schemas import (
    ExpenseDetailResponse,
    ExpenseFileResponse,
    ExpenseResponse,
    OCRBillDetailResponse,
)


def parse_payment_method(value: Optional[str]) -> Optional[PaymentMethod]:
    if not value:
        return None
    try:
        return PaymentMethod(value.lower())
    except ValueError:
        return None


def expense_file_to_response(expense_id: int, f: ExpenseFile) -> ExpenseFileResponse:
    return ExpenseFileResponse(
        id=f.id,
        file_name=f.file_name,
        file_size=f.file_size,
        mime_type=f.mime_type,
        is_primary=f.is_primary,
        file_url=f"/expenses/{expense_id}/files/{f.id}",
        thumbnail_url=(
            f"/expenses/{expense_id}/files/{f.id}/thumbnail" if f.thumbnail_data else None
        ),
        uploaded_at=f.uploaded_at,
    )


def build_expense_response(
    expense: Expense, *, is_duplicate: bool = False
) -> ExpenseResponse:
    files: List[ExpenseFileResponse] = []
    if expense.files:
        files = [expense_file_to_response(expense.id, f) for f in expense.files]
    elif expense.file_data and expense.file_name:
        files = [
            ExpenseFileResponse(
                id=0,
                file_name=expense.file_name,
                file_size=expense.file_size or 0,
                mime_type=expense.mime_type or "application/octet-stream",
                is_primary=True,
                file_url=f"/expenses/{expense.id}/file",
                thumbnail_url=(
                    f"/expenses/{expense.id}/thumbnail" if expense.thumbnail_data else None
                ),
                uploaded_at=expense.created_at,
            )
        ]

    primary = next((f for f in files if f.is_primary), files[0] if files else None)

    return ExpenseResponse(
        id=expense.id,
        user_id=expense.user_id,
        bill_name=expense.bill_name,
        bill_amount=expense.bill_amount,
        bill_date=expense.bill_date,
        transaction_type=expense.transaction_type,
        main_category=expense.main_category,
        sub_category=expense.sub_category,
        description=expense.description,
        payment_method=expense.payment_method.value if expense.payment_method else None,
        vendor_name=expense.vendor_name,
        bill_number=expense.bill_number,
        tax_amount=expense.tax_amount,
        discount_amount=expense.discount_amount,
        status=expense.status,
        upload_method=expense.upload_method.value,
        files=files,
        rejection_reason=expense.rejection_reason,
        created_at=expense.created_at,
        updated_at=expense.updated_at,
        approved_at=expense.approved_at,
        file_url=primary.file_url if primary else None,
        thumbnail_url=primary.thumbnail_url if primary else None,
        file_name=primary.file_name if primary else expense.file_name,
        file_size=primary.file_size if primary else expense.file_size,
        mime_type=primary.mime_type if primary else expense.mime_type,
        is_duplicate=is_duplicate,
    )


def ocr_bill_to_detail(ocr_bill: OCRBill) -> OCRBillDetailResponse:
    return OCRBillDetailResponse(
        id=ocr_bill.id,
        bill_number=ocr_bill.bill_number,
        vendor_name=ocr_bill.vendor_name,
        vendor_gst=ocr_bill.vendor_gst,
        subtotal=ocr_bill.subtotal,
        total_amount=ocr_bill.total_amount,
        tax_amount=ocr_bill.tax_amount,
        tax_breakdown=ocr_bill.tax_breakdown,
        payment_method=ocr_bill.payment_method,
        ride_distance=ocr_bill.ride_distance,
        ride_duration=ocr_bill.ride_duration,
        ride_type=ocr_bill.ride_type,
        pickup_location=ocr_bill.pickup_location,
        dropoff_location=ocr_bill.dropoff_location,
        restaurant_name=ocr_bill.restaurant_name,
        items_list=ocr_bill.items_list,
        customer_name=ocr_bill.customer_name,
        confidence_score=ocr_bill.confidence_score,
    )


def build_expense_detail_response(
    expense: Expense, ocr_bill: Optional[OCRBill] = None
) -> ExpenseDetailResponse:
    base = build_expense_response(expense)
    return ExpenseDetailResponse(
        **base.model_dump(),
        ocr_details=ocr_bill_to_detail(ocr_bill) if ocr_bill else None,
    )


def attach_files_to_expense(db, expense: Expense, processed_files: List[dict]) -> None:
    """Persist ExpenseFile rows and legacy primary columns on expense."""
    for file_data in processed_files:
        db.add(
            ExpenseFile(
                expense_id=expense.id,
                file_data=file_data["file_data"],
                file_name=file_data["file_name"],
                file_size=file_data["file_size"],
                mime_type=file_data["mime_type"],
                file_hash=file_data.get("file_hash"),
                thumbnail_data=file_data.get("thumbnail_data"),
                is_primary=file_data.get("is_primary", False),
            )
        )

    primary = next((f for f in processed_files if f.get("is_primary")), None)
    if not primary and processed_files:
        primary = processed_files[0]
    if primary:
        expense.file_data = primary["file_data"]
        expense.file_name = primary["file_name"]
        expense.file_size = primary["file_size"]
        expense.mime_type = primary["mime_type"]
        expense.file_hash = primary.get("file_hash")
        expense.thumbnail_data = primary.get("thumbnail_data")
