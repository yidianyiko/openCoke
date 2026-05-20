from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from agent.agno_agent.runtime.result import CapabilityResult
from dao.mongo import MongoDBBase

logger = logging.getLogger(__name__)


class AlbumCapabilityPort:
    def __init__(
        self,
        *,
        contract_factory: Callable[[Any], Any] | None = None,
    ) -> None:
        self.contract_factory = contract_factory or _default_contract_factory

    def run(
        self,
        input_message: str,
        run_context: Any,
        args: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        del input_message
        request_args = args or {}
        action = str(request_args.get("action") or "").strip()
        if action != "delete_photo":
            return CapabilityResult(
                name="album",
                ok=False,
                content={"message": "", "error": f"unsupported album action: {action}"},
                error="unsupported_album_action",
                metadata={"durable_write": False},
            )

        content = self.contract_factory(run_context).delete_photo(
            str(request_args.get("photo_id") or "")
        )
        return CapabilityResult(
            name="album",
            ok=bool(content.get("ok", True)),
            content=content,
            error=content.get("error"),
            metadata={"durable_write": bool(content.get("ok"))},
        )


class AlbumDomainContract:
    def __init__(self, *, mongo: MongoDBBase | None = None) -> None:
        self.mongo = mongo or MongoDBBase()

    def delete_photo(self, photo_id: str) -> dict[str, Any]:
        try:
            photo = self.mongo.get_vector_by_id("embeddings", photo_id)
            if photo is None:
                return {"ok": False, "message": "", "error": f"找不到照片: {photo_id}"}

            self.mongo.delete_vector("embeddings", photo_id)
            logger.info("照片已删除: %s", photo_id)
            return {"ok": True, "message": f"照片已删除: {photo_id}"}
        except Exception as exc:
            logger.error("photo_delete_tool error: %s", exc)
            return {"ok": False, "message": "", "error": str(exc)}


def _default_contract_factory(_run_context: Any) -> AlbumDomainContract:
    return AlbumDomainContract()
