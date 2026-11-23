from ninja import Schema
from pydantic import EmailStr, Field


class SignupIn(Schema):
    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginIn(Schema):
    # Not EmailStr: logging in only needs to match an account, whatever its domain.
    email: str = Field(max_length=254)
    password: str


class UserOut(Schema):
    id: int
    name: str
    email: str


class SessionOut(Schema):
    token: str
    user: UserOut
