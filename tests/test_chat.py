import main
from config import settings


async def test_anonymous_chat_gets_a_guest_cookie(client, monkeypatch):
    monkeypatch.setattr(main.ai_platform_gemini.__class__, "chat", lambda self, prompt: "mocked reply")

    res = await client.post("/chat", json={"message": "hello"})
    assert res.status_code == 200
    assert res.json()["response"] == "mocked reply"
    assert "guest_id" in client.cookies


async def test_chat_remembers_history_across_requests(client, monkeypatch):
    seen_prompts = []

    def fake_chat(self, prompt):
        seen_prompts.append(prompt)
        return f"reply-{len(seen_prompts)}"

    monkeypatch.setattr(main.ai_platform_gemini.__class__, "chat", fake_chat)

    await client.post("/chat", json={"message": "my name is Ali"})
    await client.post("/chat", json={"message": "what is my name?"})

    assert "my name is Ali" in seen_prompts[1]
    assert "reply-1" in seen_prompts[1]


async def test_rate_limit_blocks_after_threshold(client, monkeypatch):
    monkeypatch.setattr(main.ai_platform_gemini.__class__, "chat", lambda self, prompt: "ok")

    for _ in range(settings.GLOBAL_RATE_LIMIT):
        res = await client.post("/chat", json={"message": "x"})
        assert res.status_code == 200

    res = await client.post("/chat", json={"message": "x"})
    assert res.status_code == 429


async def test_different_guests_get_isolated_history(client, monkeypatch):
    # Regression: every anonymous visitor used to share one "global_user"
    # Redis key, so guests could see each other's conversation.
    seen_prompts = []

    def fake_chat(self, prompt):
        seen_prompts.append(prompt)
        return f"reply-{len(seen_prompts)}"

    monkeypatch.setattr(main.ai_platform_gemini.__class__, "chat", fake_chat)

    await client.post("/chat", json={"message": "guest one secret"})

    client.cookies.delete("guest_id")
    await client.post("/chat", json={"message": "guest two message"})

    assert "guest one secret" not in seen_prompts[1]


async def test_different_guests_have_independent_rate_limits(client, monkeypatch):
    monkeypatch.setattr(main.ai_platform_gemini.__class__, "chat", lambda self, prompt: "ok")

    for _ in range(settings.GLOBAL_RATE_LIMIT):
        res = await client.post("/chat", json={"message": "x"})
        assert res.status_code == 200
    blocked = await client.post("/chat", json={"message": "x"})
    assert blocked.status_code == 429

    client.cookies.delete("guest_id")
    res = await client.post("/chat", json={"message": "x"})
    assert res.status_code == 200
