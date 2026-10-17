"""Triage the user's X bookmarks into Papers with Code paper actions.

Reads the newest bookmarks with the OAuth2 user token, finds the arXiv papers
each post (or the post it quotes, or the author's own replies) links to, and
checks every paper against the public Papers with Code API. Writes a JSON
report and prints a short table; it never writes to Papers with Code.

Usage (from the repository root):
  uv run --env-file backend/keys.env python \
      .agents/skills/process-x-bookmarks/scripts/triage_bookmarks.py \
      --max 200 --out <scratchpad>/x_bookmarks.json
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

from backend.services.x_thread_discovery_service import (
    author_matches,
    post_text_and_urls,
)

X_API = "https://api.x.com/2"
PWC_API = "https://paperswithcode.co/api/v1"
UA = {"User-Agent": "curl/8.5.0"}
ARXIV = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf|html)/|huggingface\.co/papers/|hf\.co/papers/|"
    r"alphaxiv\.org/(?:abs|overview)/|paperswithcode\.co/paper/|arxiv[: ])"
    r"(\d{4}\.\d{4,5})",
    re.IGNORECASE,
)
SKIP_HOSTS = ("x.com", "twitter.com", "t.co", "pic.x.com")
TWEET_FIELDS = (
    "tweet.fields=created_at,conversation_id,entities,note_tweet,"
    "referenced_tweets,author_id,public_metrics"
    "&expansions=author_id,referenced_tweets.id,referenced_tweets.id.author_id"
    "&user.fields=name,username,verified_type"
)


def get(url, headers):
    request = urllib.request.Request(url, headers={**UA, **headers})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def x_get(path):
    token = os.environ["X_USER_ACCESS_TOKEN"]
    try:
        return get(f"{X_API}{path}", {"Authorization": f"Bearer {token}"})
    except urllib.error.HTTPError as error:
        if error.code == 401:
            sys.exit(
                "X token expired: run scripts/x_user_token.py --refresh "
                "(or without --refresh to re-authorize)."
            )
        raise


def pwc_paper(arxiv_id):
    try:
        return get(f"{PWC_API}/papers/{arxiv_id}?include_resources=true", {})
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def fetch_bookmarks(limit):
    me = x_get("/users/me")["data"]
    posts, users, tweets, token = [], {}, {}, None
    while len(posts) < limit:
        page = f"&pagination_token={token}" if token else ""
        data = x_get(
            f"/users/{me['id']}/bookmarks?max_results=100&{TWEET_FIELDS}{page}"
        )
        posts += data.get("data", [])
        includes = data.get("includes", {})
        users.update({u["id"]: u for u in includes.get("users", [])})
        tweets.update({t["id"]: t for t in includes.get("tweets", [])})
        token = data.get("meta", {}).get("next_token")
        if not token:
            break
    return me["username"], posts[:limit], users, tweets


def self_replies(post, user):
    """Return the author's own posts in the thread (they often hold the links)."""
    created = datetime.fromisoformat(post["created_at"].replace("Z", "+00:00"))
    # X rejects an end_time later than a few seconds ago.
    end = min(created + timedelta(days=2), datetime.now(UTC) - timedelta(minutes=1))
    if end <= created:
        return []
    window = urllib.parse.urlencode(
        {
            "start_time": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_time": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "max_results": 100,
        }
    )
    data = x_get(f"/users/{user['id']}/tweets?{window}&{TWEET_FIELDS}")
    root = post.get("conversation_id", post["id"])
    return [t for t in data.get("data", []) if t.get("conversation_id") == root]


def links(posts):
    text, urls = "", []
    for post in posts:
        post_text, post_urls = post_text_and_urls(post)
        text += "\n" + post_text
        urls += post_urls
    arxiv_ids = list(dict.fromkeys(ARXIV.findall(text + " " + " ".join(urls))))
    other = [
        u
        for u in dict.fromkeys(urls)
        if not ARXIV.search(u)
        and urllib.parse.urlsplit(u).netloc.removeprefix("www.") not in SKIP_HOSTS
    ]
    return arxiv_ids, other


