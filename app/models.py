# models.py
from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, ForeignKey, Text, JSON, Boolean, LargeBinary, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import enum

# ==================== Enums ====================

class TransactionType(str, enum.Enum):
    INCOME = "income"
    EXPENSE = "expense"

class ExpenseStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

# Main Categories (Parent Categories)
class MainCategory(str, enum.Enum):
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

# Sub Categories Constants
class SubCategoryConstants:
    # Travel subcategories
    UBER = "uber"
    RAPIDO = "rapido"
    OLA = "ola"
    METRO = "metro"
    BUS = "bus"
    TRAIN = "train"
    FLIGHT = "flight"
    TAXI = "taxi"
    AUTO = "auto"
    FUEL_TRAVEL = "fuel_travel"
    PARKING = "parking"
    TOLL = "toll"
    CAR_RENTAL = "car_rental"
    
    # Food subcategories
    SWIGGY = "swiggy"
    ZOMATO = "zomato"
    DINING = "dining"
    CAFE = "cafe"
    RESTAURANT = "restaurant"
    STREET_FOOD = "street_food"
    PARTY_FOOD = "party_food"
    OFFICE_LUNCH = "office_lunch"
    
    # Bills subcategories
    ELECTRICITY = "electricity"
    WATER = "water"
    GAS = "gas"
    INTERNET = "internet"
    MOBILE = "mobile"
    DTH = "dth"
    MAINTENANCE = "maintenance"
    PROPERTY_TAX = "property_tax"
    
    # Shopping subcategories
    CLOTHING = "clothing"
    ELECTRONICS = "electronics"
    GROCERIES_SHOPPING = "groceries_shopping"
    HOME_APPLIANCES = "home_appliances"
    FURNITURE = "furniture"
    BOOKS = "books"
    MEDICINE_SHOPPING = "medicine_shopping"
    
    # Entertainment subcategories
    MOVIES = "movies"
    CONCERT = "concert"
    NETFLIX = "netflix"
    AMAZON_PRIME = "amazon_prime"
    HOTSTAR = "hotstar"
    GAMING = "gaming"
    SPORTS = "sports"
    PARTY_ENTERTAINMENT = "party_entertainment"
    
    # Healthcare subcategories
    DOCTOR = "doctor"
    DENTIST = "dentist"
    MEDICINE = "medicine"
    HOSPITAL = "hospital"
    LAB_TESTS = "lab_tests"
    PHYSIOTHERAPY = "physiotherapy"
    FITNESS = "fitness"
    GYM = "gym"
    
    # Education subcategories
    SCHOOL_FEES = "school_fees"
    COLLEGE_FEES = "college_fees"
    BOOKS_EDUCATION = "books_education"
    COURSES = "courses"
    TUITION = "tuition"
    EXAM_FEES = "exam_fees"
    STATIONERY = "stationery"
    
    # Fuel subcategories
    PETROL = "petrol"
    DIESEL = "diesel"
    CNG = "cng"
    EV_CHARGING = "ev_charging"
    
    # Insurance subcategories
    HEALTH_INSURANCE = "health_insurance"
    LIFE_INSURANCE = "life_insurance"
    VEHICLE_INSURANCE = "vehicle_insurance"
    HOME_INSURANCE = "home_insurance"
    TRAVEL_INSURANCE = "travel_insurance"
    
    # Investment subcategories
    STOCKS = "stocks"
    MUTUAL_FUNDS = "mutual_funds"
    FIXED_DEPOSIT = "fixed_deposit"
    PPF = "ppf"
    NPS = "nps"
    GOLD = "gold"
    REAL_ESTATE = "real_estate"
    
    # Income subcategories
    SALARY_INCOME = "salary_income"
    BONUS = "bonus"
    FREELANCE = "freelance"
    BUSINESS = "business"
    RENTAL_INCOME = "rental_income"
    INVESTMENT_RETURNS = "investment_returns"
    REFUND = "refund"
    GIFTS = "gifts"
    REIMBURSEMENT = "reimbursement"

