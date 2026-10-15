import pytest

from backend.utils.github_utils import normalize_github_url, parse_github_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/wuzimeng/comp.git", ("wuzimeng", "comp")),
        ("https://github.com/AIRI-Institute/CAMAR.GIT", ("AIRI-Institute", "CAMAR")),
        ("https://github.com/owner/repo.git/", ("owner", "repo")),
        ("https://github.com/owner/name.github.io", ("owner", "name.github.io")),
        ("https://github.com/owner/.git", (None, None)),
    ],
)
def test_parse_github_url_strips_clone_suffix(url, expected):
    assert parse_github_url(url) == expected


def test_normalize_github_url_drops_clone_suffix():
    assert (
        normalize_github_url("github.com/YU-deep/MACT.git")
        == "https://github.com/yu-deep/mact"
    )
