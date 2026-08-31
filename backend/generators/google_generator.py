"""
Google Generator which wraps the Gemini API.

Docs: https://ai.google.dev/gemini-api/docs.
"""

from typing import Optional
import io
import tempfile
import shutil
import asyncio
import json

from backend.config import get_settings
from backend.models.generators import Generator, Message
from backend.models.rate_limiting import RateLimitingMixin

from google import genai
from google.genai.types import Content, Part, FileData
from pydantic import BaseModel


gemini_roles = {
    "user": "user",
    "assistant": "model",
}

GEMINI_API_KEY = get_settings().gemini_api_key

# Global semaphore to limit concurrent API calls
# Adjust this value based on your API quota
API_CONCURRENCY_LIMIT = 10
api_semaphore = asyncio.Semaphore(API_CONCURRENCY_LIMIT)


class GoogleGenerator(RateLimitingMixin, Generator):
    # Primary model for URL extraction and other Gemini call sites.
    DEFAULT_MODEL_NAMES = (
        "gemini-3.5-flash",
        "gemini-2.5-flash",
    )

    def __init__(
        self,
        requests_per_minute=60,
        requests_per_day=1500,
        model_names: tuple[str, ...] | list[str] | None = None,
        **kwargs,
    ):
        # Initialize rate limiting with Gemini's typical limits
        super().__init__(
            requests_per_minute=requests_per_minute,
            requests_per_day=requests_per_day,
            **kwargs,
        )
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model_names = tuple(model_names or self.DEFAULT_MODEL_NAMES)

    async def format_messages(
        self, messages: list[Message]
    ) -> tuple[list[Content], list[str]]:
        """
        Format messages for the Gemini API.
        """
        contents = []

        # create a temporary directory
        temp_dir = await asyncio.to_thread(tempfile.mkdtemp)

        uploaded_file_names = []
        try:
            for message in messages:
                # can be either a string or a list of strings
                is_string_content = isinstance(message.content, str)
                parts = (
                    [Part(text=message.content)]
                    if is_string_content
                    else [Part(text=text) for text in message.content]
                )
                # Image inputs are only supported by OpenRouterGenerator.
                if message.image_urls:
                    print(
                        f"Warning: image URLs are not supported by GoogleGenerator: {message.image_urls}"
                    )

                if message.image_paths:
                    print(
                        f"Warning: image paths are not supported by GoogleGenerator: {message.image_paths}"
                    )

                if message.pdf_path is not None:
                    # Read and upload the PDF using the File API
                    def _read_and_upload_pdf():
                        with open(message.pdf_path, "rb") as f_read:
                            doc_io_bytes = f_read.read()
                        doc_io = io.BytesIO(doc_io_bytes)
                        return self.client.files.upload(
                            file=doc_io, config=dict(mime_type="application/pdf")
                        )

                    pdf_file = await asyncio.to_thread(_read_and_upload_pdf)
                    pdf_part = Part(
                        file_data=FileData(
                            mime_type=pdf_file.mime_type, file_uri=pdf_file.uri
                        )
                    )
                    parts = parts + [pdf_part]
                    uploaded_file_names.append(pdf_file.name)

                content = Content(role=gemini_roles[message.role], parts=parts)
                contents.append(content)
        finally:
            # clean up the temporary directory
            await asyncio.to_thread(shutil.rmtree, temp_dir)

        return contents, uploaded_file_names

    async def _call_gemini_api_internal(
        self,
        model_name: str,
        messages: list[Content],
        schema: Optional[BaseModel] = None,
        uploaded_file_names: list[str] = None,
    ) -> str:
        """Internal API call method without rate limiting (handled by mixin)."""
        config = None
        if schema is not None:
            config = {
                "response_mime_type": "application/json",
                "response_schema": schema,
            }

        # Use semaphore to limit concurrent API calls
        async with api_semaphore:
            response = await self.client.aio.models.generate_content(
                model=model_name,
                contents=messages,
                config=config,
            )

            # Log usage metadata
            if response.usage_metadata:
                print(
                    f"Token usage - Prompt: {response.usage_metadata.prompt_token_count}, "
                    f"Completion: {response.usage_metadata.candidates_token_count}, "
                    f"Total: {response.usage_metadata.total_token_count}"
                )

            # Clean up the files from Gemini storage
            if uploaded_file_names:
                for file_name in uploaded_file_names:
                    await asyncio.to_thread(self.client.files.delete, name=file_name)

            return response.text

    async def call_gemini_api(
        self,
        model_name: str,
        messages: list[Content],
        schema: Optional[BaseModel] = None,
        uploaded_file_names: list[str] = None,
    ) -> str:
        """Call Gemini API with rate limiting and retry logic."""
        return await self._execute_with_rate_limiting(
            self._call_gemini_api_internal,
            model_name,
            messages,
            schema,
            uploaded_file_names,
        )

    async def chat(
        self,
        messages: list[dict],
        schema: Optional[BaseModel] = None,
        uploaded_file_names: list[str] = None,
    ) -> tuple[str, str]:
        """
        Given a list of messages, this function generates a response using the Gemini API
        along with the model name used.
        """
        # Use configured models in priority order (first success wins).
        models = list(self.model_names)
        last_exception = None
        for model_name in models:
            try:
                response = await self.call_gemini_api(
                    model_name=model_name,
                    messages=messages,
                    schema=schema,
                    uploaded_file_names=uploaded_file_names,
                )
                return response, model_name
            except Exception as e:
                print(f"An error occurred with model {model_name}: {str(e)}")
                last_exception = e
                # Add a small delay before trying the next model to avoid immediate rate limiting
                if self._is_rate_limit_error(e):
                    print("Adding delay before trying next model...")
                    await asyncio.sleep(5)  # Small delay before trying next model
                elif self._is_service_unavailable_error(e):
                    print(
                        "Service unavailable - adding delay before trying next model..."
                    )
                    await asyncio.sleep(3)  # Small delay before trying next model
                continue
        if last_exception:
            raise last_exception
        return "", "No model succeeded"

    async def generate(
        self, messages: list[Message], schema: Optional[BaseModel] = None
    ) -> tuple[str, str]:
        formatted_messages, uploaded_file_names = await self.format_messages(messages)

        response, model_name = await self.chat(
            messages=formatted_messages,
            schema=schema,
            uploaded_file_names=uploaded_file_names,
        )

        if len(response) == 0 and model_name != "No model succeeded":
            print(
                "!!!! Gemini not returning anything, retrying with fewer messages (if applicable)"
            )
            if len(messages) > 4:
                messages_retry = messages[4:]
                (
                    formatted_messages_retry,
                    uploaded_file_names_retry,
                ) = await self.format_messages(messages_retry)
                response, model_name = await self.chat(
                    messages=formatted_messages_retry,
                    schema=schema,
                    uploaded_file_names=uploaded_file_names_retry,
                )
            else:
                print("!!!! Not enough messages to retry by slicing.")

        if schema is not None:
            response = json.loads(response) if isinstance(response, str) else response

        return response, model_name


