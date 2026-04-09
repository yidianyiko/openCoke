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
    assert "channels" not in runtime_config
    assert "channels" not in deploy_config

    runtime_bridge = runtime_config["clawscale_bridge"]
    deploy_bridge = deploy_config["clawscale_bridge"]
    assert "bind_base_url" not in runtime_bridge
    assert "wechat_public_connect_url_template" not in runtime_bridge
    assert "wechat_bind_session_ttl_seconds" not in runtime_bridge
    assert "bind_base_url" not in deploy_bridge
    assert "wechat_public_connect_url_template" not in deploy_bridge
    assert "wechat_bind_session_ttl_seconds" not in deploy_bridge


def test_compose_and_nginx_expose_only_clawscale_services():
    compose = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text())
    services = compose["services"]

    assert "ecloud-input" not in services
    assert "ecloud-output" not in services
    assert "coke-bootstrap" in services
    assert "coke-agent" in services
    assert "coke-bridge" in services
    assert "gateway" in services
    assert services["coke-bridge"]["command"][0] == "gunicorn"
    assert services["coke-bridge"]["command"][-1] == "connector.clawscale_bridge.wsgi:app"
    assert (
        services["coke-agent"]["depends_on"]["coke-bootstrap"]["condition"]
        == "service_completed_successfully"
    )
    assert (
        services["coke-bridge"]["depends_on"]["coke-bootstrap"]["condition"]
        == "service_completed_successfully"
    )

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
    assert not (ROOT / "connector" / "gateway").exists()
    assert not (ROOT / "connector" / "channel").exists()


def test_legacy_gateway_assets_are_removed():
    assert not (ROOT / "scripts" / "deploy-to-gcp.sh").exists()
    assert not (ROOT / "tests" / "unit" / "connector" / "test_gateway_config.py").exists()
    assert not (ROOT / "tests" / "unit" / "connector" / "test_channel_registry.py").exists()
    assert not (ROOT / "tests" / "unit" / "connector" / "test_channel_types.py").exists()
    assert not (ROOT / "tests" / "unit" / "connector" / "test_discord_adapter.py").exists()
    assert not (ROOT / "tests" / "unit" / "connector" / "test_telegram_adapter.py").exists()
    assert not (ROOT / "tests" / "unit" / "connector" / "test_terminal_adapter.py").exists()
    assert not (ROOT / "connector" / "clawscale_bridge" / "backfill_clawscale_users.py").exists()
    assert not (ROOT / "connector" / "clawscale_bridge" / "backfill_delivery_routes.py").exists()
    assert not (ROOT / "connector" / "clawscale_bridge" / "output_route_resolver.py").exists()
    assert not (ROOT / "dao" / "external_identity_dao.py").exists()
    assert not (ROOT / "dao" / "clawscale_push_route_dao.py").exists()
    assert not (ROOT / "tests" / "unit" / "connector" / "clawscale_bridge" / "test_backfill_clawscale_users.py").exists()
    assert not (ROOT / "tests" / "unit" / "connector" / "clawscale_bridge" / "test_backfill_delivery_routes.py").exists()
    assert not (ROOT / "tests" / "unit" / "connector" / "clawscale_bridge" / "test_output_route_resolver.py").exists()
    assert not (ROOT / "tests" / "unit" / "dao" / "test_external_identity_dao.py").exists()
    assert not (ROOT / "tests" / "unit" / "dao" / "test_clawscale_push_route_dao.py").exists()


def test_runtime_sources_remove_legacy_wechat_identity_fallbacks():
    message_processor = (ROOT / "agent" / "runner" / "message_processor.py").read_text()
    background_handler = (
        ROOT / "agent" / "runner" / "agent_background_handler.py"
    ).read_text()
    hardcode_handler = (
        ROOT / "agent" / "runner" / "agent_hardcode_handler.py"
    ).read_text()
    agent_handler = (ROOT / "agent" / "runner" / "agent_handler.py").read_text()
    user_dao = (ROOT / "dao" / "user_dao.py").read_text()
    chat_workflow = (
        ROOT / "agent" / "agno_agent" / "workflows" / "chat_workflow_streaming.py"
    ).read_text()
    chat_context = (
        ROOT / "agent" / "prompt" / "chat_contextprompt.py"
    ).read_text()
    chat_task = (ROOT / "agent" / "prompt" / "chat_taskprompt.py").read_text()
    chat_notice = (ROOT / "agent" / "prompt" / "chat_noticeprompt.py").read_text()
    context_file = (ROOT / "agent" / "runner" / "context.py").read_text()
    reminder_tools = (
        ROOT / "agent" / "agno_agent" / "tools" / "reminder_tools.py"
    ).read_text()
    time_util = (ROOT / "util" / "time_util.py").read_text()

    assert "platforms.wechat.id" not in message_processor
    assert "platforms.wechat.id" not in background_handler
    assert "platforms.wechat.id" not in user_dao
    assert 'CONF.get("default_platform"' not in background_handler
    assert 'CONF.get("default_platform"' not in agent_handler
    assert '["platforms"]["wechat"]' not in hardcode_handler
    assert '.get("platforms", {}).get("wechat"' not in chat_workflow
    assert '.get("platforms", {}).get("wechat"' not in chat_context
    assert "get_user_by_platform" not in user_dao
    assert "update_platform_info" not in user_dao
    assert "find_users_by_platform" not in user_dao
    assert "find_by_platform" not in user_dao
    assert "add_platform_to_user" not in user_dao
    assert "remove_platform_from_user" not in user_dao
    assert "[platforms][wechat]" not in chat_context
    assert "[platforms][wechat]" not in chat_task
    assert "[platforms][wechat]" not in chat_notice
    assert 'setdefault("wechat"' not in context_file
    assert "在微信上认识的朋友" not in context_file
    assert "get_user_timezone" not in context_file
    assert "get_user_timezone" not in reminder_tools
    assert "WhatsApp JID" not in time_util
