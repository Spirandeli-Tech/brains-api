def _create_customer(client, legal_name="Acme Corp"):
    resp = client.post("/customers", json={"legal_name": legal_name})
    assert resp.status_code == 201
    return resp.json()


def _create_bank_account(client, label="USD Account"):
    resp = client.post("/bank-accounts", json={
        "label": label,
        "beneficiary_full_name": "Test Company Inc.",
        "beneficiary_account_number": "123456789",
        "swift_code": "CITIUS33",
    })
    assert resp.status_code == 201
    return resp.json()


def _create_invoice(client, customer_id, **overrides):
    payload = {
        "customer_id": customer_id,
        "issue_date": "2025-01-01",
        "due_date": "2025-01-31",
        "services": [
            {
                "service_title": "Web Development",
                "service_description": "Full-stack development services",
                "amount": 5000.00,
            }
        ],
        **overrides,
    }
    resp = client.post("/invoices", json=payload)
    return resp


# --- Auth tests ---

def test_list_invoices_unauthenticated(unauthenticated_client):
    resp = unauthenticated_client.get("/invoices")
    assert resp.status_code in (401, 403)


def test_list_customers_unauthenticated(unauthenticated_client):
    resp = unauthenticated_client.get("/customers")
    assert resp.status_code in (401, 403)


def test_list_bank_accounts_unauthenticated(unauthenticated_client):
    resp = unauthenticated_client.get("/bank-accounts")
    assert resp.status_code in (401, 403)


# --- Multi-tenancy tests ---

def test_user_a_cannot_see_user_b_customer(client_a, client_b):
    customer = _create_customer(client_a, "User A Customer")
    resp = client_b.get(f"/customers/{customer['id']}")
    assert resp.status_code == 404


def test_user_a_cannot_see_user_b_invoice(client_a, client_b):
    customer = _create_customer(client_a, "User A Customer")
    invoice_resp = _create_invoice(client_a, customer["id"])
    assert invoice_resp.status_code == 201
    invoice = invoice_resp.json()

    resp = client_b.get(f"/invoices/{invoice['id']}")
    assert resp.status_code == 404


def test_user_b_cannot_delete_user_a_customer(client_a, client_b):
    customer = _create_customer(client_a, "User A Customer")
    resp = client_b.delete(f"/customers/{customer['id']}")
    assert resp.status_code == 404


def test_bank_account_tenant_isolation(client_a, client_b):
    account = _create_bank_account(client_a, "User A Account")
    resp = client_b.get(f"/bank-accounts/{account['id']}")
    assert resp.status_code == 404

    # User B cannot see in list either
    resp = client_b.get("/bank-accounts")
    assert resp.status_code == 200
    assert len(resp.json()) == 0


# --- Happy path tests ---

def test_create_customer_and_invoice(client_a):
    # Create customer
    customer = _create_customer(client_a, "Test Corp")
    assert customer["legal_name"] == "Test Corp"
    assert "id" in customer

    # Create invoice with services
    resp = _create_invoice(client_a, customer["id"])
    assert resp.status_code == 201
    invoice = resp.json()
    assert invoice["customer"]["legal_name"] == "Test Corp"
    assert len(invoice["services"]) == 1
    assert invoice["services"][0]["service_title"] == "Web Development"
    assert float(invoice["services"][0]["amount"]) == 5000.00
    assert float(invoice["total_amount"]) == 5000.00
    assert invoice["status"] == "draft"
    assert invoice["currency"] == "USD"
    assert invoice["bank_account"] is None

    # Verify invoice appears in list
    list_resp = client_a.get("/invoices")
    assert list_resp.status_code == 200
    invoices = list_resp.json()
    assert len(invoices) == 1
    assert invoices[0]["id"] == invoice["id"]
    assert float(invoices[0]["total_amount"]) == 5000.00


def test_create_invoice_with_multiple_services(client_a):
    customer = _create_customer(client_a, "Multi Service Corp")
    resp = _create_invoice(client_a, customer["id"], services=[
        {"service_title": "Design", "service_description": "UI/UX Design", "amount": 3000.00},
        {"service_title": "Development", "service_description": "Frontend dev", "amount": 7000.00},
        {"service_title": "QA", "service_description": "Testing", "amount": 2000.00},
    ])
    assert resp.status_code == 201
    invoice = resp.json()
    assert len(invoice["services"]) == 3
    assert float(invoice["total_amount"]) == 12000.00

    # Verify sort order
    assert invoice["services"][0]["service_title"] == "Design"
    assert invoice["services"][1]["service_title"] == "Development"
    assert invoice["services"][2]["service_title"] == "QA"


