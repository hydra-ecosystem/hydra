#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

"""Refresh live GitHub metadata used for Hydra Landscape maintenance evidence."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
WORK_ROOT = REPO_ROOT / "temp" / "hydra-dependents"
DEFAULT_INPUT = WORK_ROOT / "hydra-project-analysis-v1.ndjson"
DEFAULT_OUT = WORK_ROOT / "hydra-landscape-repository-metadata-v1.ndjson"
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
UTC = timezone.utc


def read_rows(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        rows = value if isinstance(value, list) else [value]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{path}: expected JSON objects")
    return rows


def read_repositories(path: Path) -> list[str]:
    repositories = set()
    for index, row in enumerate(read_rows(path)):
        if row.get("status") != "ok" and row.get("decision") != "include":
            continue
        repo = row.get("repo")
        if not isinstance(repo, str) or not REPOSITORY_RE.fullmatch(repo):
            raise ValueError(f"{path}: row {index} has invalid repository {repo!r}")
        repositories.add(repo)
    return sorted(repositories, key=str.lower)


def build_query(repositories: list[str]) -> str:
    fields = []
    for index, repo in enumerate(repositories):
        owner, name = repo.split("/", 1)
        fields.append(
            f"""
            r{index}: repository(
              owner: {json.dumps(owner)}, name: {json.dumps(name)}
            ) {{
              nameWithOwner
              url
              homepageUrl
              description
              isFork
              isArchived
              stargazerCount
              pushedAt
              updatedAt
              createdAt
              defaultBranchRef {{
                name
                target {{
                  ... on Commit {{
                    oid
                    committedDate
                  }}
                }}
              }}
              latestRelease {{
                tagName
                publishedAt
                url
              }}
              parent {{
                nameWithOwner
              }}
            }}
            """
        )
    return "query {\n" + "\n".join(fields) + "\nrateLimit { cost remaining resetAt }\n}"


def normalize_homepage(value: Any) -> str | None:
    """Return the repository homepage as recorded on GitHub, or None.

    GitHub reports an unset homepage as either null or an empty string, and
    stores whatever the project typed, so the value is kept verbatim apart from
    surrounding whitespace. Promoting it into a public listing is a maintainer
    decision, and build_public_landscape.py validates it there.
    """
    if not isinstance(value, str):
        return None
    return value.strip() or None


def parse_response(
    repositories: list[str],
    payload: dict[str, Any],
    *,
    fetched_at: str,
) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError(f"GitHub GraphQL response has no data: {payload}")
    rows: list[dict[str, Any]] = []
    for index, requested_repo in enumerate(repositories):
        repository = data.get(f"r{index}")
        if not isinstance(repository, dict):
            rows.append(
                {
                    "repo": requested_repo,
                    "status": "error",
                    "fetched_at": fetched_at,
                    "error": "repository was not returned by GitHub",
                }
            )
            continue
        default_branch_ref = repository.get("defaultBranchRef") or {}
        target = default_branch_ref.get("target") or {}
        latest_release = repository.get("latestRelease")
        canonical_repo = repository["nameWithOwner"]
        rows.append(
            {
                "repo": requested_repo,
                "status": "ok",
                "fetched_at": fetched_at,
                "canonical_repo": canonical_repo,
                "url": repository["url"],
                "homepage": normalize_homepage(repository.get("homepageUrl")),
                "description": repository.get("description"),
                "fork": repository["isFork"],
                "parent": (repository.get("parent") or {}).get("nameWithOwner"),
                "archived": repository["isArchived"],
                "stars": repository["stargazerCount"],
                "created_at": repository.get("createdAt"),
                "updated_at": repository.get("updatedAt"),
                "pushed_at": repository.get("pushedAt"),
                "default_branch": {
                    "name": default_branch_ref.get("name"),
                    "head_oid": target.get("oid"),
                    "committed_at": target.get("committedDate"),
                    "commit_url": (
                        f"https://github.com/{canonical_repo}/commit/{target['oid']}"
                        if target.get("oid")
                        else None
                    ),
                },
                "latest_release": (
                    {
                        "tag": latest_release["tagName"],
                        "published_at": latest_release["publishedAt"],
                        "url": latest_release["url"],
                    }
                    if latest_release
                    else None
                ),
            }
        )
    return rows


def fetch_batch(
    repositories: list[str],
    *,
    gh_bin: str,
    timeout: float,
    fetched_at: str,
) -> list[dict[str, Any]]:
    completed = subprocess.run(
        [gh_bin, "api", "graphql", "-f", f"query={build_query(repositories)}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"GitHub metadata refresh failed: {detail}")
    return parse_response(
        repositories,
        json.loads(completed.stdout),
        fetched_at=fetched_at,
    )


def write_ndjson(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    temporary.replace(path)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--batch-size", type=int, default=40)
    parser.add_argument("--gh-bin", default="gh")
    parser.add_argument("--timeout", type=float, default=60)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if args.batch_size < 1 or args.batch_size > 50:
        raise SystemExit("--batch-size must be between 1 and 50")
    if args.timeout <= 0:
        raise SystemExit("--timeout must be positive")
    if shutil.which(args.gh_bin) is None:
        raise SystemExit(f"GitHub CLI not found: {args.gh_bin}")

    repositories = read_repositories(args.input)
    fetched_at = datetime.now(UTC).isoformat()
    rows = []
    total_batches = (len(repositories) + args.batch_size - 1) // args.batch_size
    for batch_number, start in enumerate(
        range(0, len(repositories), args.batch_size), 1
    ):
        batch = repositories[start : start + args.batch_size]
        batch_rows = fetch_batch(
            batch,
            gh_bin=args.gh_bin,
            timeout=args.timeout,
            fetched_at=fetched_at,
        )
        rows.extend(batch_rows)
        errors = sum(row["status"] != "ok" for row in batch_rows)
        print(
            f"{batch_number}/{total_batches} fetched={len(batch_rows)} errors={errors}"
        )
    write_ndjson(args.out, rows)
    errors = sum(row["status"] != "ok" for row in rows)
    print(f"repositories={len(rows)} errors={errors} output={args.out}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
