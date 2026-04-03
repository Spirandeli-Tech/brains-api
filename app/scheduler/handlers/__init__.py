from app.scheduler.handlers.generate_contract_invoice import GenerateContractInvoiceHandler

TASK_HANDLERS: dict = {
    "generate_contract_invoice": GenerateContractInvoiceHandler(),
}
