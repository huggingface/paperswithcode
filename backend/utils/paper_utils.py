from typing import Optional
import re
import aiohttp
import asyncio
from bs4 import BeautifulSoup

from huggingface_hub import paper_info
from huggingface_hub.utils import build_hf_headers

from backend.utils.hf_utils import get_user_organizations


GITHUB_URL_PATTERN = r"\bhttps?:\/\/github\.com[^\s]*\b"


async def get_github_and_project_page_urls_from_daily_papers(
    arxiv_id: str,
) -> tuple[str, str]:
    """
    Get the Github URL and project page URLs from the Hugging Face REST API.
    """
    github_url, project_page_url = "", ""
    if arxiv_id != "":
        try:
            headers = build_hf_headers(token=False, user_agent={"is_ci": "true"})
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(
                    f"https://huggingface.co/api/papers/{arxiv_id}",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                    github_url = data.get("githubRepo", "")
                    project_page_url = data.get("projectPage", "")

        except Exception as e:
            print(f"Error getting Github URL from daily papers API: {e}")
            pass

    return github_url, project_page_url


async def find_github_url(arxiv_id: str, abstract: Optional[str] = None) -> str:
    """
    Try to extract the first matched Github URL
    from text using a regular expression.

    Args:
        pdf_path (str): Path to the PDF file

    Returns:
        list: List of found GitHub URLs
    """
    if abstract is None:
        abstract = await get_abstract(arxiv_id=arxiv_id)
    match = re.search(GITHUB_URL_PATTERN, abstract)
    return match.group(0) if match else ""


async def _fetch_arxiv_page(arxiv_id: str) -> BeautifulSoup | None:
    """
    Shared function to fetch and parse an ArXiv page.

    Args:
        arxiv_id: The ArXiv identifier (e.g., "2505.17225" or "cs/0001001v1").

    Returns:
        BeautifulSoup object of the parsed HTML, or None if fetching fails.
    """
    if not arxiv_id:
        print("Error: ArXiv ID cannot be empty.")
        return None

    url = f"https://arxiv.org/abs/{arxiv_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    async def _do_fetch():
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=10) as response:
                response.raise_for_status()
                return await response.text()

    try:
        # Shield from cancellation to prevent cancel scope propagation from MCP cleanup
        html_content = await asyncio.shield(_do_fetch())
    except aiohttp.ClientError as e:
        print(f"Error fetching ArXiv page {url}: {e}")
        return None
    except asyncio.TimeoutError:
        print(f"Timeout error fetching ArXiv page {url}")
        return None
    except asyncio.CancelledError:
        # If still cancelled despite shield, return None gracefully
        print(f"Request cancelled while fetching ArXiv page {url}")
        return None

    return BeautifulSoup(html_content, "html.parser")


async def get_abstract_arxiv(arxiv_id: str) -> str | None:
    """
    Fetches the Arxiv page for a given ID and extracts the abstract asynchronously.

    Args:
        arxiv_id: The ArXiv identifier (e.g., "2505.17225" or "cs/0001001v1").

    Returns:
        The abstract text as a string, or None if fetching fails or abstract not found.
    """
    soup = await _fetch_arxiv_page(arxiv_id)
    if soup is None:
        return None

    # Primary method: Look for the blockquote containing the abstract
    abstract_blockquote = soup.find("blockquote", class_="abstract mathjax")
    if abstract_blockquote:
        full_text = abstract_blockquote.get_text(separator=" ", strip=True)
        prefix_to_remove = "Abstract:"
        if full_text.startswith(prefix_to_remove):
            abstract_text = full_text[len(prefix_to_remove) :].strip()
            return abstract_text
        else:
            # If the prefix isn't there for some reason, return the whole text of the blockquote
            # This might happen if the structure changes slightly or if there's no <span>
            return full_text  # Or return None if strict prefix matching is required

    # Fallback methods: Check meta tags
    meta_tags_to_check = [
        {"name": "citation_abstract"},
        {"property": "og:description"},
        {"name": "description"},  # This one might contain "Abstract page for..."
    ]

    for tag_attrs in meta_tags_to_check:
        meta_tag = soup.find("meta", attrs=tag_attrs)
        if meta_tag and meta_tag.get("content"):
            content = meta_tag.get("content").strip()
            # The 'description' meta tag sometimes has a prefix like "Abstract page for arXiv paper XXXXX: "
            if (
                tag_attrs.get("name") == "description"
                and "Abstract page for arXiv paper" in content
            ):
                # Try to remove the generic prefix if it's the 'description' tag
                parts = content.split(":", 1)
                if len(parts) > 1:
                    abstract_candidate = parts[1].strip()
                    # A simple heuristic: if it's long enough and doesn't seem like just a title, use it.
                    # This is to avoid picking up just "Reasoning Model is Stubborn..." from the generic description.
                    # The actual abstract from citation_abstract or og:description is usually much longer.
                    if len(abstract_candidate) > 100:  # Arbitrary length check
                        return abstract_candidate
                    # else, continue to next meta tag
            else:
                # For citation_abstract and og:description, the content is usually the direct abstract
                return content

    print(f"Abstract not found in expected locations for ArXiv ID: {arxiv_id}")
    return None


