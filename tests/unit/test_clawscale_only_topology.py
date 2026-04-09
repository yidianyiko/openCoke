import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_runtime_configs_remove_legacy_connector_sections():
    runtime_config = json.loads((ROOT / "conf" / "config.json").read_text())
    deploy_config = json.loads(
        (ROOT / "deploy" / "config" / "coke.config.json").read_text()
    )

    assert "ecloud" not in runtime_config
    assert "whatsapp" not in runtime_config
    assert "ecloud" not in deploy_config
    assert "whatsapp" not in deploy_config


def test_compose_and_nginx_expose_only_clawscale_services():
    compose = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text())
    services = compose["services"]

    assert "ecloud-input" not in services
    assert "ecloud-output" not in services
    assert "coke-agent" in services
    assert "coke-bridge" in services
    assert "gateway" in services

    nginx_conf = (ROOT / "deploy" / "nginx" / "coke.conf").read_text()
    assert "/message" not in nginx_conf
    assert "/webhook/creem" not in nginx_conf
    assert "/webhook/stripe" not in nginx_conf
    assert "/webhook/whatsapp" not in nginx_conf


def test_local_runtime_assets_remove_legacy_connectors():
    ecosystem = json.loads((ROOT / "ecosystem.config.json").read_text())
    app_names = {app["name"] for app in ecosystem["apps"]}
    assert app_names == {"coke-agent"}

    start_script = (ROOT / "start.sh").read_text().lower()
    assert "ecloud" not in start_script
    assert "evolution" not in start_script
    assert "whatsapp" not in start_script


def test_legacy_connector_directories_are_removed():
    assert not (ROOT / "connector" / "ecloud").exists()
    assert not (ROOT / "connector" / "adapters" / "ecloud").exists()
    assert not (ROOT / "connector" / "adapters" / "whatsapp").exists()
