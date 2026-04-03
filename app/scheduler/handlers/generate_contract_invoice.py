import re
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.contract import Contract
from app.models.invoice import Invoice
from app.models.invoice_service import InvoiceService
from app.models.recurring_task import RecurringTask
from app.models.task_execution import TaskExecution
from app.scheduler.handlers.base import TaskHandler


def _generate_invoice_number(db: Session, user_id: uuid.UUID) -> str:
    latest = (
        db.query(func.max(Invoice.invoice_number))
        .filter(Invoice.created_by_user_id == user_id)
        .scalar()
    )
    if latest:
        match = re.search(r"(\d+)$", latest)
        next_num = int(match.group(1)) + 1 if match else 1
    else:
        next_num = 1
    return f"INV-{next_num:06d}"


class GenerateContractInvoiceHandler(TaskHandler):
    def execute(
        self,
        db: Session,
        task: RecurringTask,
        execution: TaskExecution,
    ) -> uuid.UUID | None:
        contract = (
            db.query(Contract)
            .filter(Contract.id == task.reference_id)
            .first()
        )
        if not contract:
            raise ValueError(f"Contract {task.reference_id} not found")

        if contract.status != "active":
            raise ValueError(f"Contract {task.reference_id} is not active")

        issue_date = execution.scheduled_for
        due_date = issue_date + timedelta(days=30)
        monthly_value = (contract.annual_value / Decimal(12)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        new_invoice = Invoice(
            created_by_user_id=task.user_id,
            customer_id=contract.customer_id,
            bank_account_id=contract.bank_account_id,
            invoice_number=_generate_invoice_number(db, task.user_id),
            issue_date=issue_date,
            due_date=due_date,
            currency=contract.currency,
            status="draft",
            total_amount=monthly_value,
            notes=contract.notes,
            contract_id=contract.id,
        )
        db.add(new_invoice)
        db.flush()

        for svc in contract.services:
            new_service = InvoiceService(
                created_by_user_id=task.user_id,
                invoice_id=new_invoice.id,
                service_title=svc.service_title,
                service_description=svc.service_description,
                sort_order=svc.sort_order,
            )
            db.add(new_service)

        db.commit()
        return new_invoice.id
