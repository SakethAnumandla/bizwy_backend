"""Category detection and default naming for OCR / draft bills."""
from typing import Optional

from app.models import MainCategory


def detect_main_category(
    vendor_name: Optional[str], restaurant_name: Optional[str] = None
) -> MainCategory:
    combined = f"{vendor_name or ''} {restaurant_name or ''}".lower()
    if any(x in combined for x in ("uber", "rapido", "ola")):
        return MainCategory.TRAVEL
    if any(
        x in combined
        for x in (
            "swiggy",
            "zomato",
            "kitchen",
            "restaurant",
            "cafe",
            "biryani",
            "dining",
            "food",
            "hotel",
        )
    ):
        return MainCategory.FOOD
    return MainCategory.MISCELLANEOUS


def detect_sub_category(
    vendor_name: Optional[str], main_category: MainCategory
) -> Optional[str]:
    if main_category != MainCategory.TRAVEL:
        return "dining" if main_category == MainCategory.FOOD else None
    v = (vendor_name or "").lower()
    if "uber" in v:
        return "uber"
    if "rapido" in v:
        return "rapido"
    if "ola" in v:
        return "ola"
    return "taxi"


def default_bill_name(
    extracted: dict, file_name: str, bill_index: Optional[int] = None
) -> str:
    vendor = extracted.get("restaurant_name") or extracted.get("vendor_name")
    if vendor:
        name = str(vendor).strip()
    else:
        name = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
        name = name[:200]
    if bill_index is not None:
        return f"Bill {bill_index} — {name}"
    return name
