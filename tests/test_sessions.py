import main


async def signup_and_get_headers(client, email):
    res = await client.post("/signup", json={
        "username": "Session User", "email": email, "password": "Passw0rd123",
    })
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_create_session_requires_login(client):
    res = await client.post("/sessions", json={})
    assert res.status_code == 401


async def test_create_and_list_sessions(client):
    headers = await signup_and_get_headers(client, "sessions1@example.com")

    create_res = await client.post("/sessions", json={}, headers=headers)
    assert create_res.status_code == 201
    assert create_res.json()["title"] == "New chat"

    list_res = await client.get("/sessions", headers=headers)
    assert list_res.status_code == 200
    sessions = list_res.json()
    assert len(sessions) == 1
    assert sessions[0]["id"] == create_res.json()["id"]


async def test_chat_without_session_id_rejected_for_logged_in_user(client, monkeypatch):
    monkeypatch.setattr(main.ai_platform_gemini.__class__, "chat", lambda self, prompt: "mocked")
    headers = await signup_and_get_headers(client, "sessions2@example.com")

    res = await client.post("/chat", json={"message": "hi"}, headers=headers)
    assert res.status_code == 400


async def test_first_message_sets_session_title(client, monkeypatch):
    monkeypatch.setattr(main.ai_platform_gemini.__class__, "chat", lambda self, prompt: "mocked reply")
    headers = await signup_and_get_headers(client, "sessions3@example.com")

    session_id = (await client.post("/sessions", json={}, headers=headers)).json()["id"]
    await client.post(
        "/chat", json={"message": "What's the capital of France?", "session_id": session_id}, headers=headers
    )

    sessions = (await client.get("/sessions", headers=headers)).json()
    assert sessions[0]["title"] == "What's the capital of France?"


async def test_get_session_messages_returns_history(client, monkeypatch):
    monkeypatch.setattr(main.ai_platform_gemini.__class__, "chat", lambda self, prompt: "mocked reply")
    headers = await signup_and_get_headers(client, "sessions4@example.com")

    session_id = (await client.post("/sessions", json={}, headers=headers)).json()["id"]
    await client.post(
        "/chat", json={"message": "hello there", "session_id": session_id}, headers=headers
    )

    messages_res = await client.get(f"/sessions/{session_id}/messages", headers=headers)
    assert messages_res.status_code == 200
    messages = messages_res.json()
    assert messages == [
        {"role": "user", "content": "hello there"},
        {"role": "assistant", "content": "mocked reply"},
    ]


async def test_cannot_access_another_users_session(client):
    headers_a = await signup_and_get_headers(client, "sessionowner@example.com")
    headers_b = await signup_and_get_headers(client, "sessionintruder@example.com")

    session_id = (await client.post("/sessions", json={}, headers=headers_a)).json()["id"]

    res = await client.get(f"/sessions/{session_id}/messages", headers=headers_b)
    assert res.status_code == 404


async def test_rename_session_updates_title(client):
    headers = await signup_and_get_headers(client, "sessionrename@example.com")
    session_id = (await client.post("/sessions", json={}, headers=headers)).json()["id"]

    rename_res = await client.patch(
        f"/sessions/{session_id}", json={"new_session_name": "Renamed chat"}, headers=headers
    )
    assert rename_res.status_code == 200
    assert rename_res.json()["title"] == "Renamed chat"

    list_res = await client.get("/sessions", headers=headers)
    assert list_res.json()[0]["title"] == "Renamed chat"


async def test_cannot_rename_another_users_session(client):
    headers_a = await signup_and_get_headers(client, "renameowner@example.com")
    headers_b = await signup_and_get_headers(client, "renameintruder@example.com")

    session_id = (await client.post("/sessions", json={}, headers=headers_a)).json()["id"]

    res = await client.patch(
        f"/sessions/{session_id}", json={"new_session_name": "Hacked"}, headers=headers_b
    )
    assert res.status_code == 404


async def test_delete_session_removes_it(client):
    headers = await signup_and_get_headers(client, "sessiondelete@example.com")
    session_id = (await client.post("/sessions", json={}, headers=headers)).json()["id"]

    delete_res = await client.delete(f"/sessions/{session_id}", headers=headers)
    assert delete_res.status_code == 204

    list_res = await client.get("/sessions", headers=headers)
    assert list_res.json() == []
