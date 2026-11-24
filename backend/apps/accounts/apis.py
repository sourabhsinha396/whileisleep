from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from ninja import File, Router, UploadedFile
from ninja.errors import HttpError

from apps.workspaces.services import organization_for
from whileisleep import images

from .models import AuthToken, Profile, photo_url
from .schemas import LoginIn, SessionOut, SignupIn, UserOut
from .security import token_auth

router = Router(tags=["auth"])
User = get_user_model()


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


@router.post("/signup", response=SessionOut)
def signup(request, payload: SignupIn):
    if not settings.SIGNUP_ENABLED:
        raise HttpError(403, "Sign-up is closed on this installation. Ask its owner for an account.")
    email = payload.email.lower()
    if User.objects.filter(username=email).exists():
        raise HttpError(400, "An account with this email already exists.")
    user = User.objects.create_user(username=email, email=email, password=payload.password, first_name=payload.name)
    organization_for(user)
    return session_for(user)


@router.post("/login", response=SessionOut)
def login(request, payload: LoginIn):
    user = authenticate(request, username=payload.email.lower(), password=payload.password)
    if user is None:
        raise HttpError(401, "Wrong email or password.")
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
