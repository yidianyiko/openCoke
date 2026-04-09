from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "fake_wechat_provider.py"
)
SPEC = spec_from_file_location("fake_wechat_provider", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_fake_wechat_provider_prefixes_generated_ids_with_instance_nonce():
    app = MODULE.create_app(
        public_base_url="http://127.0.0.1:19090",
        instance_nonce="run_a",
    )
    client = app.test_client()

    qr_payload = client.get("/ilink/bot/get_bot_qrcode").get_json()
    qrcode = qr_payload["qrcode"]
    confirm_payload = client.post("/__e2e/confirm", json={"qrcode": qrcode}).get_json()

    assert qrcode == "qr_run_a_1"
    assert confirm_payload["bot_token"] == "bot_run_a_1"


def test_fake_wechat_provider_uses_distinct_nonces_across_instances():
    app_a = MODULE.create_app(
        public_base_url="http://127.0.0.1:19090",
        instance_nonce="run_a",
    )
    app_b = MODULE.create_app(
        public_base_url="http://127.0.0.1:19090",
        instance_nonce="run_b",
    )

    qr_a = app_a.test_client().get("/ilink/bot/get_bot_qrcode").get_json()["qrcode"]
    qr_b = app_b.test_client().get("/ilink/bot/get_bot_qrcode").get_json()["qrcode"]

    assert qr_a == "qr_run_a_1"
    assert qr_b == "qr_run_b_1"
    assert qr_a != qr_b
