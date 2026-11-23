from ninja.security import HttpBearer

from .models import AuthToken


class TokenAuth(HttpBearer):
    """Dashboard auth: `Authorization: Bearer <AuthToken.key>`. Sets request.auth to the user."""

    def authenticate(self, request, token):
        row = AuthToken.objects.select_related("user").filter(key=token, user__is_active=True).first()
        return row.user if row else None


token_auth = TokenAuth()
