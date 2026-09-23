"""
Tests for POST /signup and POST /login.
No auth headers needed anywhere here — these endpoints ARE what PRODUCES them.
"""

def test_signup_creates_buyer(client):
    response = client.post("/signup", json={
        "email": "newbuyer@test.com",
        "password": "securepass123",
        "role": "buyer"
    })
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "newbuyer@test.com"
    assert body["role"] == "buyer"
    assert "password" not in body
    assert "hashed_pwd" not in body

def test_signup_creates_seller(client):
    response = client.post("/signup", json={
        "email": "newseller@test.com",
        "password": "securepass123",
        "role": "seller"
    })
    assert response.status_code == 201
    assert response.json()["role"] == "seller"

def test_signup_rejects_invalid_role(client):
    response = client.post("/signup", json={
        "email": "bad@test.com",
        "password": "securepass123",
        "role": "superuser"
    })
    assert response.status_code == 422

def test_signup_duplicate_email_rejected(client):
    payload = {"email": "dupe@test.com", "password": "pass12345", "role": "buyer"}
    first = client.post("/signup", json=payload)
    assert first.status_code == 201

    second = client.post("/signup", json=payload)
    assert second.status_code == 400
    assert "already registered" in second.json()["detail"].lower()

def test_login_success_returns_jwt(client):
    client.post("/signup", json={"email": "loginme@test.com", "password": "pass12345", "role": "buyer"})

    # /login uses OAuth2PasswordRequestForm — that's FORM-encoded data
    # (`data=...`), NOT a JSON body. Sending this as `json=` would 422.
    response = client.post("/login", data={"username": "loginme@test.com", "password": "pass12345"})
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"

def test_login_wrong_password_rejected(client):
    client.post("/signup", json={"email": "wrongpass@test.com", "password": "correct123", "role": "buyer"})
 
    response = client.post("/login", data={"username": "wrongpass@test.com", "password": "incorrect"})
    # Your auth.py deliberately raises HTTP_403_FORBIDDEN here (not the more
    # common 401) — this test documents that as the actual current behavior.
    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid Credentials"

def test_login_unknown_email_rejected(client):
    response = client.post("/login", data={"username": "doesnotexist@test.com", "password": "whatever"})
    assert response.status_code == 403
 