from abc import ABC, abstractmethod


class BaseTTS(ABC):

    @abstractmethod
    async def synthesize(
        self,
        text: str,
    ) -> bytes:
        """
        Convert text into speech audio.
        """
        raise NotImplementedError