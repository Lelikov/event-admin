from __future__ import annotations
from typing import Protocol


class ITOTPService(Protocol):
    def verify(self, code: str, secret: str) -> bool: ...

    def generate_secret(self) -> str: ...
