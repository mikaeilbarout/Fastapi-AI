import os

import main


async def signup_and_get_headers(client, email):
    res = await client.post("/signup", json={
        "username": "Image User", "email": email, "password": "Passw0rd123",
    })
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_generate_image_saves_file_and_persists_url(client, monkeypatch):
    fake_bytes = b"fake-png-bytes"
    monkeypatch.setattr(
        main.ai_platform_gemini.__class__,
        "generate_image",
        lambda self, prompt: (fake_bytes, "image/png"),
    )

    headers = await signup_and_get_headers(client, "imagegen@example.com")
    session_id = (await client.post("/sessions", json={}, headers=headers)).json()["id"]

    res = await client.post(
        "/generate-image", json={"prompt": "a red apple", "session_id": session_id}, headers=headers
    )
    assert res.status_code == 200
    image_url = res.json()["image_url"]
    assert image_url.startswith("/static/photos/")

    file_path = os.path.join(main.BASE_DIR, image_url.lstrip("/"))
    try:
        assert os.path.isfile(file_path)
        with open(file_path, "rb") as f:
            assert f.read() == fake_bytes

        messages = (await client.get(f"/sessions/{session_id}/messages", headers=headers)).json()
        assert messages == [
            {"role": "user", "content": "a red apple"},
            {"role": "assistant", "content": image_url},
        ]
    finally:
        os.remove(file_path)


async def test_generate_image_no_image_returned_gives_clean_json_error(client, monkeypatch):
    # Regression: aimodel.Gemini.generate_image raises a plain ValueError
    # when the model returns no image, which wasn't caught by the endpoint's
    # `except errors.ClientError` — that turned into an unhandled 500 with a
    # plain-text body, which broke the frontend's `res.json()`.
    def raise_no_image(self, prompt):
        raise ValueError("The model did not return an image for this prompt.")

    monkeypatch.setattr(main.ai_platform_gemini.__class__, "generate_image", raise_no_image)

    headers = await signup_and_get_headers(client, "imagegenerror@example.com")
    session_id = (await client.post("/sessions", json={}, headers=headers)).json()["id"]

    res = await client.post(
        "/generate-image", json={"prompt": "x", "session_id": session_id}, headers=headers
    )
    assert res.status_code == 502
    assert res.json() == {"detail": "Image generation failed. Please try again later."}
