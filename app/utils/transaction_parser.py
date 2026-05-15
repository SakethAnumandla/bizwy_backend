from fastapi import HTTPException

from app.models import TransactionType

# Aliases for mobile / casual input
EXPENSE_ALIASES = {"expense", "out", "debit", "spend", "spent", "payment", "paid"}
INCOME_ALIASES = {"income", "in", "credit", "received", "earn", "earning"}


def parse_transaction_type(value: str) -> TransactionType:
    if not value or not str(value).strip():
        raise HTTPException(status_code=400, detail="transaction_type is required")

    key = str(value).strip().lower()
    if key in EXPENSE_ALIASES:
        return TransactionType.EXPENSE
    if key in INCOME_ALIASES:
        return TransactionType.INCOME
    try:
        return TransactionType(key)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transaction_type '{value}'. Use: expense, out, income, in",
        )
