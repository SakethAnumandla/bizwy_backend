# schemas.py - With File Upload Support
from pydantic import BaseModel, Field, validator, root_validator
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

# Enums for validation
class TransactionType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"

class ExpenseStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

# Main Categories
class MainCategory(str, Enum):
    TRAVEL = "travel"
    FOOD = "food"
    BILLS = "bills"
    SHOPPING = "shopping"
    ENTERTAINMENT = "entertainment"
    HEALTHCARE = "healthcare"
    EDUCATION = "education"
    FUEL = "fuel"
    INSURANCE = "insurance"
    INVESTMENT = "investment"
    SALARY = "salary"
    RENT = "rent"
    UTILITIES = "utilities"
    GROCERIES = "groceries"
    PERSONAL_CARE = "personal_care"
    SUBSCRIPTIONS = "subscriptions"
    MISCELLANEOUS = "miscellaneous"

# Sub Categories enums (keep these for validation)
class TravelSubCategory(str, Enum):
    UBER = "uber"
    RAPIDO = "rapido"
    OLA = "ola"
    METRO = "metro"
    BUS = "bus"
    TRAIN = "train"
    FLIGHT = "flight"
    TAXI = "taxi"
    AUTO = "auto"
    FUEL = "fuel"
    PARKING = "parking"
    TOLL = "toll"
    CAR_RENTAL = "car_rental"

class FoodSubCategory(str, Enum):
    SWIGGY = "swiggy"
    ZOMATO = "zomato"
    DINING = "dining"
    CAFE = "cafe"
    GROCERIES = "groceries"
    RESTAURANT = "restaurant"
    STREET_FOOD = "street_food"
    PARTY = "party"
    OFFICE_LUNCH = "office_lunch"

# Main Category Mapping
CATEGORY_SUBCATEGORY_MAPPING = {
    MainCategory.TRAVEL: [item.value for item in TravelSubCategory],
    MainCategory.FOOD: [item.value for item in FoodSubCategory],
    MainCategory.BILLS: ["electricity", "water", "gas", "internet", "mobile", "dth", "maintenance", "property_tax"],
    MainCategory.INSURANCE: ["health_insurance", "life_insurance", "vehicle_insurance", "home_insurance", "travel_insurance"],
    MainCategory.SHOPPING: ["clothing", "electronics", "groceries", "home_appliances", "furniture", "books", "medicine"],
    MainCategory.ENTERTAINMENT: ["movies", "concert", "netflix", "amazon_prime", "hotstar", "gaming", "sports", "party"],
    MainCategory.HEALTHCARE: ["doctor", "dentist", "medicine", "hospital", "lab_tests", "physiotherapy", "fitness", "gym"],
    MainCategory.EDUCATION: ["school_fees", "college_fees", "books", "courses", "tuition", "exam_fees", "stationery"],
    MainCategory.FUEL: ["petrol", "diesel", "cng", "ev_charging"],
    MainCategory.INVESTMENT: ["stocks", "mutual_funds", "fixed_deposit", "ppf", "nps", "gold", "real_estate"],
}

# Category Hierarchy for Frontend
CATEGORY_HIERARCHY = {
    "travel": {
        "display_name": "Travel & Transport",
        "icon": "🚗",
        "color": "#4CAF50",
        "subcategories": {
            "uber": {"display_name": "Uber", "icon": "🚗", "color": "#000000"},
            "rapido": {"display_name": "Rapido", "icon": "🏍️", "color": "#FF5722"},
            "ola": {"display_name": "Ola", "icon": "🚕", "color": "#FFC107"},
            "metro": {"display_name": "Metro", "icon": "🚇", "color": "#2196F3"},
            "bus": {"display_name": "Bus", "icon": "🚌", "color": "#9E9E9E"},
            "train": {"display_name": "Train", "icon": "🚂", "color": "#795548"},
            "flight": {"display_name": "Flight", "icon": "✈️", "color": "#607D8B"},
            "taxi": {"display_name": "Taxi", "icon": "🚖", "color": "#FF9800"},
            "auto": {"display_name": "Auto Rickshaw", "icon": "🛺", "color": "#FFC107"},
            "fuel": {"display_name": "Fuel", "icon": "⛽", "color": "#F44336"},
            "parking": {"display_name": "Parking", "icon": "🅿️", "color": "#9E9E9E"},
            "toll": {"display_name": "Toll", "icon": "🛣️", "color": "#795548"},
            "car_rental": {"display_name": "Car Rental", "icon": "🚙", "color": "#3F51B5"}
        }
    },
    "food": {
        "display_name": "Food & Dining",
        "icon": "🍔",
        "color": "#FF5722",
        "subcategories": {
            "swiggy": {"display_name": "Swiggy", "icon": "🍕", "color": "#FC8019"},
            "zomato": {"display_name": "Zomato", "icon": "🍜", "color": "#CB202D"},
            "dining": {"display_name": "Dining Out", "icon": "🍽️", "color": "#FFC107"},
            "cafe": {"display_name": "Cafe", "icon": "☕", "color": "#8D6E63"},
            "groceries": {"display_name": "Groceries", "icon": "🛒", "color": "#4CAF50"},
            "restaurant": {"display_name": "Restaurant", "icon": "🍴", "color": "#FF9800"},
            "street_food": {"display_name": "Street Food", "icon": "🍢", "color": "#FF5252"},
            "party": {"display_name": "Party/Friends", "icon": "🎉", "color": "#E91E63"},
            "office_lunch": {"display_name": "Office Lunch", "icon": "💼", "color": "#607D8B"}
        }
    }
}