def post_url(post, users):
    user = users.get(post.get("author_id"), {})
    return f"https://x.com/{user.get('username', 'i')}/status/{post['id']}"


def paper_status(arxiv_id, thread_users):
    paper = pwc_paper(arxiv_id)
    if paper is None:
        return {"arxiv_id": arxiv_id, "indexed": False}
    linked = [t["url"] for t in paper.get("x_threads") or []]
    authors = paper.get("authors") or []
    matches = {
        handle: author_matches(user.get("name", ""), authors, handle)
        for handle, user in thread_users.items()
    }
    return {
        "arxiv_id": arxiv_id,
        "indexed": True,
        "paper_id": int(paper["id"]),
        "title": paper["title"],
        "linked_threads": linked,
        "author_matches": {h: a for h, a in matches.items() if a},
        "gaps": [
            name
            for name, missing in (
                ("code", not paper.get("repositories")),
                ("project_page", not paper.get("project_pages")),
                ("tasks", not paper.get("tasks")),
                ("methods", not paper.get("methods")),
                ("thumbnail", not paper.get("thumbnail_url")),
            )
            if missing
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=200, help="newest N bookmarks")
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--no-replies",
        action="store_true",
        help="skip the self-reply lookup for posts without an arXiv link",
    )
    args = parser.parse_args()

    handle, bookmarks, users, tweets = fetch_bookmarks(args.max)
    report = []
    for post in bookmarks:
        # A quote or retweet of an announcement: the quoted post is the thread.
        thread = [post] + [
            tweets[ref["id"]]
            for ref in post.get("referenced_tweets") or []
            if ref["type"] in ("quoted", "retweeted") and ref["id"] in tweets
        ]
        arxiv_ids, other = links(thread)
        replies_checked = False
        if not arxiv_ids and not args.no_replies:
            root = thread[-1]
            replies = self_replies(root, users[root["author_id"]])
            replies_checked = True
            arxiv_ids, more = links(thread + replies)
            other = list(dict.fromkeys(other + more))
        thread_users = {
            users[t["author_id"]]["username"]: users[t["author_id"]]
            for t in thread
            if t.get("author_id") in users
        }
        report.append(
            {
                "bookmark": post_url(post, users),
                "thread_candidates": [post_url(t, users) for t in thread],
                "conversation_root": post.get("conversation_id") == post["id"],
                "posted_at": post.get("created_at"),
                "text": post_text_and_urls(thread[-1])[0][:400],
                "arxiv_ids": arxiv_ids,
                "other_urls": other,
                "replies_checked": replies_checked,
                "papers": [paper_status(a, thread_users) for a in arxiv_ids],
            }
        )

    with open(args.out, "w") as out:
        json.dump({"account": handle, "bookmarks": report}, out, indent=2)

    paper_rows = [r for r in report if r["arxiv_ids"]]
    print(f"@{handle}: {len(report)} bookmarks, {len(paper_rows)} with arXiv links")
    for row in report:
        for paper in row["papers"]:
            if not paper["indexed"]:
                state = "MISSING"
            elif any(
                url.split("/")[-1]
                in {c.split("/")[-1] for c in row["thread_candidates"]}
                for url in paper["linked_threads"]
            ):
                state = "linked"
            else:
                state = "UNLINKED"
            gaps = ",".join(paper.get("gaps", [])) or "-"
            print(f"{state:8} {paper['arxiv_id']:11} gaps={gaps:28} {row['bookmark']}")
    others = [r for r in report if not r["arxiv_ids"] and r["other_urls"]]
    print(
        f"{len(others)} bookmarks link non-arXiv resources (review for external papers)"
    )


if __name__ == "__main__":
    main()