class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    UPI = "upi"
    NET_BANKING = "net_banking"
    WALLET = "wallet"
    CRYPTO = "crypto"

class UploadMethod(str, enum.Enum):
    MANUAL = "manual"
    OCR = "ocr"

# ==================== Models ====================

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    phone_number = Column(String)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    expenses = relationship(
        "Expense",
        back_populates="user",
        foreign_keys="Expense.user_id",
        cascade="all, delete-orphan",
    )
    wallet = relationship("Wallet", back_populates="user", uselist=False, cascade="all, delete-orphan")
    ocr_bills = relationship("OCRBill", back_populates="user", cascade="all, delete-orphan")
    ocr_batches = relationship("OCRBatch", back_populates="user", cascade="all, delete-orphan")


class Expense(Base):
    __tablename__ = "expenses"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Basic fields
    bill_name = Column(String, nullable=False)
    bill_amount = Column(Float, nullable=False)
    bill_date = Column(DateTime(timezone=True), nullable=False)
    transaction_type = Column(Enum(TransactionType), nullable=False)
    
    # Hierarchical Categories
    main_category = Column(Enum(MainCategory), nullable=False)
    sub_category = Column(String, nullable=True)  # Stores subcategory values like 'uber', 'swiggy', etc.
    
    # Additional fields
    description = Column(Text)
    payment_method = Column(Enum(PaymentMethod))
    vendor_name = Column(String)
    bill_number = Column(String)
    tax_amount = Column(Float, default=0.0)
    discount_amount = Column(Float, default=0.0)
    
    # Legacy single-file columns (deprecated; use expense_files)
    file_data = Column(LargeBinary, nullable=True)
    file_name = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String, nullable=True)
    file_hash = Column(String(64), nullable=True)
    thumbnail_data = Column(LargeBinary, nullable=True)
    
    # Status tracking
    status = Column(Enum(ExpenseStatus), default=ExpenseStatus.PENDING)
    upload_method = Column(Enum(UploadMethod), nullable=False)
    rejection_reason = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    approved_at = Column(DateTime(timezone=True))
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="expenses", foreign_keys=[user_id])
    files = relationship("ExpenseFile", back_populates="expense", cascade="all, delete-orphan")
    wallet_transaction = relationship("WalletTransaction", back_populates="expense", uselist=False, cascade="all, delete-orphan")
    ocr_bills = relationship("OCRBill", back_populates="expense", cascade="all, delete-orphan")
    approver = relationship("User", foreign_keys=[approved_by])
    
    # Indexes for better performance
    __table_args__ = (
        Index('ix_expenses_user_status', 'user_id', 'status'),
        Index('ix_expenses_user_date', 'user_id', 'bill_date'),
        Index('ix_expenses_user_category', 'user_id', 'main_category'),
        Index('ix_expenses_file_hash', 'file_hash'),
        Index('ix_expenses_bill_date', 'bill_date'),
    )