async def get_abstract_hf_hub(arxiv_id: str) -> str:
    """
    Get the abstract of a paper using the Hugging Face Hub API.
    """
    try:
        # Shield from cancellation to prevent cancel scope propagation
        paper_details = await asyncio.shield(asyncio.to_thread(paper_info, id=arxiv_id))
        abstract = paper_details.summary
        return abstract
    except asyncio.CancelledError:
        print(f"Request cancelled while fetching HF Hub abstract for {arxiv_id}")
        return "No abstract was found."


async def get_abstract(arxiv_id: str) -> str:
    """
    Get the abstract of a paper using the HF REST API and ArXiv API.
    """

    try:
        abstract = await get_abstract_hf_hub(arxiv_id=arxiv_id)
        if abstract is None:
            abstract = await get_abstract_arxiv(arxiv_id=arxiv_id)
    except Exception as e:
        print(f"Error getting abstract: {e}")
        abstract = "No abstract was found."

    return abstract


async def get_title_hf_hub(arxiv_id: str) -> str:
    """
    Get the title of a paper using the Hugging Face Hub API.
    """
    try:
        # Shield from cancellation to prevent cancel scope propagation
        paper_details = await asyncio.shield(asyncio.to_thread(paper_info, id=arxiv_id))
        title = paper_details.title
        return title
    except asyncio.CancelledError:
        print(f"Request cancelled while fetching HF Hub info for {arxiv_id}")
        return "No title was found."  # Return fallback value instead of crashing


async def get_title_arxiv(arxiv_id: str) -> str | None:
    """
    Fetches the Arxiv page for a given ID and extracts the paper title.

    Args:
        arxiv_id: The ArXiv identifier (e.g., "2505.17225" or "cs/0001001v1").

    Returns:
        The paper title as a string, or None if fetching fails or title not found.
    """
    soup = await _fetch_arxiv_page(arxiv_id)
    if soup is None:
        return None

    # Method 1: Try the <h1> tag with class "title"
    title_h1 = soup.find("h1", class_="title mathjax")
    if title_h1:
        # The <h1> often contains a <span class="descriptor">Title:</span>
        # We want the text after that span.
        title_span = title_h1.find("span", class_="descriptor")
        if title_span and title_span.get_text(strip=True).lower() == "title:":
            # Get all text nodes following the span directly within h1
            # or just get the full text and remove the prefix
            full_h1_text = title_h1.get_text(separator=" ", strip=True)
            prefix_to_remove = "Title:"
            if full_h1_text.lower().startswith(prefix_to_remove.lower()):
                title_text = full_h1_text[len(prefix_to_remove) :].strip()
                if title_text:  # Ensure it's not empty after stripping
                    return title_text
        else:
            # If no "Title:" descriptor span, take the whole h1 text
            # This might happen if the structure changes
            title_text = title_h1.get_text(strip=True)
            if title_text:
                return title_text

    # Method 2: Try meta tags (often more reliable for clean title)
    meta_tags_to_check = [
        {"name": "citation_title"},  # Usually the most direct and clean
        {"property": "og:title"},  # OpenGraph title
        {"name": "twitter:title"},  # Twitter card title
    ]
    for tag_attrs in meta_tags_to_check:
        meta_tag = soup.find("meta", attrs=tag_attrs)
        if meta_tag and meta_tag.get("content"):
            title_text = meta_tag.get("content").strip()
            # Sometimes og:title or twitter:title might have extra bits for very long titles (e.g., "...")
            # citation_title is usually precise.
            if title_text:
                return title_text

    # Method 3: Try the <title> tag in the <head>
    # This usually looks like "[arxiv_id] Actual Title"
    head_title_tag = soup.find("title")
    if head_title_tag and head_title_tag.string:
        full_title_text = head_title_tag.string.strip()
        # Try to remove the "[arxiv_id]" part
        # A more robust way using regex to remove anything in brackets at the start
        cleaned_title = re.sub(r"^\[[^\]]+\]\s*", "", full_title_text).strip()
        if cleaned_title:
            return cleaned_title

    print(f"Title not found in expected locations for ArXiv ID: {arxiv_id}")
    return None


