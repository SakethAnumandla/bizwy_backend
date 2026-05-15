from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.dependencies import get_default_user
from app.models import User, Wallet, WalletTransaction
from app.schemas import WalletResponse, WalletTransactionResponse
from app.services.wallet_service import WalletService

router = APIRouter(prefix="/wallet", tags=["wallet"])

@router.get("/balance", response_model=WalletResponse)
async def get_wallet_balance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Get user's wallet balance"""
    wallet_service = WalletService(db)
    wallet = wallet_service.get_or_create_wallet(current_user.id)
    return wallet

@router.get("/transactions", response_model=List[WalletTransactionResponse])
async def get_transactions(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Get wallet transaction history"""
    wallet_service = WalletService(db)
    wallet = wallet_service.get_or_create_wallet(current_user.id)
    
    transactions = db.query(WalletTransaction).filter(
        WalletTransaction.wallet_id == wallet.id
    ).order_by(WalletTransaction.transaction_date.desc()).offset(skip).limit(limit).all()
    
    return transactions

@router.get("/summary")
async def get_wallet_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Get wallet summary statistics"""
    wallet_service = WalletService(db)
    wallet = wallet_service.get_or_create_wallet(current_user.id)
    
    return {
        "current_balance": wallet.balance,
        "total_income": wallet.total_income,
        "total_expense": wallet.total_expense,
        "net_savings": wallet.total_income - wallet.total_expense
    }