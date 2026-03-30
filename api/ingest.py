from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from api.config import GatewayConfig
from api.schema import ChatRequest
from util.redis_stream import publish_input_event


class DuplicateMessageError(Exception):
    def __init__(self, message_id: str):
        super().__init__(message_id)
        self.message_id = message_id


@dataclass(frozen=True)
class IngestResult:
    request_message_id: str
    input_message_id: str


class GatewayIngestService:
    def __init__(
        self,
        mongo,
        user_dao,
        redis_client,
        redis_conf,
        gateway_config: GatewayConfig,
    ):
        self.mongo = mongo
        self.user_dao = user_dao
        self.redis_client = redis_client
        self.redis_conf = redis_conf
        self.gateway_config = gateway_config

    def _ensure_not_duplicate(self, request: ChatRequest) -> None:
        existing = self.mongo.find_one(
            "inputmessages",
            {
                "platform": request.channel,
                "metadata.gateway.account_id": request.account_id,
                "metadata.gateway.message_id": request.message_id,
            },
        )
        if existing:
            raise DuplicateMessageError(request.message_id)

    def _normalize_reference(self, request: ChatRequest) -> Dict[str, Any]:
        if not request.reply_to:
            return {}
        return {
            "reference": {
                "id": request.reply_to.id,
                "text": request.reply_to.content or "",
                "user": request.reply_to.author_name or "",
            }
        }

    def _resolve_sender(self, request: ChatRequest) -> dict:
        sender_query = {f"platforms.{request.channel}.id": request.sender.platform_id}
        users = self.user_dao.find_users(sender_query)
        if users:
            return users[0]

        user_data = {
            "is_character": False,
            "name": request.sender.display_name or request.sender.platform_id,
            "platforms": {
                request.channel: {
                    "id": request.sender.platform_id,
                    "display_name": request.sender.display_name or "",
                }
            },
            "status": "normal",
            "user_info": {},
        }
        created_id = self.user_dao.create_user(user_data)
        return self.user_dao.get_user_by_id(created_id) or {
            "_id": created_id,
            **user_data,
        }

    def _resolve_character(self, request: ChatRequest, account_id: str) -> dict:
        resolved = self.gateway_config.resolve_account(account_id, request.channel)
        characters = self.user_dao.find_characters({"name": resolved.character})
        if not characters:
            raise LookupError(
                f"character not found for gateway account {account_id!r}"
            )
        character = characters[0]
        routing_identity = (
            (character.get("platforms") or {})
            .get(request.channel, {})
            .get("id")
        )
        if routing_identity != resolved.character_platform_id:
            raise LookupError(
                f"character routing identity mismatch for gateway account {account_id!r}"
            )
        return {
            "resolved": resolved,
            "character": character,
        }

    def _resolve_message_payload(self, request: ChatRequest) -> tuple[str, Dict[str, Any]]:
        message_text = request.content
        metadata: Dict[str, Any] = {}

        if request.message_type == "voice" and request.media_url:
            from agent.tool.image import download_image
            from framework.tool.voice2text.aliyun_asr import voice_to_text

            file_path = download_image(
                request.media_url, "coke/temp/", f"{request.message_id}.silk"
            )
            metadata.update({"file_path": file_path, "media_url": request.media_url})
            message_text = voice_to_text(file_path)
        elif request.message_type == "image" and request.media_url:
            from framework.tool.image2text.ark import ark_image2text

            metadata.update({"url": request.media_url, "media_url": request.media_url})
            message_text = ark_image2text(
                "请详细描述图中有什么？输出不要分段和换行.", request.media_url
            )
        elif request.media_url:
            metadata["media_url"] = request.media_url

        return message_text, metadata

    def _build_input_doc(self, request: ChatRequest) -> Dict[str, Any]:
        character_info = self._resolve_character(request, request.account_id)
        resolved = character_info["resolved"]
        character = character_info["character"]
        sender = self._resolve_sender(request)
        message_text, media_metadata = self._resolve_message_payload(request)

        metadata = {
            **request.metadata,
            **self._normalize_reference(request),
            **media_metadata,
            "gateway": {
                "account_id": resolved.account_id,
                "message_id": request.message_id,
                "character_platform_id": resolved.character_platform_id,
            },
        }

        return {
            "input_timestamp": request.timestamp,
            "handled_timestamp": None,
            "status": "pending",
            "from_user": str(sender["_id"]),
            "to_user": str(character["_id"]),
            "platform": request.channel,
            "chatroom_name": request.group_id,
            "message_type": request.message_type,
            "message": message_text,
            "metadata": metadata,
        }

    def accept(self, request: ChatRequest) -> IngestResult:
        self._ensure_not_duplicate(request)
        doc = self._build_input_doc(request)
        inserted_id = self.mongo.insert_one("inputmessages", doc)
        if self.redis_client is not None:
            publish_input_event(
                self.redis_client,
                inserted_id,
                request.channel,
                request.timestamp,
                stream_key=self.redis_conf.stream_key,
            )
        return IngestResult(
            request_message_id=request.message_id,
            input_message_id=inserted_id,
        )
