import pyotp

from event_admin.interfaces.totp import ITOTPService


class TOTPService(ITOTPService):
    def verify(self, code: str, secret: str) -> bool:
        return pyotp.TOTP(secret).verify(code)

    def generate_secret(self) -> str:
        return pyotp.random_base32()