class ExpenseFile(Base):
    """Multiple files attached to one expense."""
    __tablename__ = "expense_files"

    id = Column(Integer, primary_key=True, index=True)
    expense_id = Column(Integer, ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False)

    file_data = Column(LargeBinary, nullable=False)
    file_name = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String, nullable=False)
    file_hash = Column(String(64), nullable=True)
    thumbnail_data = Column(LargeBinary, nullable=True)

    is_primary = Column(Boolean, default=False)
    page_number = Column(Integer, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    expense = relationship("Expense", back_populates="files")

    __table_args__ = (
        Index("ix_expense_files_expense_id", "expense_id"),
        Index("ix_expense_files_hash", "file_hash"),
    )


class OCRBatch(Base):
    """Groups multiple OCR scans processed together."""
    __tablename__ = "ocr_batches"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    batch_name = Column(String, nullable=True)
    total_files = Column(Integer, default=0)
    processed_files = Column(Integer, default=0)
    status = Column(String, default="processing")  # processing, completed, failed
    result_summary = Column(JSON, nullable=True)  # failed_files, skipped_duplicates, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="ocr_batches")
    ocr_bills = relationship("OCRBill", back_populates="batch")


class OCRBill(Base):
    __tablename__ = "ocr_bills"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expense_id = Column(Integer, ForeignKey("expenses.id", ondelete="SET NULL"), nullable=True)
    batch_id = Column(Integer, ForeignKey("ocr_batches.id", ondelete="SET NULL"), nullable=True)

    # Original file data
    original_file_data = Column(LargeBinary)  # Store original uploaded file
    original_file_name = Column(String)
    original_file_size = Column(Integer)
    original_mime_type = Column(String)
    
    # Extracted data - Comprehensive fields for all types of bills
    # Basic info
    bill_number = Column(String)
    bill_date = Column(DateTime(timezone=True))
    due_date = Column(DateTime(timezone=True))
    vendor_name = Column(String)
    vendor_gst = Column(String)
    vendor_address = Column(Text)
    customer_name = Column(String)
    customer_gst = Column(String)
    
    # Financial details
    subtotal = Column(Float)
    total_amount = Column(Float)
    tax_amount = Column(Float)
    discount_amount = Column(Float)
    shipping_charges = Column(Float)
    convenience_fee = Column(Float)
    tip_amount = Column(Float)
    round_off = Column(Float)
    
    # Tax breakdown (JSON for flexibility)
    tax_breakdown = Column(JSON)  # {"cgst": 18, "sgst": 18, "igst": 0}
    
    # Ride-specific fields (Uber, Rapido, Ola)
    ride_distance = Column(Float)  # in km
    ride_duration = Column(Integer)  # in minutes
    pickup_location = Column(String)
    dropoff_location = Column(String)
    ride_type = Column(String)  # UberGo, UberXL, Rapido Auto, etc.
    driver_name = Column(String)
    vehicle_number = Column(String)
    
    # Food delivery specific (Swiggy, Zomato)
    restaurant_name = Column(String)
    restaurant_address = Column(Text)
    order_number = Column(String)
    items_list = Column(JSON)  # List of items with prices
    delivery_charge = Column(Float)
    packaging_charge = Column(Float)
    platform_fee = Column(Float)
    gst_on_platform_fee = Column(Float)
    
    # Payment details
    payment_method = Column(String)
    payment_status = Column(String)
    payment_transaction_id = Column(String)
    card_last_four = Column(String)
    
    # Raw extracted data
    raw_text = Column(Text)
    confidence_score = Column(Float)  # OCR confidence score
    extracted_fields = Column(JSON)  # All extracted fields as JSON
    
    # Detected category hierarchy
    detected_main_category = Column(Enum(MainCategory), nullable=True)
    detected_sub_category = Column(String, nullable=True)
    
    # Processing metadata
    processed_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_by = Column(String)  # OCR service used
    
    # Relationships
    user = relationship("User", back_populates="ocr_bills")
    expense = relationship("Expense", back_populates="ocr_bills")
    batch = relationship("OCRBatch", back_populates="ocr_bills")

    # Indexes
    __table_args__ = (
        Index('ix_ocr_bills_user_id', 'user_id'),
        Index('ix_ocr_bills_expense_id', 'expense_id'),
        Index('ix_ocr_bills_batch_id', 'batch_id'),
        Index('ix_ocr_bills_processed_at', 'processed_at'),
    )


class Wallet(Base):
    __tablename__ = "wallets"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    balance = Column(Float, default=0.0)
    total_income = Column(Float, default=0.0)
    total_expense = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="wallet")
    transactions = relationship("WalletTransaction", back_populates="wallet", cascade="all, delete-orphan")


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False)
    expense_id = Column(Integer, ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False)
    
    amount = Column(Float, nullable=False)
    transaction_type = Column(Enum(TransactionType), nullable=False)
    transaction_date = Column(DateTime(timezone=True), server_default=func.now())
    description = Column(Text)
    
    # Category info at time of transaction
    main_category = Column(Enum(MainCategory), nullable=True)
    sub_category = Column(String, nullable=True)
    
    # Relationships
    wallet = relationship("Wallet", back_populates="transactions")
    expense = relationship("Expense", back_populates="wallet_transaction")
    
    # Indexes
    __table_args__ = (
        Index('ix_wallet_transactions_wallet_id', 'wallet_id'),
        Index('ix_wallet_transactions_date', 'transaction_date'),
    )