async def get_title(arxiv_id: str) -> str:
    """
    Get the title of a paper using the HF REST API.
    """

    try:
        title = await get_title_arxiv(arxiv_id=arxiv_id)
        if title is None:
            title = await get_title_hf_hub(arxiv_id=arxiv_id)
    except Exception as e:
        print(f"Error getting title from HF Hub: {e}")
        title = "No title was found."

    return title


async def get_comments(arxiv_id: str) -> str:
    """
    Get the comments for a paper using the Hugging Face API.
    """
    comments_string = "No comments were found"
    if arxiv_id != "":
        comments_string = f"Comments at huggingface.co/papers/{arxiv_id}:"
        try:
            headers = build_hf_headers(token=False, user_agent={"is_ci": "true"})
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(
                    f"https://huggingface.co/api/papers/{arxiv_id}?field=comments",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

            comments = data.get("comments", [])
            if comments:
                current_comments_string = ""
                for idx, comment in enumerate(comments):
                    current_comments_string += f"### Comment {idx + 1} ###\n"
                    author = comment.get("author", {})
                    author_fullname = author.get("fullname", "N/A")
                    author_username = author.get("name", "N/A")
                    author_organizations = await get_user_organizations(
                        username=author_username
                    )
                    comment_data = (
                        comment.get("data", {}).get("latest", {}).get("raw", "")
                    )
                    current_comments_string += f"Author full name: {author_fullname}\n"
                    current_comments_string += (
                        f"Author Hugging Face username: {author_username}\n"
                    )
                    current_comments_string += (
                        f"Author organizations: {author_organizations}\n"
                    )
                    current_comments_string += f"Comment: {comment_data}\n\n"
                if current_comments_string:
                    comments_string = current_comments_string
                else:
                    comments_string += "\n\nNo valid comment content found."
            else:
                comments_string += "\n\nNo comments were found in API response."

        except Exception:
            comments_string += "\n\nNo comments were found (due to error)."

    return comments_string


async def get_authors(arxiv_id: str) -> str:
    """
    Get the authors of a paper using the Hugging Face API along with metadata like their Hugging Face username, full name, and organizations they are a part of.
    """
    authors_string = "No authors were found"
    if arxiv_id != "":
        authors_string = f"Authors at huggingface.co/papers/{arxiv_id}:"

        async def _fetch_authors():
            headers = build_hf_headers(token=False, user_agent={"is_ci": "true"})
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(
                    f"https://huggingface.co/api/papers/{arxiv_id}",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    response.raise_for_status()
                    return await response.json()

        try:
            # Shield from cancellation to prevent cancel scope propagation
            data = await asyncio.shield(_fetch_authors())

            authors = data.get("authors", [])
            if authors:
                current_authors_string = ""
                for author in authors:
                    author_name = author.get("name")
                    current_authors_string += f"Author name: {author_name}\n"
                    # try to get the Hugging Face username
                    if author.get("user"):
                        author_hf_username = author.get("user").get("user")
                        author_full_name = author.get("user").get("fullname")
                        author_organizations = await get_user_organizations(
                            username=author_hf_username
                        )
                        current_authors_string += (
                            f"Author Hugging Face user name: {author_hf_username}\n"
                        )
                        current_authors_string += (
                            f"Author Hugging Face full name: {author_full_name}\n"
                        )
                        current_authors_string += f"Author Hugging Face organizations: {author_organizations}\n"
                    else:
                        current_authors_string += (
                            "Author Hugging Face user name: not found\n"
                        )
                    current_authors_string += "--------------------------------\n"
                if current_authors_string:
                    authors_string = current_authors_string
                else:
                    authors_string += "\n\nNo valid author content found."
            else:
                authors_string += "\n\nNo authors were found in API response."

        except asyncio.CancelledError:
            print(f"Request cancelled while fetching authors for {arxiv_id}")
            authors_string += "\n\nNo authors were found (request cancelled)."
        except Exception:
            authors_string += "\n\nNo authors were found (due to error)."

    return authors_string
