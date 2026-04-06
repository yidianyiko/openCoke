from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pymongo.errors import DuplicateKeyError
from werkzeug.security import check_password_hash, generate_password_hash


class UserAuthService:
    def __init__(self, user_dao, secret_key: str, token_ttl_seconds: int):
        self.user_dao = user_dao
        self.serializer = URLSafeTimedSerializer(
            secret_key=secret_key, salt="coke-user-auth"
        )
        self.token_ttl_seconds = token_ttl_seconds

    def _issue_token(self, user_id: str) -> str:
        return self.serializer.dumps({"user_id": user_id})

    def verify_token(self, token: str):
        try:
            payload = self.serializer.loads(token, max_age=self.token_ttl_seconds)
        except (BadSignature, SignatureExpired):
            return None
        user_id = payload.get("user_id")
        if not user_id:
            return None
        return self.user_dao.get_user_by_id(user_id)

    def register(self, display_name: str, email: str, password: str) -> dict:
        normalized_email = email.lower().strip()
        if self.user_dao.get_user_by_email(normalized_email):
            raise ValueError("email_already_exists")

        try:
            user_id = self.user_dao.create_user(
                {
                    "display_name": display_name.strip(),
                    "email": normalized_email,
                    "password_hash": generate_password_hash(password),
                    "web_auth_enabled": True,
                    "is_character": False,
                    "status": "normal",
                }
            )
        except DuplicateKeyError as exc:
            raise ValueError("email_already_exists") from exc
        return {
            "token": self._issue_token(user_id),
            "user": {
                "id": user_id,
                "email": normalized_email,
                "display_name": display_name.strip(),
            },
        }

    def login(self, email: str, password: str):
        user = self.user_dao.get_user_by_email(email.lower().strip())
        password_hash = user.get("password_hash") if user else None
        if not user or not password_hash or not check_password_hash(
            password_hash, password
        ):
            return False, "invalid_credentials"
        if user.get("status") not in (None, "normal"):
            return False, "account_unavailable"
        return True, {
            "token": self._issue_token(str(user["_id"])),
            "user": {
                "id": str(user["_id"]),
                "email": user["email"],
                "display_name": user.get("display_name")
                or user.get("name")
                or "Coke User",
            },
        }
