from dataclasses import dataclass
from typing import Any, Dict


class AccountNotFoundError(KeyError):
    pass


class ChannelNotFoundError(KeyError):
    pass


@dataclass(frozen=True)
class ResolvedAccount:
    account_id: str
    channel: str
    character: str
    character_platform_id: str


@dataclass(frozen=True)
class GatewayConfig:
    enabled: bool
    openclaw_url: str
    openclaw_token: str
    shared_secret: str
    group_chat: Dict[str, Any]
    account_mapping: Dict[str, Dict[str, Dict[str, Any]]]

    @classmethod
    def from_app_config(cls, app_config: Dict[str, Any]) -> "GatewayConfig":
        gateway = app_config.get("gateway") or {}

        def parse_bool(value: Any) -> bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, int) and value in (0, 1):
                return bool(value)
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {"true", "1", "yes", "on"}:
                    return True
                if normalized in {"false", "0", "no", "off"}:
                    return False
            raise ValueError(f"Invalid boolean value: {value!r}")

        def validate_account_mapping(
            account_mapping: Dict[str, Any],
        ) -> Dict[str, Dict[str, Dict[str, Any]]]:
            normalized_mapping: Dict[str, Dict[str, Dict[str, Any]]] = {}
            for account_id, account_config in account_mapping.items():
                if not isinstance(account_config, dict):
                    raise ValueError(f"Invalid account mapping for {account_id!r}")

                character = account_config.get("character")
                channels = account_config.get("channels")
                if not character or not isinstance(channels, dict):
                    raise ValueError(f"Invalid account mapping for {account_id!r}")

                normalized_channels: Dict[str, Dict[str, Any]] = {}
                for channel_name, channel_config in channels.items():
                    if not isinstance(channel_config, dict):
                        raise ValueError(
                            f"Invalid channel mapping for {account_id!r}:{channel_name!r}"
                        )
                    character_platform_id = channel_config.get("character_platform_id")
                    if not character_platform_id:
                        raise ValueError(
                            f"Invalid channel mapping for {account_id!r}:{channel_name!r}"
                        )
                    normalized_channels[channel_name] = {
                        "character_platform_id": character_platform_id
                    }

                normalized_mapping[account_id] = {
                    "character": character,
                    "channels": normalized_channels,
                }

            return normalized_mapping

        return cls(
            enabled=parse_bool(gateway.get("enabled", False)),
            openclaw_url=gateway.get("openclaw_url", ""),
            openclaw_token=gateway.get("openclaw_token", ""),
            shared_secret=gateway.get("shared_secret", ""),
            group_chat={
                **dict(gateway.get("group_chat") or {}),
                "enabled": parse_bool(
                    (gateway.get("group_chat") or {}).get("enabled", False)
                ),
            },
            account_mapping=validate_account_mapping(
                dict(gateway.get("account_mapping") or {})
            ),
        )

    def resolve_account(self, account_id: str, channel: str) -> ResolvedAccount:
        account_channels = self.account_mapping.get(account_id)
        if account_channels is None:
            raise AccountNotFoundError(account_id)

        channels = account_channels.get("channels") or {}
        channel_mapping = channels.get(channel)
        if channel_mapping is None:
            raise ChannelNotFoundError(channel)

        return ResolvedAccount(
            account_id=account_id,
            channel=channel,
            character=account_channels["character"],
            character_platform_id=channel_mapping["character_platform_id"],
        )
