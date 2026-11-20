"""
Base models for AI generators and messages.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Union
from pydantic import BaseModel


class Message(BaseModel):
    """Message model for generator inputs."""

    role: str
    content: Union[str, List[str]]
    image_paths: Optional[List[str]] = None
    image_urls: Optional[List[str]] = None
    pdf_path: Optional[str] = None


class Generator(ABC):
    """Abstract base class for AI generators."""

    @abstractmethod
    async def generate(
        self, messages: List[Message], schema: Optional[BaseModel] = None
    ) -> tuple[str, str]:
        """
        Generate a response from the given messages.

        Args:
            messages: List of Message objects
            schema: Optional Pydantic schema for structured output

        Returns:
            Tuple of (response, model_name)
        """
        pass

    @abstractmethod
    async def format_messages(self, messages: List[Message]):
        """Format messages for the specific API."""
        pass
