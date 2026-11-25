from ninja import Schema
from pydantic import EmailStr, Field


class CaptchaOut(Schema):
    # Empty: this installation has no captcha.
    site_key: str


class GoogleOut(Schema):
    enabled: bool


class Guarded(Schema):
    """A form with the "I'm not a robot" box; what ticking it gave."""

    captcha: str = Field("", max_length=8192)


class SignupIn(Guarded):
    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginIn(Guarded):
    # Not EmailStr: logging in only needs to match an account, whatever its domain.
    email: str = Field(max_length=254)
    password: str


class UserOut(Schema):
    id: int
    name: str
    email: str
    photo_url: str
    # Of this installation: may edit the docs' videos.
    is_superuser: bool


class SessionOut(Schema):
    token: str
    user: UserOut
