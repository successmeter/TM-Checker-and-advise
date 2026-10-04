from typing import Protocol

from ..models import RegisterMark


class RegisterClient(Protocol):
    def search(self, mark: str, classes: list[int]) -> list[RegisterMark]:
        """Marks on the register that may conflict with `mark`. Callers score and filter the results."""
        ...
