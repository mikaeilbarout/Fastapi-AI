import main


async def test_signup_returns_valid_token(client):
    res = await client.post("/signup", json={
        "username": "Test User", "email": "test@example.com", "password": "Passw0rd123",
    })
    assert res.status_code == 201
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert isinstance(data["user_id"], int)


async def test_signup_duplicate_email_rejected(client):
    payload = {"username": "Dup User", "email": "dup@example.com", "password": "Passw0rd123"}
    await client.post("/signup", json=payload)
    res = await client.post("/signup", json=payload)
    assert res.status_code == 409


async def test_login_with_correct_credentials(client):
    await client.post("/signup", json={
        "username": "Login User", "email": "login@example.com", "password": "Passw0rd123",
    })
    res = await client.post("/login", json={"email": "login@example.com", "password": "Passw0rd123"})
    assert res.status_code == 200
    assert "access_token" in res.json()


async def test_login_with_wrong_password_rejected(client):
    await client.post("/signup", json={
        "username": "Login User2", "email": "login2@example.com", "password": "Passw0rd123",
    })
    res = await client.post("/login", json={"email": "login2@example.com", "password": "WrongPass1"})
    assert res.status_code == 401


async def test_signup_token_identifies_user_in_chat(client, monkeypatch):
    # Regression: signup used to encode `sub` as full_name instead of the
    # user id, which crashed /chat's get_user_identifier with a ValueError.
    monkeypatch.setattr(main.ai_platform_gemini.__class__, "chat", lambda self, prompt: "mocked")

    signup_res = await client.post("/signup", json={
        "username": "Chat User", "email": "chatuser@example.com", "password": "Passw0rd123",
    })
    token = signup_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    session_res = await client.post("/sessions", json={}, headers=headers)
    session_id = session_res.json()["id"]

    chat_res = await client.post(
        "/chat", json={"message": "hi", "session_id": session_id}, headers=headers
    )
    assert chat_res.status_code == 200


async def test_login_refresh_token_is_created(client):
    # Regression: create_refresh_token used to require a "user_id" key that
    # login() stopped passing, raising a KeyError on every login.
    await client.post("/signup", json={
        "username": "Refresh User", "email": "refresh@example.com", "password": "Passw0rd123",
    })
    res = await client.post("/login", json={"email": "refresh@example.com", "password": "Passw0rd123"})
    assert res.status_code == 200
    assert "refresh_token" in res.cookies


async def test_refresh_issues_new_access_token(client):
    await client.post("/signup", json={
        "username": "Refresh Flow", "email": "refreshflow@example.com", "password": "Passw0rd123",
    })
    res = await client.post("/refresh")
    assert res.status_code == 200
    assert "access_token" in res.json()


async def test_refresh_rotates_and_invalidates_old_token(client):
    await client.post("/signup", json={
        "username": "Rotate User", "email": "rotate@example.com", "password": "Passw0rd123",
    })
    old_cookie = client.cookies.get("refresh_token")

    first = await client.post("/refresh")
    assert first.status_code == 200
    assert client.cookies.get("refresh_token") != old_cookie

    # Reusing the now-rotated-out old refresh token must fail.
    client.cookies.set("refresh_token", old_cookie)
    second = await client.post("/refresh")
    assert second.status_code == 401


async def test_refresh_without_cookie_fails(client):
    res = await client.post("/refresh")
    assert res.status_code == 401


async def test_logout_revokes_refresh_token(client):
    await client.post("/signup", json={
        "username": "Logout User", "email": "logoutuser@example.com", "password": "Passw0rd123",
    })
    logout_res = await client.post("/logout")
    assert logout_res.status_code == 200

    refresh_res = await client.post("/refresh")
    assert refresh_res.status_code == 401


async def test_expired_token_returns_401_not_500(client):
    from jose import jwt
    from config import settings

    expired = jwt.encode(
        {"sub": "1", "exp": 1, "type": "access"}, settings.secret_key, algorithm=settings.algorithm
    )
    res = await client.post(
        "/chat", json={"message": "hi"}, headers={"Authorization": f"Bearer {expired}"}
    )
    assert res.status_code == 401
