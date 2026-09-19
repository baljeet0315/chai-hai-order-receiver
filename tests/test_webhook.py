from fastapi.testclient import TestClient

import app.main as main


def test_verify_handshake(monkeypatch):
    monkeypatch.setattr(main, "settings", type("S", (), {"wa_verify_token": "abc", "wa_app_secret": ""})())
    client = TestClient(main.app)
    ok = client.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "abc", "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    bad = client.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "42"})
    assert bad.status_code == 403


def test_post_rejects_bad_signature(monkeypatch):
    monkeypatch.setattr(main, "settings", type("S", (), {"wa_verify_token": "abc", "wa_app_secret": "secret"})())
    client = TestClient(main.app)
    assert client.post("/webhook", json={"entry": []}, headers={"X-Hub-Signature-256": "sha256=bad"}).status_code == 401


def test_health():
    assert TestClient(main.app).get("/health").json() == {"ok": True}
