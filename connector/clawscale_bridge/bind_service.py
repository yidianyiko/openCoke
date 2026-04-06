from werkzeug.security import check_password_hash


class BindService:
    def __init__(self, user_dao, external_identity_dao, binding_ticket_dao):
        self.user_dao = user_dao
        self.external_identity_dao = external_identity_dao
        self.binding_ticket_dao = binding_ticket_dao

    def verify_account(self, phone_number: str, bind_secret: str):
        user = self.user_dao.get_user_by_phone_number(phone_number)
        if not user:
            return False, "account_not_found"
        if not check_password_hash(user["bind_secret_hash"], bind_secret):
            return False, "invalid_credentials"
        if user.get("status") not in (None, "normal"):
            return False, "account_unavailable"
        return True, user
