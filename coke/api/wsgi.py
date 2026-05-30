from __future__ import annotations

from coke.app import create_app
from coke.composition import build_runtime_from_settings
from coke.config import Settings


settings = Settings.from_env()
runtime = build_runtime_from_settings(settings)
app = create_app(
    settings,
    composed_runtime=runtime,
    provider_adapters=runtime.provider_adapters,
)
