"""Interface for the URL-shortener stats client."""

from typing import Protocol


class IShortenerClient(Protocol):
    async def get_click_count(self, ident: str) -> int | None: ...
