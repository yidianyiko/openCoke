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
    assert "access_control" not in runtime_config
    assert "access_control" not in deploy_config

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


def test_legacy_python_payment_runtime_is_removed():
    user_dao = (ROOT / "dao" / "user_dao.py").read_text()

    assert not (ROOT / "agent" / "runner" / "payment").exists()
    assert not (ROOT / "tests" / "unit" / "dao" / "test_user_dao_stripe.py").exists()
    assert not (ROOT / "tests" / "unit" / "dao" / "test_user_dao_creem.py").exists()
    assert "update_access_stripe" not in user_dao
    assert "update_access_creem" not in user_dao
    assert "access.stripe_customer_id" not in user_dao
    assert "access.creem_customer_id" not in user_dao


def test_retired_billing_auth_and_usage_cleanup_surfaces_are_removed():
    user_dao = (ROOT / "dao" / "user_dao.py").read_text()
    post_analyze = (ROOT / "agent" / "agno_agent" / "runtime" / "post_analyze.py").read_text()
    capability_exports = (
        ROOT / "agent" / "agno_agent" / "capabilities" / "__init__.py"
    ).read_text()

    retired_paths = [
        ROOT / "connector" / "scripts" / "migrate-legacy-users.py",
        ROOT / "connector" / "scripts" / "verify-auth-retirement.py",
        ROOT / "agent" / "agno_agent" / "capabilities" / "usage.py",
        ROOT / "agent" / "agno_agent" / "utils" / "usage_tracker.py",
        ROOT / "tests" / "unit" / "dao" / "test_user_dao_legacy_migration.py",
        ROOT / "tests" / "unit" / "connector" / "clawscale_bridge" / "test_verify_auth_retirement.py",
        ROOT / "tests" / "unit" / "dao" / "test_user_dao_access.py",
        ROOT / "tests" / "unit" / "dao" / "test_usage_dao.py",
        ROOT / "tests" / "unit" / "runner" / "test_background_handler_legacy_pollers.py",
        ROOT / "tests" / "unit" / "runner" / "test_dispatcher_without_gate.py",
    ]
    for path in retired_paths:
        assert not path.exists(), f"{path.relative_to(ROOT)} should stay retired"

    assert "def update_access" not in user_dao
    assert "def revoke_access" not in user_dao
    assert "usage_tracker" not in post_analyze
    assert "UsageCapabilityPort" not in capability_exports


def test_retired_output_repair_rollback_and_provider_compensation_are_removed():
    agent_runtime = (ROOT / "agent" / "agno_agent" / "runtime" / "agent_runtime.py").read_text()
    domain_results = (
        ROOT / "agent" / "agno_agent" / "runtime" / "domain_results.py"
    ).read_text()
    runtime_result = (
        ROOT / "agent" / "agno_agent" / "runtime" / "result.py"
    ).read_text()
    reminder_intent = (
        ROOT / "agent" / "agno_agent" / "capabilities" / "reminder_intent.py"
    ).read_text()
    scheduling = (
        ROOT / "agent" / "agno_agent" / "capabilities" / "scheduling.py"
    ).read_text()
    smoke_runner = (
        ROOT
        / "tools"
        / "agent_smoke"
        / "_runner_phase_cross_feature_long_conversation.py"
    ).read_text()
    bridge_app = (ROOT / "connector" / "clawscale_bridge" / "app.py").read_text()
    shared_channel_routes = (
        ROOT / "gateway" / "packages" / "api" / "src" / "routes" / "admin-shared-channels.ts"
    ).read_text()

    assert not (ROOT / "agent" / "runner" / "rollback_detection.py").exists()
    assert "rollback_count" not in (ROOT / "agent" / "runner" / "message_processor.py").read_text()
    assert "retry_count" not in (ROOT / "agent" / "runner" / "message_processor.py").read_text()
    assert "compensate_rolled_back" not in (ROOT / "agent" / "runner" / "agent_handler.py").read_text()

    assert "user_visible_fallback" not in runtime_result
    assert "prohibited_claims" not in domain_results
    assert "required_questions" not in domain_results
    assert "_UNCONFIRMED_DURABLE_WRITE_PATTERNS" not in agent_runtime
    assert "_COMPLETED_WRITE_CLAIM_PATTERNS" not in agent_runtime
    assert "_STALE_SHARED_REMINDER_INVITE_CLAIM_PATTERNS" not in agent_runtime
    assert "_VISIBLE_IDENTIFIER_LEAK_PATTERNS" not in agent_runtime
    assert "check_prohibited_claims" not in agent_runtime
    assert "_FENCED_JSON_RE" not in agent_runtime
    assert "_resolve_domain_visible_text" not in agent_runtime
    assert "_domain_visible_text_result" not in agent_runtime
    assert "domain_summary" not in agent_runtime
    assert "_recover_explicit_duration_minutes" not in agent_runtime

    assert "OUTPUT SAFETY NET" not in reminder_intent
    assert "_should_reject_" not in reminder_intent
    assert "_normalize_point_reminder_duration" not in reminder_intent
    assert "_unbounded_high_frequency_cadence" not in reminder_intent
    assert "_recover_shared_reminder_receiver_name" not in scheduling
    assert "EMPTY_FALLBACK_TOKENS" not in smoke_runner
    assert "real_empty_fallback" not in smoke_runner

    assert "LateReplyFallbackPromoter" not in bridge_app
    assert "late_reply_fallback" not in bridge_app
    assert "rollbackEvolution" not in shared_channel_routes
    assert "rollbackLinq" not in shared_channel_routes


def test_runtime_sources_remove_legacy_wechat_identity_fallbacks():
    message_processor = (ROOT / "agent" / "runner" / "message_processor.py").read_text()
    background_handler = (
        ROOT / "agent" / "runner" / "agent_background_handler.py"
    ).read_text()
    agent_handler = (ROOT / "agent" / "runner" / "agent_handler.py").read_text()
    user_dao = (ROOT / "dao" / "user_dao.py").read_text()
    chat_context = (
        ROOT / "agent" / "prompt" / "chat_contextprompt.py"
    ).read_text()
    chat_task = (ROOT / "agent" / "prompt" / "chat_taskprompt.py").read_text()
    chat_notice = (ROOT / "agent" / "prompt" / "chat_noticeprompt.py").read_text()
    context_file = (ROOT / "agent" / "runner" / "context.py").read_text()
    time_util = (ROOT / "util" / "time_util.py").read_text()

    assert "platforms.wechat.id" not in message_processor
    assert "platforms.wechat.id" not in background_handler
    assert "platforms.wechat.id" not in user_dao
    assert 'CONF.get("default_platform"' not in background_handler
    assert 'CONF.get("default_platform"' not in agent_handler
    assert not (
        ROOT / "agent" / "agno_agent" / "workflows" / "chat_workflow_streaming.py"
    ).exists()
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
    assert "WhatsApp JID" not in time_util
