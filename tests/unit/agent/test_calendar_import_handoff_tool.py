import types


def test_calendar_import_handoff_client_derives_gateway_url_and_key_from_bridge_config(
    monkeypatch,
):
    from agent.agno_agent.tools import calendar_import_handoff

    monkeypatch.delenv("CALENDAR_IMPORT_HANDOFF_API_URL", raising=False)
    monkeypatch.delenv("CALENDAR_IMPORT_HANDOFF_API_KEY", raising=False)
    monkeypatch.delenv("COKE_GATEWAY_API_URL", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_COKE_API_URL", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_API_URL", raising=False)
    monkeypatch.delenv("CLAWSCALE_IDENTITY_API_KEY", raising=False)

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True, "data": {"url": "https://coke.example/handoff/calendar-import?token=tok"}}

    calls = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return FakeResponse()

    monkeypatch.setattr(calendar_import_handoff.requests, "post", fake_post)
    monkeypatch.setitem(
        __import__("sys").modules,
        "conf.config",
        types.SimpleNamespace(
            CONF={
                "clawscale_bridge": {
                    "identity_api_url": "https://api.example/api/internal/coke-users/provision",
                    "identity_api_key": "secret",
                }
            }
        ),
    )

    link = calendar_import_handoff.create_calendar_import_handoff_link({"source_customer_id": "ck_1"})

    assert link == "https://coke.example/handoff/calendar-import?token=tok"
    assert calls[0]["url"] == "https://api.example/api/internal/calendar-import-handoffs"
    assert calls[0]["headers"]["Authorization"] == "Bearer secret"
