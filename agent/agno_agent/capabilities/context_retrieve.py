from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from agent.agno_agent.runtime.result import CapabilityResult
from dao.mongo import MongoDBBase
from util.embedding_util import embedding_by_aliyun
from util.log_util import get_logger
from util.time_util import format_time_friendly

logger = get_logger(__name__)


class ContextRetrieveCapabilityPort:
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
        content = self.contract_factory(run_context).retrieve(args or {})
        return CapabilityResult(
            name="context_retrieve",
            ok=True,
            content=content,
            metadata={
                "durable_write": False,
                "requires_response_synthesis": True,
            },
        )


class ContextRetrieveDomainContract:
    def __init__(
        self,
        *,
        mongo: MongoDBBase | None = None,
    ) -> None:
        self.mongo = mongo or MongoDBBase()

    def retrieve(self, request: dict[str, Any]) -> dict[str, Any]:
        return_resp = {
            "character_global": "",
            "character_private": "",
            "user": "",
            "character_knowledge": "",
            "confirmed_reminders": "",
            "relevant_history": "",
        }

        try:
            character_setting_query = str(request.get("character_setting_query") or "")
            character_setting_keywords = str(
                request.get("character_setting_keywords") or ""
            )
            user_profile_query = str(request.get("user_profile_query") or "")
            user_profile_keywords = str(request.get("user_profile_keywords") or "")
            character_knowledge_query = str(
                request.get("character_knowledge_query") or ""
            )
            character_knowledge_keywords = str(
                request.get("character_knowledge_keywords") or ""
            )
            chat_history_query = str(request.get("chat_history_query") or "")
            chat_history_keywords = str(request.get("chat_history_keywords") or "")
            character_id = str(request.get("character_id") or "")
            user_id = str(request.get("user_id") or "")

            return_resp["character_global"] = _search_embeddings(
                mongo=self.mongo,
                query_question=character_setting_query,
                query_keywords=character_setting_keywords,
                metadata_type="character_global",
                character_id=character_id,
                user_id=None,
                top_k=8,
                result_limit=6,
            )
            return_resp["character_private"] = _search_embeddings(
                mongo=self.mongo,
                query_question=character_setting_query,
                query_keywords=character_setting_keywords,
                metadata_type="character_private",
                character_id=character_id,
                user_id=user_id,
                top_k=8,
                result_limit=6,
            )
            return_resp["user"] = _search_embeddings(
                mongo=self.mongo,
                query_question=user_profile_query,
                query_keywords=user_profile_keywords,
                metadata_type="user",
                character_id=character_id,
                user_id=user_id,
                top_k=8,
                result_limit=6,
            )
            return_resp["character_knowledge"] = _search_embeddings(
                mongo=self.mongo,
                query_question=character_knowledge_query,
                query_keywords=character_knowledge_keywords,
                metadata_type="character_knowledge",
                character_id=character_id,
                user_id=None,
                top_k=8,
                result_limit=6,
            )

            if chat_history_query or chat_history_keywords:
                return_resp["relevant_history"] = _search_chat_history(
                    mongo=self.mongo,
                    query_question=chat_history_query,
                    query_keywords=chat_history_keywords,
                    character_id=character_id,
                    user_id=user_id,
                    top_k=15,
                    result_limit=10,
                )
                logger.info("Retrieved relevant history messages")

            return_resp["confirmed_reminders"] = self._retrieve_confirmed_reminders(
                user_id
            )
        except Exception as exc:
            logger.error("Error in context_retrieve capability: %s", exc)
            raise

        return return_resp

    def _retrieve_confirmed_reminders(self, user_id: str) -> str:
        try:
            from dao.reminder_dao import ReminderDAO

            reminder_dao = ReminderDAO()
            current_time = datetime.now(UTC)
            all_reminders = reminder_dao.list_for_owner(
                owner_user_id=user_id,
                lifecycle_states=["active"],
            )

            lines = []
            for action in all_reminders[:30]:
                if action.get("lifecycle_state") != "active":
                    continue

                title = str(action.get("title", ""))
                next_fire_at = action.get("next_fire_at")
                if not next_fire_at or next_fire_at <= current_time:
                    continue

                ts = int(next_fire_at.timestamp())
                time_str = format_time_friendly(ts) if ts > 0 else ""
                line = title
                if time_str:
                    line = line + " · " + time_str
                lines.append(line)
            reminder_dao.close()
            return "\n".join(lines)
        except Exception as exc:
            logger.warning("Failed to retrieve reminders: %s", exc)
            return ""


def _default_contract_factory(_run_context: Any) -> ContextRetrieveDomainContract:
    return ContextRetrieveDomainContract()


