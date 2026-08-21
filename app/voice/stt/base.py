from abc import ABC, abstractmethod


class BaseSTT(ABC):

    @abstractmethod
    async def transcribe(
        self,
        audio: bytes,
    ) -> str:
        """
        Convert speech audio into text.
        """
        raise NotImplementedError