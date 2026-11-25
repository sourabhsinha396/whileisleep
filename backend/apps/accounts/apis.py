from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from ninja import File, Router, UploadedFile
from ninja.errors import HttpError

from apps.conversations.limits import hit
from apps.workspaces.services import organization_for
from whileisleep import images
from whileisleep.client_ip import client_ip

from . import captcha, google, passwords, tasks
from .models import AuthToken, Profile, photo_url
from .schemas import CaptchaOut, ForgotIn, GoogleOut, LoginIn, PasswordOut, ResetIn, SessionOut, SignupIn, UserOut
from .security import token_auth

router = Router(tags=["auth"])
User = get_user_model()

# In an hour.
RESETS_PER_EMAIL = 3
RESETS_PER_ADDRESS = 20


def user_out(user) -> dict:
    return {
        "id": user.id,
        "name": user.first_name or user.email,
        "email": user.email,
        "photo_url": photo_url(user),
        "is_superuser": user.is_superuser,
    }


def session_for(user) -> dict:
    return {"token": AuthToken.objects.create(user=user).key, "user": user_out(user)}


@router.get("/captcha", response=CaptchaOut)
def captcha_key(request):
    return {"site_key": captcha.site_key()}


@router.post("/signup", response=SessionOut)
def signup(request, payload: SignupIn):
    if not settings.SIGNUP_ENABLED:
        raise HttpError(403, "Sign-up is closed on this installation. Ask its owner for an account.")
    captcha.require(request, payload.captcha)
    email = payload.email.lower()
    if User.objects.filter(username=email).exists():
        raise HttpError(400, "An account with this email already exists.")
    user = User.objects.create_user(username=email, email=email, password=payload.password, first_name=payload.name)
    organization_for(user)
    return session_for(user)


@router.post("/login", response=SessionOut)
def login(request, payload: LoginIn):
    captcha.require(request, payload.captcha)
    user = authenticate(request, username=payload.email.lower(), password=payload.password)
    if user is None:
        raise HttpError(401, "Wrong email or password.")
    return session_for(user)


@router.get("/google", response=GoogleOut)
def google_enabled(request):
    return {"enabled": settings.GOOGLE_ENABLED}


def require_google() -> None:
    if not settings.GOOGLE_ENABLED:
        raise HttpError(404, "Logging in with Google isn't set up on this installation.")


# The browser itself comes to these two, so they answer with where to go next.
@router.get("/google/start", include_in_schema=False)
def google_start(request):
    require_google()
    return google.start()


@router.get("/google/callback", include_in_schema=False)
def google_callback(request):
    require_google()
    return google.finish(request)


@router.post("/google/session", response=SessionOut)
def google_session(request):
    """The token of whoever just logged in with Google in this browser."""
    require_google()
    user = google.swap_ticket(request)
    if user is None:
        raise HttpError(401, "That login has expired. Try again.")
    return session_for(user)


@router.get("/password", response=PasswordOut)
def password_options(request):
    return {"can_reset": settings.MAIL_ENABLED}


@router.post("/password/forgot")
def forgot_password(request, payload: ForgotIn):
    """Emails a link to choose a new password. The same answer whether or not there is an account."""
    if not settings.MAIL_ENABLED:
        raise HttpError(404, "This installation can't send emails. Ask its owner for a new password.")
    captcha.require(request, payload.captcha)
    if not hit("forgot", client_ip(request) or "-", RESETS_PER_ADDRESS, 3600):
        raise HttpError(429, "Too many tries. Wait an hour and try again.")
    email = payload.email.strip().lower()
    if hit("forgot-email", email, RESETS_PER_EMAIL, 3600):
        tasks.send_reset.delay(email)
    return {"ok": True}


@router.post("/password/reset", response=SessionOut)
def reset_password(request, payload: ResetIn):
    if not hit("reset", client_ip(request) or "-", RESETS_PER_ADDRESS, 3600):
        raise HttpError(429, "Too many tries. Wait an hour and try again.")
    user = passwords.reset(payload.key, payload.password)
    if user is None:
        raise HttpError(400, "This link has expired or was already used.")
    if settings.MAIL_ENABLED:
        tasks.send_changed.delay(user.email)
    return session_for(user)


@router.post("/logout", auth=token_auth)
def logout(request):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    AuthToken.objects.filter(key=token).delete()
    return {"ok": True}


@router.get("/me", response=UserOut, auth=token_auth)
def me(request):
    return user_out(request.auth)


@router.post("/me/photo", response=UserOut, auth=token_auth)
def upload_photo(request, file: UploadedFile = File(...)):  # noqa: B008
    images.require_storage()
    content = images.clean_image(file, images.AVATAR_SIDE, square=True)
    profile, _ = Profile.objects.get_or_create(user=request.auth)
    images.replace(profile, "photo", content)
    request.auth.profile = profile
    return user_out(request.auth)


@router.delete("/me/photo", response=UserOut, auth=token_auth)
def remove_photo(request):
    profile, _ = Profile.objects.get_or_create(user=request.auth)
    images.replace(profile, "photo", None)
    request.auth.profile = profile
    return user_out(request.auth)
