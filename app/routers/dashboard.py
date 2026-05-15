# routers/dashboard.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, extract
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict

from app.database import get_db
from app.dependencies import get_default_user
from app.models import User, Expense, Wallet, ExpenseStatus, TransactionType
from app.schemas import DashboardStats, CategoryWiseExpense, MonthlySummary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Get main dashboard statistics"""
    
    # Default to last 30 days if no dates provided
    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=30)
    
    # Get wallet balance
    wallet = db.query(Wallet).filter(Wallet.user_id == current_user.id).first()
    total_balance = wallet.balance if wallet else 0.0
    
    # Get approved expenses within date range
    approved_expenses = db.query(Expense).filter(
        Expense.user_id == current_user.id,
        Expense.status == ExpenseStatus.APPROVED,
        Expense.bill_date.between(start_date, end_date)
    ).all()
    
    total_income = sum(e.bill_amount for e in approved_expenses if e.transaction_type == TransactionType.INCOME)
    total_expense = sum(e.bill_amount for e in approved_expenses if e.transaction_type == TransactionType.EXPENSE)
    
    # Get pending approvals count
    pending_approvals = db.query(Expense).filter(
        Expense.user_id == current_user.id,
        Expense.status == ExpenseStatus.PENDING
    ).count()
    
    # Get draft expenses count
    draft_expenses = db.query(Expense).filter(
        Expense.user_id == current_user.id,
        Expense.status == ExpenseStatus.DRAFT
    ).count()
    
    return DashboardStats(
        total_balance=total_balance,
        total_income=total_income,
        total_expense=total_expense,
        pending_approvals=pending_approvals,
        draft_expenses=draft_expenses
    )

@router.get("/category-breakdown", response_model=List[CategoryWiseExpense])
async def get_category_breakdown(
    period: str = Query("month", regex="^(week|month|year)$"),
    transaction_type: Optional[TransactionType] = TransactionType.EXPENSE,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Get expense/income breakdown by category"""
    
    # Set date range based on period
    end_date = datetime.utcnow()
    if period == "week":
        start_date = end_date - timedelta(days=7)
    elif period == "month":
        start_date = end_date - timedelta(days=30)
    else:  # year
        start_date = end_date - timedelta(days=365)
    
    # Query expenses by category
    expenses = db.query(
        Expense.main_category,
        func.sum(Expense.bill_amount).label('total_amount'),
        func.count(Expense.id).label('count')
    ).filter(
        Expense.user_id == current_user.id,
        Expense.status == ExpenseStatus.APPROVED,
        Expense.transaction_type == transaction_type,
        Expense.bill_date.between(start_date, end_date)
    ).group_by(Expense.main_category).all()
    
    # Calculate total for percentages
    total = sum(e.total_amount for e in expenses)
    
    result = []
    for expense in expenses:
        percentage = (expense.total_amount / total * 100) if total > 0 else 0
        result.append(CategoryWiseExpense(
            category=expense.main_category.value,
            total_amount=expense.total_amount,
            percentage=round(percentage, 2),
            count=expense.count
        ))
    
    # Sort by total amount descending
    result.sort(key=lambda x: x.total_amount, reverse=True)
    
    return result

