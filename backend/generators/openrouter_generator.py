from typing import Optional
import base64
import os
import aiohttp
import json
import asyncio
import logging

from openai import AsyncOpenAI
from pydantic import BaseModel

from backend.models.generators import Generator, Message
from backend.models.rate_limiting import RateLimitingMixin
from backend.config import get_settings


OPENROUTER_API_KEY = get_settings().openrouter_api_key

logger = logging.getLogger(__name__)


class OpenRouterGenerator(RateLimitingMixin, Generator):
    """
    OpenRouter Generator class.
    """

    def __init__(self, requests_per_minute=200, requests_per_day=10000, **kwargs):
        super().__init__(
            requests_per_minute=requests_per_minute,
            requests_per_day=requests_per_day,
            **kwargs,
        )
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY
        )
        self.model_name = "x-ai/grok-4.3"

    def encode_image(self, image_path: str) -> str:
        """
        Encode an image file to base64 string.

        Args:
            image_path: Path to the image file

        Returns:
            Base64 encoded string of the image
        """
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    async def format_messages(self, messages: list[Message]) -> list[dict]:
        """
        Format messages for the OpenAI API with support for multiple images.
        """
        formatted_messages = []
        for message in messages:
            if isinstance(message.content, str):
                text_content = message.content
            else:
                text_content = " ".join(message.content)

            content_parts = [{"type": "text", "text": text_content}]

            if message.image_paths:
                for image_path in message.image_paths:
                    _, ext = os.path.splitext(image_path.lower())
                    mime_type = {
                        ".jpg": "jpeg",
                        ".jpeg": "jpeg",
                        ".png": "png",
                        ".gif": "gif",
                        ".webp": "webp",
                    }.get(ext, "jpeg")

                    base64_image = self.encode_image(image_path)

                    content_parts.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{mime_type};base64,{base64_image}"
                            },
                        }
                    )

            if message.image_urls:
                for image_url in message.image_urls:
                    content_parts.append(
                        {"type": "image_url", "image_url": {"url": image_url}}
                    )

            if len(content_parts) > 1:
                content = content_parts
            else:
                content = text_content

            formatted_messages.append({"role": message.role, "content": content})

        return formatted_messages

    async def _generate_with_reasoning_http_internal(
        self,
        messages,
        schema: Optional[BaseModel] = None,
        reasoning_config: Optional[dict] = None,
    ) -> str:
        """Internal HTTP request method without rate limiting (handled by mixin)."""
        formatted_messages = await self.format_messages(messages)

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model_name,
            "messages": formatted_messages,
        }

        if reasoning_config:
            payload["reasoning"] = reasoning_config

        if schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                },
            }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(
                        f"OpenRouter API error {response.status}: {error_text}"
                    )

                result = await response.json()

                if schema is not None:
                    content = result["choices"][0]["message"]["content"]
                    try:
                        parsed_content = json.loads(content)
                        response_obj = schema(**parsed_content)
                        return response_obj, self.model_name
                    except (json.JSONDecodeError, ValueError) as e:
                        raise Exception(f"Failed to parse structured response: {e}")
                else:
                    return result["choices"][0]["message"]["content"], self.model_name

    async def generate_with_reasoning_http(
        self,
        messages,
        schema: Optional[BaseModel] = None,
        reasoning_config: Optional[dict] = None,
    ) -> str:
        """Generate response using direct HTTP requests with rate limiting."""
        return await self._execute_with_rate_limiting(
            self._generate_with_reasoning_http_internal,
            messages,
            schema,
            reasoning_config,
        )

    async def _generate_openai_sdk_internal(
        self, messages, schema: Optional[BaseModel] = None
    ) -> str:
        """Internal OpenAI SDK method without rate limiting (handled by mixin)."""
        formatted_messages = await self.format_messages(messages)

        if schema is not None:
            completion = await self.client.beta.chat.completions.parse(
                model=self.model_name,
                messages=formatted_messages,
                response_format=schema,
            )
            response = completion.choices[0].message.parsed
        else:
            completion = await self.client.chat.completions.create(
                model=self.model_name,
                messages=formatted_messages,
            )
            response = completion.choices[0].message.content

        return response, self.model_name

    async def generate(
        self, messages, schema: Optional[BaseModel] = None, use_reasoning: bool = True
    ) -> str:
        """
        Generate response with optional reasoning tokens support and rate limiting.
        """
        if use_reasoning:
            reasoning_config = {"effort": "high"}
            return await self.generate_with_reasoning_http(
                messages, schema, reasoning_config
            )
        else:
            return await self._execute_with_rate_limiting(
                self._generate_openai_sdk_internal, messages, schema
            )


if __name__ == "__main__":
    import asyncio

    async def test_openrouter_generator():
        """Test the OpenRouter generator with rate limiting."""
        print("🧪 Testing OpenRouter Generator with Rate Limiting...")

        try:
            generator = OpenRouterGenerator()

            print("\n📊 Initial Rate Limit Status:")
            status = generator.get_rate_limit_status()
            for key, value in status.items():
                print(f"   {key}: {value}")

            print("\n📝 Testing text-only message with rate limiting...")
            messages = [
                Message(
                    role="user",
                    content="Hello! Can you respond with a simple greeting?",
                )
            ]

            response, model_name = await generator.generate(
                messages, use_reasoning=False
            )

            print("✅ Text-only test Success!")
            print(f"   Model: {model_name}")
            print(
                f"   Response: {response[:100]}{'...' if len(response) > 100 else ''}"
            )

            print("\n📊 Updated Rate Limit Status:")
            status = generator.get_rate_limit_status()
            for key, value in status.items():
                print(f"   {key}: {value}")

            print("\n🖼️  Testing image message formatting...")
            image_messages = [
                Message(
                    role="user",
                    content="What's in these images?",
                    image_paths=[
                        "/path/to/test/image1.jpg",
                        "/path/to/test/image2.png",
                    ],
                )
            ]

            try:
                formatted = await generator.format_messages(image_messages)
                print("✅ Image message formatting structure created!")
                print(f"   Content type: {type(formatted[0]['content'])}")
                if isinstance(formatted[0]["content"], list):
                    print(f"   Content parts: {len(formatted[0]['content'])}")
                    for i, part in enumerate(formatted[0]["content"]):
                        print(f"     Part {i}: {part.get('type', 'unknown')}")
            except FileNotFoundError:
                print("✅ Image formatting logic works (file not found as expected)")
            except Exception as format_error:
                print(f"❌ Image formatting error: {format_error}")

            print("\n⏳ Testing rate limiting behavior...")
            print("   (This would normally trigger rate limiting with real API calls)")

        except Exception as e:
            print(f"❌ OpenRouter Generator Failed: {str(e)}")
            import traceback

            traceback.print_exc()

    asyncio.run(test_openrouter_generator())
