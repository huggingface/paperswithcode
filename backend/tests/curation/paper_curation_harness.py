"""Paper text and curation context fixtures shared by paper-curation tests."""

from __future__ import annotations


PAPER_TEXT = (
    b"# A complete research paper\n"
    + b"We evaluate the proposed method on held-out tasks and compare the results. "
    * 20
)


class _HeadResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _context(*, project_page: bool = True) -> dict:
    return {
        "paper": {
            "id": 42,
            "arxiv_id": "2608.00042",
            "abstract": "A paper without inline links.",
            "repositories": [
                {
                    "url": "https://github.com/example/project",
                    "is_official": True,
                    "source": "hf_api",
                }
            ],
            "project_pages": (
                [
                    {
                        "url": "https://example.github.io/project",
                        "is_official": True,
                        "source": "hf_api",
                    }
                ]
                if project_page
                else []
            ),
        }
    }
