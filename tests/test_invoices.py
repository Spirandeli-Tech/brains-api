from datetime import date


def _create_customer(client, legal_name="Acme Corp"):
    resp = client.post("/customers", json={"legal_name": legal_name})
    assert resp.status_code == 201
    return resp.json()


def _create_invoice(client, customer_id, **overrides):
    payload = {
        "customer_id": customer_id,
        "issue_date": "2025-01-01",
        "due_date": "2025-01-31",
        "service_title": "Web Development",
        "service_description": "Full-stack development services",
        "amount_total": 5000.00,
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


# --- Happy path tests ---

def test_create_customer_and_invoice(client_a):
    # Create customer
    customer = _create_customer(client_a, "Test Corp")
    assert customer["legal_name"] == "Test Corp"
    assert "id" in customer

    # Create invoice
    resp = _create_invoice(client_a, customer["id"])
    assert resp.status_code == 201
    invoice = resp.json()
    assert invoice["customer"]["legal_name"] == "Test Corp"
    assert invoice["service_title"] == "Web Development"
    assert float(invoice["amount_total"]) == 5000.00
    assert invoice["status"] == "draft"
    assert invoice["currency"] == "USD"

    # Verify invoice appears in list
    list_resp = client_a.get("/invoices")
    assert list_resp.status_code == 200
    invoices = list_resp.json()
    assert len(invoices) == 1
    assert invoices[0]["id"] == invoice["id"]


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


def test_create_invoice_validates_amount(client_a):
    customer = _create_customer(client_a, "Validation Corp")
    resp = _create_invoice(client_a, customer["id"], amount_total=-100)
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