# Expense Schema with File Support
class ExpenseBase(BaseModel):
    bill_name: str = Field(..., min_length=1, max_length=200)
    bill_amount: float = Field(..., gt=0)
    bill_date: datetime
    transaction_type: TransactionType
    main_category: MainCategory
    sub_category: Optional[str] = None
    description: Optional[str] = None
    payment_method: Optional[str] = None
    vendor_name: Optional[str] = None
    bill_number: Optional[str] = None
    tax_amount: Optional[float] = 0.0
    discount_amount: Optional[float] = 0.0

class ExpenseCreate(ExpenseBase):
    upload_method: str = "manual"
    # File fields - these will be set from the uploaded file
    file_data: Optional[bytes] = None
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    
    @validator('bill_amount')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError('Amount must be positive')
        if v > 9999999:
            raise ValueError('Amount exceeds maximum limit')
        return v
    
    @validator('sub_category')
    def validate_sub_category(cls, v, values):
        """Validate sub_category based on main_category"""
        if v and 'main_category' in values:
            main_cat = values['main_category']
            
            # Check if main category has subcategories defined
            if main_cat in CATEGORY_SUBCATEGORY_MAPPING:
                valid_sub_categories = CATEGORY_SUBCATEGORY_MAPPING[main_cat]
                if v.lower() not in valid_sub_categories:
                    raise ValueError(f"Invalid sub_category '{v}' for main_category '{main_cat.value}'")
            return v.lower()
        return v

class ExpenseUpdate(BaseModel):
    bill_name: Optional[str] = None
    bill_amount: Optional[float] = None
    bill_date: Optional[datetime] = None
    main_category: Optional[MainCategory] = None
    sub_category: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ExpenseStatus] = None
    vendor_name: Optional[str] = None
    bill_number: Optional[str] = None


class ExpenseFileResponse(BaseModel):
    id: int
    file_name: str
    file_size: int
    mime_type: str
    is_primary: bool
    file_url: str
    thumbnail_url: Optional[str] = None
    uploaded_at: datetime

    class Config:
        from_attributes = True


class ExpenseResponse(ExpenseBase):
    id: int
    user_id: int
    status: ExpenseStatus
    upload_method: str
    files: List["ExpenseFileResponse"] = []
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    # Deprecated single-file fields (backward compatibility)
    file_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    is_duplicate: bool = False

    class Config:
        from_attributes = True


class BatchUploadResponse(BaseModel):
    batch_id: int
    total_files: int
    processed_files: int
    status: str
    expenses: List[ExpenseResponse] = []
    failed_files: List[Dict[str, Any]] = []
    message: Optional[str] = None
    status_url: Optional[str] = None


class BillPrefillData(BaseModel):
    """Fields to prefill on the frontend form (main info only)."""
    bill_name: str
    bill_amount: float
    bill_date: datetime
    transaction_type: str
    main_category: str
    sub_category: Optional[str] = None
    description: Optional[str] = None
    file_name: str
    amount_needs_review: bool = False


class BillDraftItem(BaseModel):
    bill_index: int
    label: str
    expense_id: int
    is_duplicate: bool = False
    prefill: BillPrefillData


class MultiBillDraftResponse(BaseModel):
    batch_id: int
    bills: List[BillDraftItem] = []
    failed: List[Dict[str, Any]] = []
    skipped_duplicates: List[Dict[str, Any]] = []
    message: Optional[str] = None


