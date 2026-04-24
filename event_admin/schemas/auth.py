from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"  # noqa: S105
    role: str