class Budget(Base):
    __tablename__ = "budgets"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    main_category = Column(Enum(MainCategory), nullable=False)
    sub_category = Column(String, nullable=True)
    month = Column(Integer, nullable=False)  # 1-12
    year = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)
    alert_threshold = Column(Float, default=80.0)  # Alert at 80% of budget
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User")
    
    # Unique constraint for user+category+month+year
    __table_args__ = (
        Index('ix_budgets_user_category_month', 'user_id', 'main_category', 'month', 'year', unique=True),
    )


# ==================== Category Mapping Helper ====================

class CategoryMapping:
    """Helper class for category mappings"""
    
    # Map subcategories to main categories
    SUBCATEGORY_TO_MAIN = {
        # Travel
        SubCategoryConstants.UBER: MainCategory.TRAVEL,
        SubCategoryConstants.RAPIDO: MainCategory.TRAVEL,
        SubCategoryConstants.OLA: MainCategory.TRAVEL,
        SubCategoryConstants.METRO: MainCategory.TRAVEL,
        SubCategoryConstants.BUS: MainCategory.TRAVEL,
        SubCategoryConstants.TRAIN: MainCategory.TRAVEL,
        SubCategoryConstants.FLIGHT: MainCategory.TRAVEL,
        SubCategoryConstants.TAXI: MainCategory.TRAVEL,
        SubCategoryConstants.AUTO: MainCategory.TRAVEL,
        SubCategoryConstants.FUEL_TRAVEL: MainCategory.TRAVEL,
        SubCategoryConstants.PARKING: MainCategory.TRAVEL,
        SubCategoryConstants.TOLL: MainCategory.TRAVEL,
        SubCategoryConstants.CAR_RENTAL: MainCategory.TRAVEL,
        
        # Food
        SubCategoryConstants.SWIGGY: MainCategory.FOOD,
        SubCategoryConstants.ZOMATO: MainCategory.FOOD,
        SubCategoryConstants.DINING: MainCategory.FOOD,
        SubCategoryConstants.CAFE: MainCategory.FOOD,
        SubCategoryConstants.RESTAURANT: MainCategory.FOOD,
        SubCategoryConstants.STREET_FOOD: MainCategory.FOOD,
        SubCategoryConstants.PARTY_FOOD: MainCategory.FOOD,
        SubCategoryConstants.OFFICE_LUNCH: MainCategory.FOOD,
        
        # Bills
        SubCategoryConstants.ELECTRICITY: MainCategory.BILLS,
        SubCategoryConstants.WATER: MainCategory.BILLS,
        SubCategoryConstants.GAS: MainCategory.BILLS,
        SubCategoryConstants.INTERNET: MainCategory.BILLS,
        SubCategoryConstants.MOBILE: MainCategory.BILLS,
        SubCategoryConstants.DTH: MainCategory.BILLS,
        SubCategoryConstants.MAINTENANCE: MainCategory.BILLS,
        SubCategoryConstants.PROPERTY_TAX: MainCategory.BILLS,
        
        # Shopping
        SubCategoryConstants.CLOTHING: MainCategory.SHOPPING,
        SubCategoryConstants.ELECTRONICS: MainCategory.SHOPPING,
        SubCategoryConstants.GROCERIES_SHOPPING: MainCategory.SHOPPING,
        SubCategoryConstants.HOME_APPLIANCES: MainCategory.SHOPPING,
        SubCategoryConstants.FURNITURE: MainCategory.SHOPPING,
        SubCategoryConstants.BOOKS: MainCategory.SHOPPING,
        
        # Entertainment
        SubCategoryConstants.MOVIES: MainCategory.ENTERTAINMENT,
        SubCategoryConstants.CONCERT: MainCategory.ENTERTAINMENT,
        SubCategoryConstants.NETFLIX: MainCategory.ENTERTAINMENT,
        SubCategoryConstants.AMAZON_PRIME: MainCategory.ENTERTAINMENT,
        SubCategoryConstants.HOTSTAR: MainCategory.ENTERTAINMENT,
        SubCategoryConstants.GAMING: MainCategory.ENTERTAINMENT,
        SubCategoryConstants.SPORTS: MainCategory.ENTERTAINMENT,
        SubCategoryConstants.PARTY_ENTERTAINMENT: MainCategory.ENTERTAINMENT,
        
        # Healthcare
        SubCategoryConstants.DOCTOR: MainCategory.HEALTHCARE,
        SubCategoryConstants.DENTIST: MainCategory.HEALTHCARE,
        SubCategoryConstants.MEDICINE: MainCategory.HEALTHCARE,
        SubCategoryConstants.HOSPITAL: MainCategory.HEALTHCARE,
        SubCategoryConstants.LAB_TESTS: MainCategory.HEALTHCARE,
        SubCategoryConstants.PHYSIOTHERAPY: MainCategory.HEALTHCARE,
        SubCategoryConstants.FITNESS: MainCategory.HEALTHCARE,
        SubCategoryConstants.GYM: MainCategory.HEALTHCARE,
        
        # Education
        SubCategoryConstants.SCHOOL_FEES: MainCategory.EDUCATION,
        SubCategoryConstants.COLLEGE_FEES: MainCategory.EDUCATION,
        SubCategoryConstants.BOOKS_EDUCATION: MainCategory.EDUCATION,
        SubCategoryConstants.COURSES: MainCategory.EDUCATION,
        SubCategoryConstants.TUITION: MainCategory.EDUCATION,
        SubCategoryConstants.EXAM_FEES: MainCategory.EDUCATION,
        SubCategoryConstants.STATIONERY: MainCategory.EDUCATION,
        
        # Fuel
        SubCategoryConstants.PETROL: MainCategory.FUEL,
        SubCategoryConstants.DIESEL: MainCategory.FUEL,
        SubCategoryConstants.CNG: MainCategory.FUEL,
        SubCategoryConstants.EV_CHARGING: MainCategory.FUEL,
        
        # Insurance
        SubCategoryConstants.HEALTH_INSURANCE: MainCategory.INSURANCE,
        SubCategoryConstants.LIFE_INSURANCE: MainCategory.INSURANCE,
        SubCategoryConstants.VEHICLE_INSURANCE: MainCategory.INSURANCE,
        SubCategoryConstants.HOME_INSURANCE: MainCategory.INSURANCE,
        SubCategoryConstants.TRAVEL_INSURANCE: MainCategory.INSURANCE,
        
        # Investment
        SubCategoryConstants.STOCKS: MainCategory.INVESTMENT,
        SubCategoryConstants.MUTUAL_FUNDS: MainCategory.INVESTMENT,
        SubCategoryConstants.FIXED_DEPOSIT: MainCategory.INVESTMENT,
        SubCategoryConstants.PPF: MainCategory.INVESTMENT,
        SubCategoryConstants.NPS: MainCategory.INVESTMENT,
        SubCategoryConstants.GOLD: MainCategory.INVESTMENT,
        SubCategoryConstants.REAL_ESTATE: MainCategory.INVESTMENT,
    }
    
    @classmethod
    def get_main_category(cls, sub_category: str) -> MainCategory:
        """Get main category for a subcategory"""
        if not sub_category:
            return MainCategory.MISCELLANEOUS
        return cls.SUBCATEGORY_TO_MAIN.get(sub_category.lower(), MainCategory.MISCELLANEOUS)
    
    @classmethod
    def get_all_subcategories(cls, main_category: MainCategory) -> list:
        """Get all subcategories for a main category"""
        return [key for key, value in cls.SUBCATEGORY_TO_MAIN.items() if value == main_category]