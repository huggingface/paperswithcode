#!/usr/bin/env python3
"""
Canonicalize GitHub repository rows whose URL ends in a clone-style ``.git``.

GitHub serves ``owner/name.git`` only to git, so the stars refresh got 404s
and those rows stayed at zero stars. For each such row this script:
1. Merges it into an existing canonical ``owner/name`` row when one exists,
   moving paper, framework, and task links (paper links keep ``is_official``)
2. Otherwise rewrites its URL, owner, and name in place
3. Deletes its zero-star snapshots, which are 404 artifacts, and clears
   ``num_stars_updated_at`` so the next stars refresh picks it up first

Dry run by default; pass ``--apply`` to write.
"""

from __future__ import annotations

import argparse

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.utils.github_utils import normalize_github_url, parse_github_url


def find_canonical_row(session, repository_id: int, owner: str, name: str):
    return session.execute(
        text(
            """
            SELECT id FROM repositories
            WHERE id != :repository_id
              AND (
                lower(url) = :url
                OR (lower(owner) = :owner AND lower(name) = :name)
              )
            ORDER BY (lower(url) = :url) DESC, num_stars DESC, id
            LIMIT 1
            """
        ),
        {
            "repository_id": repository_id,
            "url": f"https://github.com/{owner.lower()}/{name.lower()}",
            "owner": owner.lower(),
            "name": name.lower(),
        },
    ).scalar()


def merge_into(session, duplicate_id: int, keeper_id: int) -> None:
    ids = {"dup": duplicate_id, "keep": keeper_id}
    session.execute(
        text(
            """
            UPDATE paper_repositories SET is_official = TRUE
            WHERE repository_id = :keep AND paper_id IN (
                SELECT paper_id FROM paper_repositories
                WHERE repository_id = :dup AND is_official
            )
            """
        ),
        ids,
    )
    for table in ("paper_repositories", "task_recommended_frameworks"):
        owner_column = "paper_id" if table == "paper_repositories" else "task_id"
        session.execute(
            text(
                f"""
                UPDATE {table} SET repository_id = :keep
                WHERE repository_id = :dup AND {owner_column} NOT IN (
                    SELECT {owner_column} FROM {table} WHERE repository_id = :keep
                )
                """
            ),
            ids,
        )
        session.execute(text(f"DELETE FROM {table} WHERE repository_id = :dup"), ids)
    session.execute(
        text("UPDATE frameworks SET repository_id = :keep WHERE repository_id = :dup"),
        ids,
    )
    session.execute(
        text(
            """
            UPDATE repository_star_history SET repository_id = :keep
            WHERE repository_id = :dup AND num_stars > 0 AND snapshot_at NOT IN (
                SELECT snapshot_at FROM repository_star_history
                WHERE repository_id = :keep
            )
            """
        ),
        ids,
    )
    session.execute(
        text(
            """
            UPDATE repositories SET num_stars = (
                SELECT MAX(num_stars) FROM repositories WHERE id IN (:dup, :keep)
            )
            WHERE id = :keep
            """
        ),
        ids,
    )
    session.execute(
        text("DELETE FROM repository_star_history WHERE repository_id = :dup"), ids
    )
    session.execute(text("DELETE FROM repositories WHERE id = :dup"), ids)


def strip_dotgit_repositories(session, apply: bool = False) -> dict[str, int]:
    rows = session.execute(
        text(
            """
            SELECT id, url FROM repositories
            WHERE lower(url) LIKE '%github.com/%.git'
            ORDER BY id
            """
        )
    ).fetchall()
    stats = {"rows": len(rows), "merged": 0, "renamed": 0, "skipped": 0}

    for repository_id, url in rows:
        canonical_url = normalize_github_url(url)
        if not canonical_url:
            stats["skipped"] += 1
            continue
        owner, name = parse_github_url(canonical_url)
        keeper_id = find_canonical_row(session, repository_id, owner, name)
        action = (
            f"merge into {keeper_id}" if keeper_id else f"rename to {canonical_url}"
        )
        print(f"  {repository_id} {url} -> {action}")
        if keeper_id:
            stats["merged"] += 1
            if apply:
                merge_into(session, repository_id, keeper_id)
        else:
            stats["renamed"] += 1
            if apply:
                session.execute(
                    text(
                        """
                        UPDATE repositories
                        SET url = :url, owner = :owner, name = :name,
                            num_stars_updated_at = NULL
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": repository_id,
                        "url": canonical_url,
                        "owner": owner,
                        "name": name,
                    },
                )
                session.execute(
                    text(
                        """
                        DELETE FROM repository_star_history
                        WHERE repository_id = :id AND num_stars = 0
                        """
                    ),
                    {"id": repository_id},
                )

    if apply:
        session.commit()
    else:
        session.rollback()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--apply", action="store_true", help="write the changes")
    args = parser.parse_args()

    session = db_manager.session_local()
    try:
        stats = strip_dotgit_repositories(session, apply=args.apply)
    finally:
        session.close()
    mode = "Applied" if args.apply else "Dry run"
    print(
        f"{mode}: {stats['rows']} .git rows, {stats['merged']} merged, "
        f"{stats['renamed']} renamed, {stats['skipped']} skipped"
    )


if __name__ == "__main__":
    main()
