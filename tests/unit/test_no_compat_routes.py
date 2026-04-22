from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_legacy_coke_generic_route_wrappers_are_removed():
    removed_routes = [
        ROOT / "gateway" / "packages" / "web" / "app" / "(coke-user)" / "coke" / "login",
        ROOT / "gateway" / "packages" / "web" / "app" / "(coke-user)" / "coke" / "register",
        ROOT / "gateway" / "packages" / "web" / "app" / "(coke-user)" / "coke" / "forgot-password",
        ROOT / "gateway" / "packages" / "web" / "app" / "(coke-user)" / "coke" / "reset-password",
        ROOT / "gateway" / "packages" / "web" / "app" / "(coke-user)" / "coke" / "verify-email",
        ROOT / "gateway" / "packages" / "web" / "app" / "(coke-user)" / "coke" / "bind-wechat",
        ROOT / "gateway" / "packages" / "web" / "app" / "(coke-user)" / "coke" / "renew",
        ROOT / "gateway" / "packages" / "web" / "app" / "(coke-user)" / "coke" / "payment-success",
        ROOT / "gateway" / "packages" / "web" / "app" / "(coke-user)" / "coke" / "payment-cancel",
        ROOT / "gateway" / "packages" / "web" / "app" / "(coke-user)" / "coke" / "payment",
        ROOT / "gateway" / "packages" / "web" / "app" / "(coke-user)" / "coke" / "layout.tsx",
        ROOT / "gateway" / "packages" / "web" / "app" / "(coke-user)" / "coke" / "layout.test.tsx",
        ROOT / "gateway" / "packages" / "web" / "lib" / "coke-user-auth.ts",
        ROOT / "gateway" / "packages" / "web" / "lib" / "coke-user-auth.test.ts",
        ROOT / "gateway" / "packages" / "web" / "lib" / "coke-user-api.ts",
        ROOT / "gateway" / "packages" / "web" / "lib" / "coke-user-api.test.ts",
        ROOT / "gateway" / "packages" / "web" / "lib" / "coke-user-api-empty-body.test.ts",
        ROOT / "gateway" / "packages" / "web" / "lib" / "coke-user-wechat-channel.ts",
        ROOT / "gateway" / "packages" / "web" / "lib" / "coke-user-wechat-channel.test.ts",
        ROOT / "gateway" / "packages" / "web" / "lib" / "coke-user-wechat-channel-machine.ts",
        ROOT / "gateway" / "packages" / "web" / "lib" / "coke-user-bind.ts",
        ROOT / "gateway" / "packages" / "web" / "lib" / "coke-user-bind.test.ts",
    ]

    present = [str(path.relative_to(ROOT)) for path in removed_routes if path.exists()]
    assert present == []


def test_legacy_coke_auth_router_is_removed():
    compat_route_file = ROOT / "gateway" / "packages" / "api" / "src" / "routes" / "coke-auth-routes.ts"
    compat_payment_route_file = (
        ROOT / "gateway" / "packages" / "api" / "src" / "routes" / "coke-payment-routes.ts"
    )
    compat_wechat_route_file = (
        ROOT / "gateway" / "packages" / "api" / "src" / "routes" / "coke-wechat-routes.ts"
    )
    api_index = ROOT / "gateway" / "packages" / "api" / "src" / "index.ts"
    redirect_component = ROOT / "gateway" / "packages" / "web" / "components" / "legacy-redirect-page.tsx"

    assert not compat_route_file.exists()
    assert not compat_payment_route_file.exists()
    assert not compat_wechat_route_file.exists()
    assert not redirect_component.exists()
    assert "cokeAuthRouter" not in api_index.read_text()
    assert "cokePaymentRouter" not in api_index.read_text()
    assert "cokeWechatRouter" not in api_index.read_text()
