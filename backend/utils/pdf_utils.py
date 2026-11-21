from typing import List, Callable, Any, TypeVar
from contextlib import asynccontextmanager
import asyncio
import aiohttp
import logging
import tempfile
import os
import re

import fitz
from PyPDF2 import PdfReader
from pdf2image import convert_from_path
import pdfplumber
from pdfminer.psexceptions import PSException
from pdfplumber.utils.exceptions import MalformedPDFException, PdfminerException

T = TypeVar("T")
logger = logging.getLogger(__name__)

PROJECT_PAGE_URL_PATTERN = r"\bhttps?://[a-zA-Z0-9.-]+\.github\.io[^\s]*"


async def safe_regex_search_async(pattern: str, text: str, timeout_seconds: int = 5):
    """
    Perform regex search with asyncio timeout to prevent hanging.
    """
    try:
        match = await asyncio.wait_for(
            asyncio.to_thread(re.search, pattern, text), timeout=timeout_seconds
        )
        return match
    except asyncio.TimeoutError:
        print(f"Regex search timed out after {timeout_seconds} seconds")
        return None
    except Exception as e:
        print(f"Error during regex search: {e}")
        return None


def extract_text_from_pdf(pdf_path: str, num_pages: int = 2) -> str:
    """
    Extract text of the first number of pages from a PDF file.
    """
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages[:num_pages]:
        text += page.extract_text()

    return text


def extract_hyperlinks_from_pdf(pdf_path):
    """
    Extract all hyperlinks from a PDF file.

    Args:
        pdf_path (str): Path to PDF file

    Returns:
        list: List of dictionaries containing link text and URL
    """
    links = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                annotations = page.hyperlinks
                if annotations:
                    for link in annotations:
                        if "uri" in link:
                            text = ""
                            if "text" in link:
                                text = link["text"]
                            elif "bbox" in link:
                                bbox = link["bbox"]
                                crop = page.crop(bbox)
                                text = crop.extract_text() or ""

                            links.append({"text": text.strip(), "url": link["uri"]})
    except (PdfminerException, MalformedPDFException, PSException):
        logger.exception("Could not read hyperlinks from PDF %s", pdf_path)
        return []

    return links


async def safe_extract_hyperlinks_async(pdf_path: str, timeout_seconds: int = 10):
    """
    Extract hyperlinks with timeout protection.
    """
    try:
        links = await asyncio.wait_for(
            asyncio.to_thread(extract_hyperlinks_from_pdf, pdf_path),
            timeout=timeout_seconds,
        )
        return links
    except asyncio.TimeoutError:
        print(f"Hyperlink extraction timed out after {timeout_seconds} seconds")
        return []


def pdf_to_images_sync(pdf_path: str, pages: List[int] = [1, 2]) -> List[str]:
    """
    Convert PDF pages to images and return list of image paths.
    """
    temp_files = []
    try:
        images = convert_from_path(pdf_path, first_page=pages[0], last_page=pages[-1])

        for i, image in enumerate(images):
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                image.save(temp_file.name, "PNG")
                temp_files.append(temp_file.name)

        return temp_files
    except Exception as e:
        print(f"Error converting PDF to images: {e}")
        for temp_file in temp_files:
            try:
                os.unlink(temp_file)
            except:  # noqa: E722
                pass
        return []


async def safe_pdf_to_images_async(pdf_path: str, timeout_seconds: int = 30):
    """
    Convert PDF to images with timeout protection.
    """
    try:
        image_paths = await asyncio.wait_for(
            asyncio.to_thread(pdf_to_images_sync, pdf_path), timeout=timeout_seconds
        )
        return image_paths
    except asyncio.TimeoutError:
        print(f"PDF to images conversion timed out after {timeout_seconds} seconds")
        return []
    except Exception as e:
        print(f"Error during PDF to images conversion: {e}")
        return []


def cleanup_image_files(image_paths: List[str]):
    """
    Clean up temporary image files.
    """
    for image_path in image_paths:
        try:
            os.unlink(image_path)
        except Exception:
            pass