if __name__ == "__main__":
    import asyncio

    async def test_google_generator():
        """Test the Google Gemini generator with rate limiting."""
        print("🧪 Testing Google Gemini Generator with Rate Limiting...")
        print(
            f"API Key loaded: {'Yes' if GEMINI_API_KEY else 'No'} (length: {len(GEMINI_API_KEY) if GEMINI_API_KEY else 0})"
        )

        try:
            # Test with typical Gemini limits
            generator = GoogleGenerator(requests_per_minute=60, requests_per_day=1500)

            # Show initial rate limit status
            print("\n📊 Initial Rate Limit Status:")
            status = generator.get_rate_limit_status()
            for key, value in status.items():
                print(f"   {key}: {value}")

            messages = [
                Message(
                    role="user",
                    content="Hello! Can you respond with a simple greeting?",
                )
            ]

            response, model_name = await generator.generate(messages)

            print("✅ Google Generator Success!")
            print(f"   Model: {model_name}")
            print(
                f"   Response: {response[:100]}{'...' if len(response) > 100 else ''}"
            )

            # Show updated rate limit status
            print("\n📊 Updated Rate Limit Status:")
            status = generator.get_rate_limit_status()
            for key, value in status.items():
                print(f"   {key}: {value}")

        except Exception as e:
            print(f"❌ Google Generator Failed: {str(e)}")
            import traceback

            traceback.print_exc()

    asyncio.run(test_google_generator())
