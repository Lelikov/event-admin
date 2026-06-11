import binascii

import pyotp
import structlog

from event_admin.interfaces.totp import ITOTPService


logger = structlog.get_logger(__name__)


class TOTPService(ITOTPService):
    def verify(self, code: str, secret: str) -> bool:
        """Verify a TOTP code; a malformed/empty secret fails closed (no 500)."""
        try:
            return pyotp.TOTP(secret).verify(code)
        except (binascii.Error, ValueError, TypeError, IndexError):
            logger.exception("totp_secret_malformed")
            return False

    def generate_secret(self) -> str:
        return pyotp.random_base32()
