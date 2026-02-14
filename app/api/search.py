from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.models.bank_account import BankAccount
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.invoice_service import InvoiceService
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.search import SearchResponse, SearchResultGroup, SearchResultItem

router = APIRouter(prefix="/search", tags=["search"])

MAX_RESULTS_PER_CATEGORY = 3


@router.get("", response_model=SearchResponse)
def global_search(
    q: str = Query(..., min_length=1, description="Search query"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pattern = f"%{q}%"
    data: list[SearchResultGroup] = []

    # Invoices — search by invoice_number or customer legal_name
    invoices = (
        db.query(Invoice)
        .join(Customer, Invoice.customer_id == Customer.id)
        .filter(
            Invoice.created_by_user_id == current_user.id,
            Invoice.invoice_number.ilike(pattern) | Customer.legal_name.ilike(pattern),
        )
        .order_by(Invoice.issue_date.desc())
        .limit(MAX_RESULTS_PER_CATEGORY)
        .all()
    )
    if invoices:
        data.append(
            SearchResultGroup(
                type="invoices",
                items=[
                    SearchResultItem(
                        id=str(inv.id),
                        title=inv.invoice_number,
                        subtitle=inv.customer.legal_name if inv.customer else None,
                    )
                    for inv in invoices
                ],
            )
        )

    # Customers — search by legal_name or display_name
    customers = (
        db.query(Customer)
        .filter(
            Customer.created_by_user_id == current_user.id,
            Customer.legal_name.ilike(pattern) | Customer.display_name.ilike(pattern),
        )
        .order_by(Customer.legal_name)
        .limit(MAX_RESULTS_PER_CATEGORY)
        .all()
    )
    if customers:
        data.append(
            SearchResultGroup(
                type="customers",
                items=[
                    SearchResultItem(
                        id=str(c.id),
                        title=c.legal_name,
                        subtitle=c.email,
                    )
                    for c in customers
                ],
            )
        )

    # Bank Accounts — search by label or bank_name
    bank_accounts = (
        db.query(BankAccount)
        .filter(
            BankAccount.created_by_user_id == current_user.id,
            BankAccount.label.ilike(pattern) | BankAccount.bank_name.ilike(pattern),
        )
        .order_by(BankAccount.label)
        .limit(MAX_RESULTS_PER_CATEGORY)
        .all()
    )
    if bank_accounts:
        data.append(
            SearchResultGroup(
                type="banks",
                items=[
                    SearchResultItem(
                        id=str(ba.id),
                        title=ba.label,
                        subtitle=ba.bank_name,
                    )
                    for ba in bank_accounts
                ],
            )
        )

    # Services — search by service_title (template services only)
    services = (
        db.query(InvoiceService)
        .filter(
            InvoiceService.created_by_user_id == current_user.id,
            InvoiceService.invoice_id.is_(None),
            InvoiceService.service_title.ilike(pattern),
        )
        .order_by(InvoiceService.service_title)
        .limit(MAX_RESULTS_PER_CATEGORY)
        .all()
    )
    if services:
        data.append(
            SearchResultGroup(
                type="services",
                items=[
                    SearchResultItem(
                        id=str(s.id),
                        title=s.service_title,
                        subtitle=f"${s.amount:,.2f}" if s.amount else None,
                    )
                    for s in services
                ],
            )
        )

    # Transactions — search by description
    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.created_by_user_id == current_user.id,
            Transaction.description.ilike(pattern),
        )
        .order_by(Transaction.date.desc())
        .limit(MAX_RESULTS_PER_CATEGORY)
        .all()
    )
    if transactions:
        data.append(
            SearchResultGroup(
                type="transactions",
                items=[
                    SearchResultItem(
                        id=str(t.id),
                        title=t.description,
                        subtitle=f"{'+'if t.type=='income' else '-'}{t.currency} {t.amount:,.2f}",
                    )
                    for t in transactions
                ],
            )
        )

    # Users — only if current user is ADMIN
    if current_user.role and current_user.role.name == "ADMIN":
        users = (
            db.query(User)
            .filter(
                User.email.ilike(pattern)
                | User.first_name.ilike(pattern)
                | User.last_name.ilike(pattern),
            )
            .order_by(User.first_name)
            .limit(MAX_RESULTS_PER_CATEGORY)
            .all()
        )
        if users:
            data.append(
                SearchResultGroup(
                    type="users",
                    items=[
                        SearchResultItem(
                            id=str(u.id),
                            title=f"{u.first_name} {u.last_name}",
                            subtitle=u.email,
                        )
                        for u in users
                    ],
                )
            )

    return SearchResponse(data=data)