def _merge_results_embedding(
    merged_results: dict, results: list, bar_min: float, bar_max: float, weight: float
) -> dict:
    for result in results:
        if result["similarity"] > bar_max:
            result["similarity"] = bar_max
        if result["similarity"] < bar_min:
            continue

        result_weight = weight * (result["similarity"] - bar_min) / (bar_max - bar_min)
        result_id = str(result["_id"])
        if result_id not in merged_results:
            merged_results[result_id] = {
                "_id": result_id,
                "key": result["key"],
                "value": result["value"],
                "similarity": result["similarity"],
                "weight": result_weight,
            }
        else:
            merged_results[result_id]["weight"] += result_weight

    return merged_results


def _merge_results_text(
    merged_results: dict, results: list, total_weight: float
) -> dict:
    if len(results) == 0:
        return merged_results

    result_weight = total_weight / len(results)
    for result in results:
        result_id = str(result["_id"])
        if result_id not in merged_results:
            merged_results[result_id] = {
                "_id": result_id,
                "key": result["key"],
                "value": result["value"],
                "weight": result_weight,
            }
        else:
            merged_results[result_id]["weight"] += result_weight

    return merged_results


def _top_n(results: dict, n: int, photo_prefix: bool = False) -> str:
    sorted_items = sorted(results.items(), key=lambda x: x[1]["weight"], reverse=True)
    top_n_results = [item[1] for item in sorted_items[:n]]

    top_n_str_list = []
    for result in top_n_results:
        line = str(result["key"] + "：" + result["value"]).strip()
        if photo_prefix:
            line = "「照片" + str(result["_id"]) + "」" + line
        top_n_str_list.append(line)

    return "\n".join(top_n_str_list)


def _search_embeddings(
    mongo: MongoDBBase,
    query_question: str,
    query_keywords: str,
    metadata_type: str,
    character_id: str,
    user_id: str | None = None,
    top_k: int = 8,
    result_limit: int = 6,
) -> str:
    merged_results = {}

    metadata_filter = {"type": metadata_type, "cid": character_id}
    if user_id and metadata_type in ["character_private", "user"]:
        metadata_filter["uid"] = user_id

    if not query_question or query_question == "空":
        return ""

    emb_query = embedding_by_aliyun(query_question)
    results = mongo.vector_search(
        "embeddings",
        query_embedding=emb_query,
        embedding_field="key_embedding",
        metadata_filters=metadata_filter,
        top_k=top_k,
    )
    merged_results = _merge_results_embedding(merged_results, results, 0.3, 1, 0.7)

    results = mongo.vector_search(
        "embeddings",
        query_embedding=emb_query,
        embedding_field="value_embedding",
        metadata_filters=metadata_filter,
        top_k=top_k,
    )
    merged_results = _merge_results_embedding(merged_results, results, 0.3, 1, 0.3)

    if query_keywords:
        for keyword in str(query_keywords).split(","):
            keyword = keyword.strip()
            if not keyword:
                continue
            keyword_results = mongo.find_many(
                "embeddings",
                query={
                    "key": {"$in": [keyword]},
                    "metadata": metadata_filter,
                },
                limit=5,
            )
            merged_results = _merge_results_text(merged_results, keyword_results, 1)

    if query_keywords:
        for keyword in str(query_keywords).split(","):
            keyword = keyword.strip()
            if not keyword:
                continue
            keyword_results = mongo.find_many(
                "embeddings",
                query={
                    "value": {"$in": [keyword]},
                    "metadata": metadata_filter,
                },
                limit=5,
            )
            merged_results = _merge_results_text(merged_results, keyword_results, 1)

    return _top_n(merged_results, result_limit)


def _search_chat_history(
    mongo: MongoDBBase,
    query_question: str,
    query_keywords: str,
    character_id: str,
    user_id: str,
    top_k: int = 15,
    result_limit: int = 10,
) -> str:
    merged_results = {}
    metadata_filter = {"type": "chat_history", "cid": character_id, "uid": user_id}

    if not query_question and not query_keywords:
        return ""

    if query_question:
        emb_query = embedding_by_aliyun(query_question)
        if emb_query:
            results = mongo.vector_search(
                "embeddings",
                query_embedding=emb_query,
                embedding_field="key_embedding",
                metadata_filters=metadata_filter,
                top_k=top_k,
            )
            merged_results = _merge_results_embedding(
                merged_results, results, 0.4, 1, 0.8
            )

    if query_keywords:
        for keyword in str(query_keywords).split(","):
            keyword = keyword.strip()
            if not keyword:
                continue
            keyword_results = mongo.find_many(
                "embeddings",
                query={
                    "key": {"$regex": keyword, "$options": "i"},
                    "metadata": metadata_filter,
                },
                limit=5,
            )
            merged_results = _merge_results_text(merged_results, keyword_results, 0.5)

    sorted_items = sorted(
        merged_results.items(), key=lambda x: x[1]["weight"], reverse=True
    )
    top_n_results = [item[1] for item in sorted_items[:result_limit]]

    result_lines = []
    for result in top_n_results:
        message = str(result["value"]).strip()
        if message:
            result_lines.append(f"- {message}")

    return "\n".join(result_lines)
