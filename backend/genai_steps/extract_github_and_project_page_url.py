"""
This step uses an LLM to get the Github URL and project page URL
from a given paper, using the comments of the paper page + first 2 pages of the PDF.

You can run it like so:
```bash
uv run --env-file backend/keys.env -m backend.genai_steps.extract_github_and_project_page_url --arxiv_id 2409.18313
```
"""

import argparse
from typing import Optional
import asyncio
import os
from pathlib import Path
import logging
import time

from pydantic import BaseModel

from huggingface_hub import hf_hub_download

from backend.utils.prompt_utils import load_prompt
from backend.utils.logging_utils import async_export_txt
from backend.utils.verify_url import verify_url
from backend.utils.pdf_utils import (
    extract_text_from_pdf,
    safe_extract_hyperlinks_async,
    temp_pdf_download,
    find_project_page_url,
    safe_pdf_to_images_async,
    cleanup_image_files,
    extract_first_two_pages_pymupdf,
)
from backend.utils.paper_utils import (
    get_abstract,
    get_comments,
    find_github_url,
    get_github_and_project_page_urls_from_daily_papers,
)

from backend.models.generators import Message
from backend.generators.openrouter_generator import OpenRouterGenerator
from backend.models.generators import Generator
from backend.operator_profile import OPERATOR


class Response(BaseModel):
    reasoning: str
    github_url: str
    project_page_url: str


# Set up logging
logger = logging.getLogger(__name__)

# Initialize variables
template = load_prompt("extract_github_and_project_page_url.json")

# ArXiv rate limiting - 3 seconds between requests
ARXIV_RATE_LIMIT_DELAY = 3.0
_last_arxiv_request_time = None


async def _rate_limit_arxiv():
    """Ensure we respect ArXiv's rate limit of 1 request per 3 seconds."""
    global _last_arxiv_request_time

    if _last_arxiv_request_time is not None:
        elapsed = time.time() - _last_arxiv_request_time
        if elapsed < ARXIV_RATE_LIMIT_DELAY:
            wait_time = ARXIV_RATE_LIMIT_DELAY - elapsed
            logger.debug(
                f"Rate limiting: waiting {wait_time:.2f}s before ArXiv request"
            )
            await asyncio.sleep(wait_time)

    _last_arxiv_request_time = time.time()