def test_create_invoice_with_bank_account(client_a):
    customer = _create_customer(client_a, "Bank Account Corp")
    bank_account = _create_bank_account(client_a, "Main USD Account")

    resp = _create_invoice(client_a, customer["id"], bank_account_id=bank_account["id"])
    assert resp.status_code == 201
    invoice = resp.json()
    assert invoice["bank_account"] is not None
    assert invoice["bank_account"]["label"] == "Main USD Account"
    assert invoice["bank_account"]["swift_code"] == "CITIUS33"


def test_invoice_number_auto_generation(client_a):
    customer = _create_customer(client_a, "Auto Number Corp")

    resp1 = _create_invoice(client_a, customer["id"])
    assert resp1.status_code == 201
    assert resp1.json()["invoice_number"] == "INV-000001"

    resp2 = _create_invoice(client_a, customer["id"])
    assert resp2.status_code == 201
    assert resp2.json()["invoice_number"] == "INV-000002"


def test_delete_customer_with_invoices_blocked(client_a):
    customer = _create_customer(client_a, "Delete Test Corp")
    _create_invoice(client_a, customer["id"])

    resp = client_a.delete(f"/customers/{customer['id']}")
    assert resp.status_code == 409
    assert "invoices" in resp.json()["detail"].lower()


def test_delete_customer_without_invoices(client_a):
    customer = _create_customer(client_a, "No Invoice Corp")
    resp = client_a.delete(f"/customers/{customer['id']}")
    assert resp.status_code == 204


def test_create_invoice_no_services_fails(client_a):
    customer = _create_customer(client_a, "No Service Corp")
    resp = _create_invoice(client_a, customer["id"], services=[])
    assert resp.status_code == 422


def test_create_invoice_service_amount_zero_fails(client_a):
    customer = _create_customer(client_a, "Zero Amount Corp")
    resp = _create_invoice(client_a, customer["id"], services=[
        {"service_title": "Free Work", "amount": 0},
    ])
    assert resp.status_code == 422


def test_create_invoice_validates_due_date(client_a):
    customer = _create_customer(client_a, "Date Corp")
    resp = _create_invoice(
        client_a,
        customer["id"],
        issue_date="2025-02-01",
        due_date="2025-01-01",
    )
    assert resp.status_code == 422


def test_customer_search(client_a):
    _create_customer(client_a, "Alpha Corp")
    _create_customer(client_a, "Beta Inc")

    resp = client_a.get("/customers?q=alpha")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["legal_name"] == "Alpha Corp"