@router.get("/monthly-trend", response_model=List[MonthlySummary])
async def get_monthly_trend(
    months: int = Query(6, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Get monthly income/expense trend for last N months"""
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30 * months)
    
    # Query monthly aggregates
    results = db.query(
        extract('year', Expense.bill_date).label('year'),
        extract('month', Expense.bill_date).label('month'),
        Expense.transaction_type,
        func.sum(Expense.bill_amount).label('total')
    ).filter(
        Expense.user_id == current_user.id,
        Expense.status == ExpenseStatus.APPROVED,
        Expense.bill_date.between(start_date, end_date)
    ).group_by(
        'year', 'month', Expense.transaction_type
    ).order_by('year', 'month').all()
    
    # Organize data by month
    monthly_data = defaultdict(lambda: {'income': 0, 'expense': 0})
    
    for result in results:
        month_key = f"{int(result.year)}-{int(result.month):02d}"
        if result.transaction_type == TransactionType.INCOME:
            monthly_data[month_key]['income'] = float(result.total)
        else:
            monthly_data[month_key]['expense'] = float(result.total)
    
    # Create response list
    response = []
    for month_key in sorted(monthly_data.keys()):
        data = monthly_data[month_key]
        response.append(MonthlySummary(
            month=month_key,
            income=data['income'],
            expense=data['expense'],
            net=data['income'] - data['expense']
        ))
    
    return response

@router.get("/recent-transactions")
async def get_recent_transactions(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Get most recent approved transactions"""
    
    transactions = db.query(Expense).filter(
        Expense.user_id == current_user.id,
        Expense.status == ExpenseStatus.APPROVED
    ).order_by(
        Expense.bill_date.desc()
    ).limit(limit).all()
    
    return [
        {
            "id": t.id,
            "bill_name": t.bill_name,
            "bill_amount": t.bill_amount,
            "bill_date": t.bill_date,
            "transaction_type": t.transaction_type,
            "category": t.main_category.value,
            "vendor_name": t.vendor_name
        }
        for t in transactions
    ]

@router.get("/top-categories")
async def get_top_categories(
    limit: int = Query(5, ge=1, le=10),
    transaction_type: TransactionType = TransactionType.EXPENSE,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Get top spending/earning categories"""
    
    # Get last 90 days data
    start_date = datetime.utcnow() - timedelta(days=90)
    
    top_categories = db.query(
        Expense.main_category,
        func.sum(Expense.bill_amount).label('total'),
        func.count(Expense.id).label('count')
    ).filter(
        Expense.user_id == current_user.id,
        Expense.status == ExpenseStatus.APPROVED,
        Expense.transaction_type == transaction_type,
        Expense.bill_date >= start_date
    ).group_by(
        Expense.main_category
    ).order_by(
        func.sum(Expense.bill_amount).desc()
    ).limit(limit).all()
    
    return [
        {
            "category": cat.main_category.value,
            "total_amount": cat.total,
            "transaction_count": cat.count,
            "average_amount": cat.total / cat.count if cat.count > 0 else 0
        }
        for cat in top_categories
    ]

@router.get("/daily-spending")
async def get_daily_spending(
    days: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Get daily spending for last N days"""
    
    start_date = datetime.utcnow() - timedelta(days=days)
    
    daily_data = db.query(
        func.date(Expense.bill_date).label('date'),
        func.sum(Expense.bill_amount).label('total')
    ).filter(
        Expense.user_id == current_user.id,
        Expense.status == ExpenseStatus.APPROVED,
        Expense.transaction_type == TransactionType.EXPENSE,
        Expense.bill_date >= start_date
    ).group_by(
        func.date(Expense.bill_date)
    ).order_by('date').all()
    
    return [
        {
            "date": data.date,
            "amount": float(data.total) if data.total else 0
        }
        for data in daily_data
    ]

@router.get("/pending-approvals-summary")
async def get_pending_approvals_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Get summary of pending approvals"""
    
    pending = db.query(Expense).filter(
        Expense.user_id == current_user.id,
        Expense.status == ExpenseStatus.PENDING
    ).all()
    
    total_pending_amount = sum(e.bill_amount for e in pending)
    
    # Group by category
    by_category = defaultdict(lambda: {'count': 0, 'total': 0})
    for expense in pending:
        by_category[expense.main_category.value]['count'] += 1
        by_category[expense.main_category.value]['total'] += expense.bill_amount
    
    return {
        "total_pending_count": len(pending),
        "total_pending_amount": total_pending_amount,
        "by_category": dict(by_category),
        "oldest_pending": min([e.bill_date for e in pending]) if pending else None,
        "newest_pending": max([e.bill_date for e in pending]) if pending else None
    }

@router.get("/ocr-statistics")
async def get_ocr_statistics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Get statistics about OCR scanned bills"""
    
    ocr_expenses = db.query(Expense).filter(
        Expense.user_id == current_user.id,
        Expense.upload_method == "ocr"
    ).all()
    
    total_scanned = len(ocr_expenses)
    approved_scanned = len([e for e in ocr_expenses if e.status == ExpenseStatus.APPROVED])
    pending_scanned = len([e for e in ocr_expenses if e.status == ExpenseStatus.PENDING])
    
    total_ocr_amount = sum(e.bill_amount for e in ocr_expenses if e.status == ExpenseStatus.APPROVED)
    
    # Get average confidence scores from OCR bills table
    from app.models import OCRBill
    
    avg_confidence = db.query(func.avg(OCRBill.confidence_score)).filter(
        OCRBill.user_id == current_user.id
    ).scalar()
    
    return {
        "total_ocr_scans": total_scanned,
        "approved_ocr_scans": approved_scanned,
        "pending_ocr_scans": pending_scanned,
        "total_ocr_amount": total_ocr_amount,
        "average_confidence_score": round(avg_confidence or 0, 2),
        "approval_rate": round((approved_scanned / total_scanned * 100) if total_scanned > 0 else 0, 2)
    }

@router.get("/budget-vs-actual")
async def get_budget_vs_actual(
    month: Optional[str] = None,  # Format: YYYY-MM
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Compare actual spending vs budget (you'll need to add budget table)"""
    
    # Set month to current if not specified
    if not month:
        month = datetime.utcnow().strftime("%Y-%m")
    
    year, month_num = map(int, month.split('-'))
    
    # Get actual spending for the month
    start_date = datetime(year, month_num, 1)
    if month_num == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month_num + 1, 1)
    
    actual_spending = db.query(
        Expense.main_category,
        func.sum(Expense.bill_amount).label('actual')
    ).filter(
        Expense.user_id == current_user.id,
        Expense.status == ExpenseStatus.APPROVED,
        Expense.transaction_type == TransactionType.EXPENSE,
        Expense.bill_date.between(start_date, end_date)
    ).group_by(Expense.main_category).all()
    
    # For now, return actual spending (you can create a Budget model later)
    return {
        "month": month,
        "categories": [
            {
                "category": cat.main_category.value,
                "actual": float(cat.actual),
                "budget": None  # To be implemented with budget table
            }
            for cat in actual_spending
        ]
    }

@router.get("/export-data")
async def export_expense_data(
    start_date: datetime,
    end_date: datetime,
    format: str = Query("json", regex="^(json|csv)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Export expense data in JSON or CSV format"""
    
    expenses = db.query(Expense).filter(
        Expense.user_id == current_user.id,
        Expense.status == ExpenseStatus.APPROVED,
        Expense.bill_date.between(start_date, end_date)
    ).all()
    
    export_data = []
    for expense in expenses:
        export_data.append({
            "id": expense.id,
            "bill_name": expense.bill_name,
            "bill_amount": expense.bill_amount,
            "bill_date": expense.bill_date.isoformat(),
            "transaction_type": expense.transaction_type.value,
            "category": expense.main_category.value,
            "description": expense.description,
            "vendor_name": expense.vendor_name,
            "payment_method": expense.payment_method.value if expense.payment_method else None,
            "created_at": expense.created_at.isoformat(),
            "approved_at": expense.approved_at.isoformat() if expense.approved_at else None
        })
    
    if format == "csv":
        # Convert to CSV format
        import csv
        from fastapi.responses import StreamingResponse
        from io import StringIO
        
        output = StringIO()
        if export_data:
            writer = csv.DictWriter(output, fieldnames=export_data[0].keys())
            writer.writeheader()
            writer.writerows(export_data)
        
        response = StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv"
        )
        response.headers["Content-Disposition"] = f"attachment; filename=expenses_{start_date.date()}_{end_date.date()}.csv"
        return response
    else:
        return export_data

@router.get("/quick-insights")
async def get_quick_insights(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_default_user),
):
    """Get AI-powered quick insights (simplified version)"""
    
    # Get last 30 days data
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30)
    
    expenses = db.query(Expense).filter(
        Expense.user_id == current_user.id,
        Expense.status == ExpenseStatus.APPROVED,
        Expense.transaction_type == TransactionType.EXPENSE,
        Expense.bill_date.between(start_date, end_date)
    ).all()
    
    if not expenses:
        return {"message": "No expense data available for insights"}
    
    # Find highest spending category
    category_totals = defaultdict(float)
    for expense in expenses:
        category_totals[expense.main_category.value] += expense.bill_amount
    
    top_category = max(category_totals, key=category_totals.get)
    
    # Calculate average daily spending
    total_spent = sum(e.bill_amount for e in expenses)
    avg_daily = total_spent / 30
    
    # Find biggest single expense
    biggest_expense = max(expenses, key=lambda e: e.bill_amount)
    
    # Count transactions by category
    transaction_counts = defaultdict(int)
    for expense in expenses:
        transaction_counts[expense.main_category.value] += 1
    
    most_frequent_category = max(transaction_counts, key=transaction_counts.get)
    
    return {
        "top_spending_category": {
            "category": top_category,
            "amount": category_totals[top_category]
        },
        "average_daily_spending": round(avg_daily, 2),
        "biggest_expense": {
            "name": biggest_expense.bill_name,
            "amount": biggest_expense.bill_amount,
            "category": biggest_expense.main_category.value,
            "date": biggest_expense.bill_date
        },
        "most_frequent_category": {
            "category": most_frequent_category,
            "count": transaction_counts[most_frequent_category]
        },
        "total_transactions": len(expenses),
        "total_spent": total_spent
    }