class OCRBillDetailResponse(BaseModel):
    """Full OCR extraction — shown in bill details after save, not on prefill."""
    id: int
    bill_number: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_gst: Optional[str] = None
    subtotal: Optional[float] = None
    total_amount: Optional[float] = None
    tax_amount: Optional[float] = None
    tax_breakdown: Optional[Dict[str, Any]] = None
    payment_method: Optional[str] = None
    ride_distance: Optional[float] = None
    ride_duration: Optional[int] = None
    ride_type: Optional[str] = None
    pickup_location: Optional[str] = None
    dropoff_location: Optional[str] = None
    restaurant_name: Optional[str] = None
    items_list: Optional[List[Dict[str, Any]]] = None
    customer_name: Optional[str] = None
    confidence_score: Optional[float] = None

    class Config:
        from_attributes = True


class ExpenseDetailResponse(ExpenseResponse):
    ocr_details: Optional[OCRBillDetailResponse] = None


class ExpenseSubmit(BaseModel):
    """Save / submit a draft bill (user confirms main fields + optional tax)."""
    bill_name: str
    bill_amount: float = Field(..., gt=0)
    bill_date: datetime
    transaction_type: TransactionType
    main_category: MainCategory
    sub_category: Optional[str] = None
    description: Optional[str] = None
    payment_method: Optional[str] = None
    vendor_name: Optional[str] = None
    bill_number: Optional[str] = None
    tax_amount: Optional[float] = 0.0
    discount_amount: Optional[float] = 0.0
    save_as_pending: bool = True
    auto_approve: bool = False

# OCR Bill Schema
class OCRBillBase(BaseModel):
    bill_number: Optional[str] = None
    bill_date: Optional[datetime] = None
    vendor_name: Optional[str] = None
    total_amount: Optional[float] = None
    tax_amount: Optional[float] = None
    confidence_score: Optional[float] = None
    
    # Ride specific
    ride_distance: Optional[float] = None
    pickup_location: Optional[str] = None
    dropoff_location: Optional[str] = None
    
    # Food specific
    restaurant_name: Optional[str] = None
    items_list: Optional[List[Dict]] = None

class OCRBillResponse(OCRBillBase):
    id: int
    user_id: int
    expense_id: Optional[int] = None
    batch_id: Optional[int] = None
    processed_at: datetime

    class Config:
        from_attributes = True


class OCRBatchStatusResponse(BaseModel):
    batch_id: int
    status: str
    total_files: int
    processed_files: int
    batch_name: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    expenses: List[ExpenseResponse] = []
    failed_files: List[Dict[str, Any]] = []
    skipped_duplicates: List[Dict[str, Any]] = []

# Wallet Schemas
class WalletResponse(BaseModel):
    id: int
    user_id: int
    balance: float
    total_income: float
    total_expense: float
    created_at: datetime
    updated_at: datetime

class WalletTransactionResponse(BaseModel):
    id: int
    amount: float
    transaction_type: TransactionType
    transaction_date: datetime
    description: Optional[str]
    expense_id: int

# Approval Schema
class ExpenseApproval(BaseModel):
    status: ExpenseStatus
    rejection_reason: Optional[str] = None

# Dashboard Schemas
class DashboardStats(BaseModel):
    total_balance: float
    total_income: float
    total_expense: float
    pending_approvals: int
    draft_expenses: int

class CategoryWiseExpense(BaseModel):
    category: str
    total_amount: float
    percentage: float
    count: int

class MonthlySummary(BaseModel):
    month: str
    income: float
    expense: float
    net: float

# Helper functions
def get_category_hierarchy():
    """Get category hierarchy for frontend"""
    main_categories = []
    for cat_value, cat_data in CATEGORY_HIERARCHY.items():
        main_categories.append({
            "value": cat_value,
            "display_name": cat_data["display_name"],
            "icon": cat_data["icon"],
            "color": cat_data["color"]
        })
    
    return {
        "main_categories": main_categories,
        "subcategories": CATEGORY_HIERARCHY
    }

def get_all_categories():
    """Get all categories for dropdowns"""
    main_cats = [{"value": cat.value, "label": cat.value.capitalize()} for cat in MainCategory]
    
    sub_cats = {}
    for main_cat in MainCategory:
        if main_cat in CATEGORY_SUBCATEGORY_MAPPING:
            sub_cats[main_cat.value] = [
                {"value": sub, "label": sub.replace('_', ' ').capitalize()}
                for sub in CATEGORY_SUBCATEGORY_MAPPING[main_cat]
            ]
    
    return {
        "main_categories": main_cats,
        "subcategories": sub_cats
    }