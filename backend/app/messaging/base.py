from abc import ABC, abstractmethod

class Sender(ABC):
    @abstractmethod
    def send(self, identifier: str, text: str) -> dict:
        """Return {"ok": bool, "detail": str}."""
        ...