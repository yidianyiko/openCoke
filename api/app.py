try:
    import redis  # type: ignore
except ImportError:  # pragma: no cover - optional dependency until redis is installed
    redis = None

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.config import AccountNotFoundError, GatewayConfig
from api.ingest import DuplicateMessageError, GatewayIngestService
from api.payment_webhooks import router as payment_webhook_router
from api.schema import ChatAcceptedResponse, ChatRequest, ErrorResponse
from conf.config import get_config
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO
from util.redis_client import RedisClient


def _get_gateway_config() -> GatewayConfig:
    return GatewayConfig.from_app_config(get_config())


def _require_bearer_auth(
    authorization: str | None = Header(default=None),
) -> None:
    expected_secret = _get_gateway_config().shared_secret
    if not expected_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "unauthorized"},
        )
    expected_header = f"Bearer {expected_secret}"
    if authorization != expected_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "unauthorized"},
        )


def _build_ingest_service() -> GatewayIngestService:
    redis_conf = RedisClient.from_config()
    redis_client = None
    if redis is not None:
        redis_client = redis.Redis(
            host=redis_conf.host,
            port=redis_conf.port,
            db=redis_conf.db,
        )

    return GatewayIngestService(
        mongo=MongoDBBase(),
        user_dao=UserDAO(),
        redis_client=redis_client,
        redis_conf=redis_conf,
        gateway_config=_get_gateway_config(),
    )


def create_app() -> FastAPI:
    app = FastAPI()
    app.include_router(payment_webhook_router)
    app.state.ingest_service = _build_ingest_service()

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc):  # pragma: no cover
        del request
        error = ErrorResponse(error="validation_error", detail=str(exc))
        return JSONResponse(status_code=400, content=error.model_dump(exclude_none=True))

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc):  # pragma: no cover
        del request
        if exc.status_code == status.HTTP_401_UNAUTHORIZED and isinstance(
            exc.detail, dict
        ):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(error="http_error", detail=str(exc.detail)).model_dump(
                exclude_none=True
            ),
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/v1/chat",
        dependencies=[Depends(_require_bearer_auth)],
        response_model=ChatAcceptedResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def chat(payload: ChatRequest, request: Request):
        try:
            result = request.app.state.ingest_service.accept(payload)
        except DuplicateMessageError:
            error = ErrorResponse(error="duplicate", message_id=payload.message_id)
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=error.model_dump(exclude_none=True),
            )
        except (AccountNotFoundError, LookupError):
            error = ErrorResponse(
                error="unknown_account",
                account_id=payload.account_id,
            )
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=error.model_dump(exclude_none=True),
            )

        return ChatAcceptedResponse(
            status="accepted",
            request_message_id=result.request_message_id,
            input_message_id=result.input_message_id,
        )

    return app