def _is_valid_pdf(content: bytes) -> tuple[bool, str]:
    """
    Check if the downloaded content is a valid PDF file.

    Args:
        content: The downloaded file content

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not content.startswith(b"%PDF-"):
        if content.startswith(b"<!DOCTYPE") or content.startswith(b"<html"):
            if b"recaptcha" in content.lower() or b"captcha" in content.lower():
                return False, "ArXiv returned reCAPTCHA page (rate limited)"
            return False, "ArXiv returned HTML page instead of PDF"
        return False, "Downloaded file is not a valid PDF (missing PDF magic bytes)"

    content_stripped = content.rstrip()
    if not content_stripped.endswith(b"%%EOF"):
        return False, "Downloaded file appears to be truncated (missing PDF EOF marker)"

    if len(content) < 1024:
        return (
            False,
            f"Downloaded file too small ({len(content)} bytes) to be a valid PDF",
        )

    return True, ""


def _is_valid_pdf_content(content: bytes) -> bool:
    """
    Check if the downloaded content is actually a PDF file.

    Args:
        content: The downloaded content as bytes

    Returns:
        bool: True if content appears to be a valid PDF, False otherwise
    """
    if not content:
        return False

    if not content.startswith(b"%PDF-"):
        return False

    content_lower = content[:1024].lower()
    html_indicators = [b"<html", b"<!doctype", b"<head>", b"<body>", b"recaptcha"]

    for indicator in html_indicators:
        if indicator in content_lower:
            print(
                f"Warning: Downloaded content appears to be HTML (contains '{indicator.decode()}')"
            )
            return False

    return True


async def async_retry_with_backoff(
    func: Callable[[], Any],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    retry_exceptions: tuple = (Exception,),
    operation_name: str = "operation",
) -> T:
    """
    Generic async retry function with exponential backoff.

    Args:
        func: Async function to retry (should be a callable that returns a coroutine)
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        backoff_factor: Multiplier for delay after each failure
        retry_exceptions: Tuple of exception types that should trigger a retry
        operation_name: Name of the operation for logging purposes

    Returns:
        The result of the successful function call

    Raises:
        The last exception if all retries are exhausted
    """
    if max_retries < 1:
        raise ValueError("max_retries must be at least 1")

    for attempt in range(max_retries):
        try:
            if attempt == 0:
                print(f"Starting {operation_name}")
            else:
                print(f"Retry attempt {attempt + 1}/{max_retries} for {operation_name}")

            result = await func()
            return result

        except retry_exceptions as e:
            if attempt == max_retries - 1:
                print(f"All {max_retries} attempts failed for {operation_name}")
                raise e

            delay = min(base_delay * (backoff_factor**attempt), max_delay)
            print(
                f"{operation_name} failed with {type(e).__name__}: {str(e)}, retrying in {delay:.1f} seconds..."
            )
            await asyncio.sleep(delay)


class PDFDownloadError(Exception):
    """An arXiv PDF could not be downloaded; retrying later may succeed."""


class PDFNotFoundError(PDFDownloadError):
    """arXiv has no PDF for the paper."""


@asynccontextmanager
async def temp_pdf_download(arxiv_id: str):
    """
    Temporarily download a PDF from arXiv and yield its local path.

    Raises PDFNotFoundError when arXiv has no PDF and PDFDownloadError for
    other download failures.
    """
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    timeout = aiohttp.ClientTimeout(total=120, connect=10, sock_read=60)

    async def download_pdf():
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(pdf_url) as response:
                if response.status in (404, 410):
                    raise PDFNotFoundError(f"{pdf_url} returned HTTP {response.status}")
                response.raise_for_status()
                return await response.read()

    try:
        content = await async_retry_with_backoff(
            func=download_pdf,
            max_retries=3,
            base_delay=1.0,
            backoff_factor=2.0,
            retry_exceptions=(asyncio.TimeoutError, aiohttp.ClientError),
            operation_name=f"PDF download from {pdf_url}",
        )
    except (asyncio.TimeoutError, aiohttp.ClientError) as e:
        raise PDFDownloadError(
            f"Failed to download {pdf_url}: {type(e).__name__}: {e}"
        ) from e

    if not _is_valid_pdf_content(content):
        raise PDFDownloadError(f"{pdf_url} did not return a valid PDF")

    with tempfile.TemporaryDirectory() as temp_dir:
        filepath = os.path.join(temp_dir, f"{arxiv_id.replace('/', '_')}.pdf")
        with open(filepath, "wb") as f:
            f.write(content)
        yield filepath


async def find_project_page_url(pdf_path: str) -> str:
    """
    Try to extract the first matched Project page URL
    from text using a regular expression.

    Args:
        pdf_path (str): Path to the PDF file

    Returns:
        list: List of found GitHub URLs
    """
    text = await asyncio.to_thread(extract_text_from_pdf, pdf_path, num_pages=2)
    match = await safe_regex_search_async(PROJECT_PAGE_URL_PATTERN, text, 5)
    return match.group(0) if match else ""


async def extract_first_two_pages_pymupdf_sync(input_path: str) -> str:
    """
    Synchronous part of extracting first 2 pages from a PDF file using PyMuPDF.
    Attempts to clean the input PDF first by re-saving it.
    """
    input_doc = None
    writer_doc = None
    cleaned_temp_pdf = None

    try:
        try:
            initial_doc = fitz.open(input_path)
            with tempfile.NamedTemporaryFile(
                delete=False, suffix="_cleaned.pdf"
            ) as temp_clean_file:
                cleaned_pdf_path = temp_clean_file.name
            initial_doc.save(cleaned_pdf_path, garbage=4, deflate=True)
            initial_doc.close()
            print(f"Attempted to clean PDF, saved to: {cleaned_pdf_path}")
            input_path_to_use = cleaned_pdf_path
            cleaned_temp_pdf = cleaned_pdf_path
        except Exception as clean_e:
            print(
                f"Warning: Failed to clean PDF, proceeding with original. Error: {clean_e}"
            )
            input_path_to_use = input_path

        input_doc = fitz.open(input_path_to_use)

        writer_doc = fitz.open()

        if len(input_doc) == 0:
            if input_doc:
                input_doc.close()
            if writer_doc:
                writer_doc.close()
            raise ValueError("Input PDF has no pages.")

        num_pages_to_extract = min(len(input_doc), 2)

        writer_doc.insert_pdf(input_doc, from_page=0, to_page=num_pages_to_extract - 1)

        with tempfile.NamedTemporaryFile(
            delete=False, suffix="_extract.pdf"
        ) as temp_extract_file:
            writer_doc.save(temp_extract_file.name, garbage=4, deflate=True)
            output_temp_file_path = temp_extract_file.name

        input_doc.close()
        writer_doc.close()

        print(f"Extracted first {num_pages_to_extract} pages using PyMuPDF.")
        return output_temp_file_path

    except Exception as e:
        print(f"Error using PyMuPDF to extract pages: {e}")
        try:
            if input_doc:
                input_doc.close()
            if writer_doc:
                writer_doc.close()
        except Exception as cleanup_e:
            print(f"Error during exception cleanup: {cleanup_e}")
        raise

    finally:
        if cleaned_temp_pdf and os.path.exists(cleaned_temp_pdf):
            try:
                os.unlink(cleaned_temp_pdf)
                print(f"Cleaned up intermediate file: {cleaned_temp_pdf}")
            except Exception as final_cleanup_e:
                print(
                    f"Error cleaning up intermediate file {cleaned_temp_pdf}: {final_cleanup_e}"
                )


async def extract_first_two_pages_pymupdf(input_path: str) -> str:
    """
    Function to extract the first 2 pages from a PDF file using PyMuPDF.
    Attempts to clean the input PDF first by re-saving it.
    This version runs synchronous file operations in a separate thread.
    """
    return await extract_first_two_pages_pymupdf_sync(input_path)


if __name__ == "__main__":

    async def main():
        async with temp_pdf_download(arxiv_id="2509.22622") as pdf_path:
            print("Successfully downloaded PDF to: ", pdf_path)

    try:
        asyncio.run(main())
    except Exception as e:
        print(e)
    print("Done")