def test_update_invoice(client_a):
    customer = _create_customer(client_a, "Update Corp")
    invoice_resp = _create_invoice(client_a, customer["id"])
    invoice = invoice_resp.json()

    resp = client_a.put(f"/invoices/{invoice['id']}", json={"status": "sent"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"


def test_update_invoice_replaces_services(client_a):
    customer = _create_customer(client_a, "Replace Services Corp")
    invoice_resp = _create_invoice(client_a, customer["id"], services=[
        {"service_title": "Old Service", "amount": 1000.00},
    ])
    invoice = invoice_resp.json()
    assert float(invoice["total_amount"]) == 1000.00

    # Replace with new services
    resp = client_a.put(f"/invoices/{invoice['id']}", json={
        "services": [
            {"service_title": "New Service A", "amount": 2000.00},
            {"service_title": "New Service B", "amount": 3000.00},
        ]
    })
    assert resp.status_code == 200
    updated = resp.json()
    assert len(updated["services"]) == 2
    assert float(updated["total_amount"]) == 5000.00
    assert updated["services"][0]["service_title"] == "New Service A"


# --- Bank Account CRUD tests ---

def test_create_bank_account(client_a):
    resp = client_a.post("/bank-accounts", json={
        "label": "EUR Account",
        "beneficiary_full_name": "Test GmbH",
        "beneficiary_account_number": "DE89370400440532013000",
        "swift_code": "COBADEFFXXX",
        "bank_name": "Commerzbank",
    })
    assert resp.status_code == 201
    account = resp.json()
    assert account["label"] == "EUR Account"
    assert account["swift_code"] == "COBADEFFXXX"
    assert account["bank_name"] == "Commerzbank"


def test_create_bank_account_duplicate_label(client_a):
    _create_bank_account(client_a, "Duplicate Label")
    resp = client_a.post("/bank-accounts", json={
        "label": "Duplicate Label",
        "beneficiary_full_name": "Test Inc.",
        "beneficiary_account_number": "999999",
        "swift_code": "TESTUS00",
    })
    assert resp.status_code == 409


def test_delete_bank_account_with_invoices_blocked(client_a):
    customer = _create_customer(client_a, "Bank Delete Corp")
    bank_account = _create_bank_account(client_a, "Referenced Account")
    _create_invoice(client_a, customer["id"], bank_account_id=bank_account["id"])

    resp = client_a.delete(f"/bank-accounts/{bank_account['id']}")
    assert resp.status_code == 409


def test_delete_bank_account_without_invoices(client_a):
    bank_account = _create_bank_account(client_a, "Deletable Account")
    resp = client_a.delete(f"/bank-accounts/{bank_account['id']}")
    assert resp.status_code == 204


def test_update_bank_account(client_a):
    bank_account = _create_bank_account(client_a, "Updatable Account")
    resp = client_a.put(f"/bank-accounts/{bank_account['id']}", json={
        "bank_name": "Updated Bank Name",
    })
    assert resp.status_code == 200
    assert resp.json()["bank_name"] == "Updated Bank Name"
    assert resp.json()["label"] == "Updatable Account"  # unchanged


# --- Recurrence tests ---

def test_create_recurrent_invoice_monthly(client_a):
    customer = _create_customer(client_a, "Monthly Corp")
    resp = _create_invoice(
        client_a, customer["id"],
        is_recurrent=True,
        recurrence_frequency="monthly",
        recurrence_day=15,
    )
    assert resp.status_code == 201
    invoice = resp.json()
    assert invoice["is_recurrent"] is True
    assert invoice["recurrence_frequency"] == "monthly"
    assert invoice["recurrence_day"] == 15


def test_create_recurrent_invoice_weekly(client_a):
    customer = _create_customer(client_a, "Weekly Corp")
    resp = _create_invoice(
        client_a, customer["id"],
        is_recurrent=True,
        recurrence_frequency="weekly",
        recurrence_day=2,
    )
    assert resp.status_code == 201
    invoice = resp.json()
    assert invoice["is_recurrent"] is True
    assert invoice["recurrence_frequency"] == "weekly"
    assert invoice["recurrence_day"] == 2


def test_create_recurrent_invoice_daily(client_a):
    customer = _create_customer(client_a, "Daily Corp")
    resp = _create_invoice(
        client_a, customer["id"],
        is_recurrent=True,
        recurrence_frequency="daily",
    )
    assert resp.status_code == 201
    invoice = resp.json()
    assert invoice["is_recurrent"] is True
    assert invoice["recurrence_frequency"] == "daily"
    assert invoice["recurrence_day"] is None


def test_create_non_recurrent_invoice_defaults(client_a):
    customer = _create_customer(client_a, "Default Corp")
    resp = _create_invoice(client_a, customer["id"])
    assert resp.status_code == 201
    invoice = resp.json()
    assert invoice["is_recurrent"] is False
    assert invoice["recurrence_frequency"] is None
    assert invoice["recurrence_day"] is None


def test_create_recurrent_without_frequency_fails(client_a):
    customer = _create_customer(client_a, "No Freq Corp")
    resp = _create_invoice(
        client_a, customer["id"],
        is_recurrent=True,
    )
    assert resp.status_code == 422


def test_create_recurrent_weekly_invalid_day_fails(client_a):
    customer = _create_customer(client_a, "Bad Weekly Corp")
    resp = _create_invoice(
        client_a, customer["id"],
        is_recurrent=True,
        recurrence_frequency="weekly",
        recurrence_day=9,
    )
    assert resp.status_code == 422


def test_create_recurrent_monthly_invalid_day_fails(client_a):
    customer = _create_customer(client_a, "Bad Monthly Corp")
    resp = _create_invoice(
        client_a, customer["id"],
        is_recurrent=True,
        recurrence_frequency="monthly",
        recurrence_day=32,
    )
    assert resp.status_code == 422


def test_update_invoice_toggle_recurrence(client_a):
    customer = _create_customer(client_a, "Toggle Corp")
    invoice_resp = _create_invoice(client_a, customer["id"])
    invoice = invoice_resp.json()
    assert invoice["is_recurrent"] is False

    # Enable recurrence
    resp = client_a.put(f"/invoices/{invoice['id']}", json={
        "is_recurrent": True,
        "recurrence_frequency": "monthly",
        "recurrence_day": 1,
    })
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["is_recurrent"] is True
    assert updated["recurrence_frequency"] == "monthly"
    assert updated["recurrence_day"] == 1

    # Disable recurrence
    resp = client_a.put(f"/invoices/{invoice['id']}", json={
        "is_recurrent": False,
    })
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["is_recurrent"] is False
    assert updated["recurrence_frequency"] is None
    assert updated["recurrence_day"] is None
