from __future__ import annotations
from typing import Protocol


class IPasswordService(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, plain: str, hashed: str) -> bool: ...