class FewShotPDFCache:
    """Cache for few-shot example PDFs to avoid repeated downloads."""

    def __init__(self, cache_dir: str = "backend/few_shot_pdfs_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self._cached_paths = {}

    async def get_pdf_path(self, idx: int) -> str:
        """Get cached PDF path, downloading if necessary."""
        if idx in self._cached_paths:
            cached_path = self._cached_paths[idx]
            if os.path.exists(cached_path):
                logger.debug(f"Using cached PDF for index {idx}: {cached_path}")
                return cached_path

        # Download and cache the PDF
        cache_filename = f"few_shot_pdf_{idx}.pdf"
        cached_path = self.cache_dir / cache_filename

        try:
            logger.info(f"Downloading few-shot PDF {idx} to cache...")
            downloaded_path = await asyncio.to_thread(
                hf_hub_download,
                repo_id=OPERATOR.paper_page_assets_repo,
                filename=f"paper_pdfs_step_1/pdf_{idx}.pdf",
                repo_type="dataset",
            )

            # Copy to our cache directory
            await asyncio.to_thread(
                lambda: __import__("shutil").copy2(downloaded_path, cached_path)
            )

            self._cached_paths[idx] = str(cached_path)
            logger.info(f"Cached few-shot PDF {idx} at: {cached_path}")
            return str(cached_path)

        except Exception as e:
            logger.error(f"Failed to download/cache few-shot PDF {idx}: {e}")
            raise

    def get_cache_info(self) -> dict:
        """Get information about cached PDFs."""
        cached_files = list(self.cache_dir.glob("*.pdf"))
        return {
            "cache_dir": str(self.cache_dir),
            "cached_count": len(cached_files),
            "cached_files": [f.name for f in cached_files],
            "total_size_mb": sum(f.stat().st_size for f in cached_files)
            / (1024 * 1024),
        }


class FewShotManager:
    """Manages few-shot examples for the URL extraction task."""

    def __init__(self, pdf_cache: FewShotPDFCache):
        self.pdf_cache = pdf_cache
        self._cached_messages = None
        self._cached_image_paths = []

    async def get_few_shot_messages(self, generator=None) -> list[Message]:
        """Get cached few-shot messages, creating them if necessary."""
        # Use cached messages if available
        if self._cached_messages is not None:
            logger.debug("Using cached few-shot messages")
            return self._cached_messages

        logger.info("Creating few-shot messages...")
        messages = []
        all_image_paths = []

        for idx, (few_shot_arxiv_id, response_content) in enumerate(
            zip(arxiv_ids, responses)
        ):
            try:
                # Get cached PDF path
                pdf_file_path = await self.pdf_cache.get_pdf_path(idx)

                # Create user message
                message = await create_user_message(few_shot_arxiv_id, pdf_file_path)
                messages.append(message)
                messages.append(Message(role="assistant", content=response_content))

                # Track image paths for cleanup
                if hasattr(message, "image_paths") and message.image_paths:
                    all_image_paths.extend(message.image_paths)

            except Exception as e:
                logger.error(
                    f"Failed to create few-shot message for {few_shot_arxiv_id}: {e}"
                )
                continue

        self._cached_messages = messages
        self._cached_image_paths = all_image_paths
        logger.info(f"Created {len(messages)} few-shot messages")
        return messages

    def cleanup_images(self):
        """Clean up temporary image files from few-shot examples."""
        if self._cached_image_paths:
            logger.info(
                f"Cleaning up {len(self._cached_image_paths)} few-shot image files..."
            )
            cleanup_image_files(self._cached_image_paths)
            self._cached_image_paths = []


# Global instances
pdf_cache = FewShotPDFCache()
few_shot_manager = FewShotManager(pdf_cache)


# add few-shots
arxiv_ids = [
    "2409.18313",
    "2410.00337",
    "2410.02760",
    "2410.02613",
    "2410.02362",
    "2410.04534",
    "2410.05080",
    "2410.04422",
    "2410.13852",
    "2408.00714",
]

responses = [
    '{"reasoning": "**Abstract**\\n\\nThe abstract of the paper does not mention any Github or project page URL.\\n\\n**Hugging Face Paper Page:**\\n\\nThe Hugging Face paper page does not mention any Github or project page URL.\\n\\n**PDF (First 2 Pages):**\\n\\nThe first page of the PDF includes a footnote, which mentions the project page URL: https://quanting-xie.github.io/Embodied-RAG-web/. The Github URL is not mentioned.", "github_url": "", "project_page_url": "https://quanting-xie.github.io/Embodied-RAG-web/"}',
    '{"reasoning": "**Abstract**\\n\\nThe abstract of the paper does not mention any Github or project page URL.\\n\\n**Hugging Face Paper Page:**\\n\\nThe Hugging Face paper page includes a comment mentioning the project page: https://len-li.github.io/syntheocc-web/. The Github URL is not mentioned.\\n\\n**PDF (First 2 Pages):**\\n\\nThe first page of the PDF also mentions the same project page: https://len-li.github.io/syntheocc-web/. The Github URL is not mentioned.", "github_url": "", "project_page_url": "https://len-li.github.io/syntheocc-web/"}',
    '{"reasoning": "**Abstract**\\n\\nThe abstract of the paper mentions \\"Our code, data, and trained models are available at https://elm.baulab.info\\". Hence, the project page URL is https://elm.baulab.info/.\\nThe Github URL is not mentioned.\\n\\n**Hugging Face Paper Page:**\\n\\nThe Hugging Face paper page includes a comment mentioning the project page: https://elm.baulab.info/, link to the Github repository: https://github.com/rohitgandikota/erasing-llm\\nand trained models: https://elm.baulab.info/models/elm-wmdp/.\\n\\n**PDF (First 2 Pages):**\\n\\nThe first page of the PDF mentions the project page at the end of the abstract: https://elm.baulab.info/. The Github URL is not mentioned.", "github_url": "https://github.com/rohitgandikota/erasing-llm", "project_page_url": "https://elm.baulab.info/"}',
    '{"reasoning": "**Abstract**\\n\\nThe abstract of the paper does not mention any Github or project page URL.\\n\\n**Hugging Face Paper Page:**\\n\\nThe Hugging Face paper page includes one comment, but does not include any links to the project page or Github repository.\\n\\n**PDF (First 2 Pages):**\\n\\nThe first page of the PDF includes a footnote which mentions the project page URL: https://venturamor.github.io/NLEye/. The Github URL is not mentioned.", "github_url": "", "project_page_url": "https://venturamor.github.io/NLEye/"}',
    '{"reasoning": "**Abstract**\\n\\nThe abstract mentions \\"A comprehensive list of Mamba architectures applied in the medical field, reviewed in this work, is available at Github\\", but\\ndoes not include a direct link to the repository. The project page URL is not mentioned.\\n\\n**Hugging Face Paper Page:**\\n\\nThe Hugging Face paper page includes a comment mentioning \\"You can access the papers covered in this survey through the following link: https://github.com/madhavaprasath23/awesome-mamba-papers-on-medical-domain\\".\\nHence, the Github URL is https://github.com/madhavaprasath23/awesome-mamba-papers-on-medical-domain. The project page URL is not mentioned.\\n\\n**PDF (First 2 Pages):**\\n\\nThe first page of the PDF includes a link to the Github repository: https://github.com/Madhavaprasath23/Awesome-Mamba-Papers-On-Medical-Domain. The project page is not mentioned.", "github_url": "https://github.com/Madhavaprasath23/Awesome-Mamba-Papers-On-Medical-Domain", "project_page_url": ""}',
    '{"reasoning": "**Abstract**\\n\\nThe abstract mentions: \\"Quantitative results are available in the https://hanyangclarence.github.io/unimumo_demo/{project page}.\\" Hence, the project page URL\\nis https://hanyangclarence.github.io/unimumo_demo. The Github URL is not mentioned.\\n\\n**Hugging Face Paper Page:**\\n\\nThe Hugging Face paper page includes a comment by akhaliq mentioning the project page: https://hanyangclarence.github.io/unimumo_demo/.\\nA similar link is present in the abstract. The Github URL is not mentioned.\\n\\n**PDF (First 2 Pages):**\\n\\nThe first page of the PDF includes a link to the project page: https://hanyangclarence.github.io/unimumo_demo/. The Github URL is not mentioned.", "github_url": "", "project_page_url": "https://hanyangclarence.github.io/unimumo_demo/"}',
    '{"reasoning": "**Abstract**\\n\\nThe abstract does not include any Github or project page URL.\\n\\n**Hugging Face Paper Page:**\\n\\nThe Hugging Face paper page does not mention any Github or project page URL in the comments.\\n\\n**PDF (First 2 Pages):**\\n\\nThe first page of the PDF includes a link to the project page: https://osu-nlp-group.github.io/ScienceAgentBench/. The Github URL is not mentioned.", "github_url": "", "project_page_url": "https://osu-nlp-group.github.io/ScienceAgentBench/"}',
    '{"reasoning": "**Abstract**\\n\\nThe abstract does not include any Github or project page URL.\\n\\n**Hugging Face Paper Page:**\\n\\nThe Hugging Face paper page includes a comment by the author, stating that \\"Our code is publicly available at https://github.com/yuyijiong/hard_retrieval_for_llm\\".\\nHence, the Github URL is https://github.com/yuyijiong/hard_retrieval_for_llm. The project page URL is not mentioned.\\n\\n**PDF (First 2 Pages):**\\n\\nThe first page of the PDF includes a link to the Github repository: https://github.com/yuyijiong/hard_retrieval_for_llm/. The project page URL is not mentioned.", "github_url": "https://github.com/yuyijiong/hard_retrieval_for_llm", "project_page_url": ""}',
    '{"reasoning": "**Abstract**\\nThe abstract does not include any Github or project page URL.\\n\\n**Hugging Face Paper Page:**\\n\\nThe Hugging Face paper page includes a comment by the author, but it does not include a Github or project page URL.\\n\\n**PDF (First 2 Pages):**\\n\\nThe second page of the PDF includes the sentence \\"Our code, data, and models are at https://lil-lab.github.io/respect.\\". Given this link includes\\ngithub.io, it is likely the project page URL. The Github URL is not mentioned.", "github_url": "", "project_page_url": "https://lil-lab.github.io/respect"}',
    '{"reasoning": "**Abstract**\\nThe abstract mentions \\"We are releasing a version of our model, the dataset and an interactive demo.\\", but does not include any Github or project page URL.\\n\\n**Hugging Face Paper Page:**\\n\\nThe Hugging Face paper page includes a comment specifying https://ai.meta.com/sam2/, hence this refers to the project page. A Github URL is not mentioned.\\n\\n**PDF (First 2 Pages):**\\n\\nThe first page of the PDF mentions \\"Code: https://github.com/facebookresearch/sam2, Website: https://ai.meta.com/sam2/\\". Hence both the Github URL and project page\\nURL are mentioned.", "github_url": "https://github.com/facebookresearch/sam2", "project_page_url": "https://ai.meta.com/sam2/"}',
]


async def create_user_message(
    arxiv_id: str, pdf_file_path: str = None, abstract: str = None
) -> Message:
    """
    Create a user message for the Gemini API in an asynchronous manner.

    Args:
        arxiv_id: ArXiv ID of the paper
        pdf_file_path: Path to the PDF file
        abstract: Optional pre-fetched abstract. If None, will fetch from web.
    """
    # Get the abstract of the paper
    if abstract is None:
        abstract = await get_abstract(arxiv_id=arxiv_id)

    # Get the comments of the paper page
    paper_page_comments = await get_comments(arxiv_id=arxiv_id)

    # Get the text of the first two pages of the PDF
    pdf_text = await asyncio.to_thread(extract_text_from_pdf, pdf_path=pdf_file_path)

    # Get the hyperlinks of the first two pages of the PDF
    hyperlinks = await safe_extract_hyperlinks_async(pdf_file_path, timeout_seconds=10)

    prompt = template.format(
        abstract=abstract,
        paper_page_comments=paper_page_comments,
        pdf_text=pdf_text,
        hyperlinks=hyperlinks,
    )

    await async_export_txt(
        filename="extract_github_and_project_page_url_prompt", value=prompt
    )

    # Extract the images from the PDF
    image_paths = await safe_pdf_to_images_async(pdf_file_path, timeout_seconds=30)

    message = Message(
        role="user", content=prompt, pdf_path=pdf_file_path, image_paths=image_paths
    )

    return message


async def get_project_github_urls(
    arxiv_id: str,
    session_id: str = None,
    github_url: Optional[str] = None,
    use_reasoning: bool = True,
    abstract: Optional[str] = None,
    generator: Optional[Generator] = None,
) -> tuple[str, dict]:
    """
    Extract GitHub and project page URLs for a given paper.

    Args:
        arxiv_id: ArXiv ID of the paper
        session_id: Session ID (unused but kept for compatibility)
        github_url: Pre-existing GitHub URL (unused but kept for compatibility)
        use_reasoning: Whether to use reasoning in LLM generation
        abstract: Optional pre-fetched abstract
        generator: Optional Generator instance to use (defaults to OpenRouterGenerator)

    Returns:
        Tuple of (reasoning, response_dict)

    Raises:
        Exception: If rate limiting, quota exceeded, or PDF download fails
    """
    reasoning = ""
    github_url = ""
    project_page_url = ""

    # Step 1: Try simple extraction methods first (without PDF)
    print("Step 1: Trying simple methods...")
    (
        github_url,
        project_page_url,
    ) = await get_github_and_project_page_urls_from_daily_papers(arxiv_id)

    if not github_url:
        github_url = await find_github_url(arxiv_id=arxiv_id, abstract=abstract)

    print(f"Step 1: Github URL: {github_url}, Project page URL: {project_page_url}")

    # Step 2: Use LLM (only if URLs not found and requires PDF download)
    if not github_url or not project_page_url:
        print(
            "Not all URLs found with simple methods, downloading PDF and trying LLM..."
        )

        try:
            # Apply rate limiting before downloading from ArXiv
            await _rate_limit_arxiv()

            async with temp_pdf_download(arxiv_id=arxiv_id) as (
                pdf_path,
                error_message,
            ):
                # Check if download failed
                if pdf_path is None or error_message is not None:
                    error_msg = error_message or "Unknown error"

                    # Check if it's a critical error (reCAPTCHA, rate limiting, etc.)
                    error_str = error_msg.lower()
                    is_critical = (
                        "recaptcha" in error_str
                        or "captcha" in error_str
                        or "rate limit" in error_str
                        or "429" in error_str
                    )

                    if is_critical:
                        raise Exception(
                            f"Failed to download PDF for {arxiv_id}: {error_msg}"
                        )
                    else:
                        # Non-critical error, log and continue
                        print(f"Failed to download PDF for {arxiv_id}: {error_msg}")
                        # Continue with whatever URLs we found
                        return reasoning, {
                            "github_url": github_url,
                            "project_page_url": project_page_url,
                        }

                # PDF downloaded successfully, process it
                pdf_path_processed = await extract_first_two_pages_pymupdf(pdf_path)

                # Try PDF-based project page extraction if not found yet
                if not project_page_url:
                    project_page_url = await find_project_page_url(
                        pdf_path=pdf_path_processed
                    )

                # Use LLM if still missing URLs
                if not github_url or not project_page_url:
                    reasoning, llm_response = await _extract_urls_with_llm(
                        arxiv_id, pdf_path_processed, abstract, use_reasoning, generator
                    )

                    if not github_url and llm_response.get("github_url"):
                        github_url = llm_response["github_url"]
                    if not project_page_url and llm_response.get("project_page_url"):
                        project_page_url = llm_response["project_page_url"]

        except Exception as e:
            # Re-raise critical errors (rate limiting, quota, PDF download failures, reCAPTCHA, API key errors)
            error_str = str(e).lower()
            auth_markers = [
                "api key",
                "invalid_api_key",
                "api_key_invalid",
                "expired",
                "unauthorized",
                "forbidden",
                "permission",
                "not authenticated",
                "unauthenticated",
                "invalid authentication",
                "key not active",
                "insufficient authentication",
            ]
            is_critical = (
                "rate limit" in error_str
                or "429" in str(e)
                or "quota" in error_str
                or "failed to download pdf" in error_str
                or "recaptcha" in error_str
                or "captcha" in error_str
                or any(marker in error_str for marker in auth_markers)
            )

            if is_critical:
                raise  # Re-raise as-is with full context

            # For non-critical errors, log and continue with whatever URLs we found
            print(f"Non-critical error during PDF processing: {e}")
            # Continue with github_url and project_page_url as they are (may be empty)

    response = {
        "github_url": github_url,
        "project_page_url": project_page_url,
    }

    return reasoning, response


async def _extract_urls_with_llm(
    arxiv_id: str,
    pdf_path: str,
    abstract: Optional[str],
    use_reasoning: bool,
    generator: Optional[Generator] = None,
) -> tuple[str, dict]:
    """
    Extract URLs using LLM with few-shot examples.

    Args:
        arxiv_id: ArXiv ID of the paper
        pdf_path: Path to the PDF file
        abstract: Optional pre-fetched abstract
        use_reasoning: Whether to use reasoning in LLM generation
        generator: Optional Generator instance to use (defaults to OpenRouterGenerator)

    Returns:
        Tuple of (reasoning, response_dict)
    """
    if generator is None:
        generator = OpenRouterGenerator()

    # Get few-shot messages (cached after first call)
    few_shot_messages = await few_shot_manager.get_few_shot_messages(generator)

    # Create query message
    print("Processing main query...")
    query_message = await create_user_message(arxiv_id, pdf_path, abstract)

    # Combine few-shot examples with query
    messages = few_shot_messages + [query_message]

    query_image_paths = []
    if hasattr(query_message, "image_paths") and query_message.image_paths:
        query_image_paths = query_message.image_paths

    try:
        # Check if generator supports use_reasoning parameter
        from backend.generators.google_generator import GoogleGenerator

        if isinstance(generator, GoogleGenerator):
            # GoogleGenerator doesn't support use_reasoning
            response_str, _ = await generator.generate(
                messages=messages, schema=Response
            )
        else:
            # OpenRouterGenerator supports use_reasoning
            response_str, _ = await generator.generate(
                messages=messages, schema=Response, use_reasoning=use_reasoning
            )

        # Handle different response types (Pydantic model vs dict)
        if isinstance(response_str, dict):
            reasoning = response_str.get("reasoning", "")
            project_page_url = response_str.get("project_page_url", "")
            github_url = response_str.get("github_url", "")
        else:
            reasoning = response_str.reasoning
            project_page_url = response_str.project_page_url
            github_url = response_str.github_url

        # Verify the project page URL
        if isinstance(project_page_url, str) and project_page_url:
            is_valid_url = await verify_url(project_page_url)
            project_page_url = project_page_url if is_valid_url else ""

        response = {
            "github_url": github_url,
            "project_page_url": project_page_url,
        }

        return reasoning, response

    except Exception as e:
        logger.error(f"LLM extraction failed for {arxiv_id}: {e}")
        # Re-raise critical errors that should stop processing
        error_str = str(e).lower()
        auth_markers = [
            "api key",
            "invalid_api_key",
            "api_key_invalid",
            "expired",
            "unauthorized",
            "forbidden",
            "permission",
            "not authenticated",
            "unauthenticated",
            "invalid authentication",
            "key not active",
            "insufficient authentication",
        ]
        is_critical = (
            "rate limit" in error_str
            or "429" in str(e)
            or "quota exceeded" in error_str
            or any(marker in error_str for marker in auth_markers)
        )
        if is_critical:
            raise Exception(f"Critical error: {e}") from e
        # For other errors, return empty results
        return "", {"github_url": "", "project_page_url": ""}
    finally:
        # Clean up query-specific image files
        if query_image_paths:
            print(f"Cleaning up {len(query_image_paths)} query image files...")
            cleanup_image_files(query_image_paths)


async def warm_pdf_cache():
    """Pre-download all few-shot PDFs and create few-shot messages cache."""
    logger.info("Warming PDF cache with few-shot examples...")

    for idx in range(len(arxiv_ids)):
        try:
            await pdf_cache.get_pdf_path(idx)
        except Exception as e:
            logger.error(f"Failed to cache PDF {idx}: {e}")

    cache_info = pdf_cache.get_cache_info()
    logger.info(
        f"PDF cache ready: {cache_info['cached_count']} files, {cache_info['total_size_mb']:.1f} MB"
    )

    # Also warm the few-shot messages cache
    logger.info("Warming few-shot messages cache...")
    try:
        messages = await few_shot_manager.get_few_shot_messages(generator=None)
        logger.info(f"Few-shot messages cache ready: {len(messages)} messages")
    except Exception as e:
        logger.error(f"Failed to warm few-shot messages cache: {e}")

    return cache_info


async def main(
    arxiv_id: str, use_reasoning: bool = True, abstract: Optional[str] = None
):
    # Show cache info
    cache_info = pdf_cache.get_cache_info()
    print(
        f"📋 PDF Cache: {cache_info['cached_count']}/{len(arxiv_ids)} files cached ({cache_info['total_size_mb']:.1f} MB)"
    )

    try:
        reasoning, response = await get_project_github_urls(
            arxiv_id=arxiv_id,
            session_id=None,
            use_reasoning=use_reasoning,
            abstract=abstract,
        )

        print("\n" + "=" * 50)
        print("FINAL RESULTS:")
        print("=" * 50)
        print(f"ArXiv ID: {arxiv_id}")
        print(f"GitHub URL: {response.get('github_url', 'Not found')}")
        print(f"Project Page URL: {response.get('project_page_url', 'Not found')}")
        if reasoning:
            print(f"Reasoning: {reasoning}")
        print("=" * 50)
    finally:
        few_shot_manager.cleanup_images()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Get Github URL and project page URL from paper."
    )
    parser.add_argument(
        "--arxiv_id", type=str, help="Arxiv ID of the paper.", default="2509.14033"
    )
    parser.add_argument(
        "--no-reasoning", action="store_true", help="Disable reasoning tokens"
    )
    parser.add_argument(
        "--warm-cache",
        action="store_true",
        help="Pre-download all few-shot PDFs to cache and exit",
    )
    args = parser.parse_args()

    if args.warm_cache:
        asyncio.run(warm_pdf_cache())
    else:
        asyncio.run(main(args.arxiv_id, use_reasoning=not args.no_reasoning))
