#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

"""Generate public Hydra Landscape data from maintainer decisions."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent

DEFAULT_DECISIONS = ROOT / "data" / "decisions.json"
DEFAULT_OUT = REPO_ROOT / "website/src/data/landscape.json"

ALLOWED_DECISIONS = {"exclude", "include"}
ALLOWED_GROUPS = {"good_hydra_usage", "powered_by_hydra"}
ALLOWED_KINDS = {
    "application",
    "framework",
    "hydra_developer_tool",
    "learning_resource",
    "library_tool",
    "ml_experimentation_platform",
    "plugin_integration",
    "template_starter",
}
ALLOWED_RELATIONSHIPS = {"extends", "integrates", "teaches"}
LISTING_FIELDS = {
    "description",
    "kind",
    "name",
    "relationships",
    "tags",
    "type",
    "url",
}
OPTIONAL_LISTING_FIELDS = {"homepage"}
REPOSITORY_RE = re.compile(r"^[\w.-]+/[\w.-]+$")
TAG_RE = re.compile(r"^[a-z][a-z0-9_]*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def read_decisions(path: Path) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{path}: expected an array of objects")
    return rows


def require_string(value: Any, *, field: str, repo: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{repo}: {field} must be a non-empty string")
    return value.strip()


def require_sorted_strings(
    value: Any,
    *,
    field: str,
    repo: str,
    allowed: set[str] | None = None,
    pattern: re.Pattern[str] | None = None,
) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{repo}: {field} must be a list of strings")
    if value != sorted(set(value)):
        raise ValueError(f"{repo}: {field} must be sorted and unique")
    if allowed is not None:
        invalid = set(value) - allowed
        if invalid:
            raise ValueError(f"{repo}: unsupported {field} {sorted(invalid)!r}")
    if pattern is not None and any(pattern.fullmatch(item) is None for item in value):
        raise ValueError(f"{repo}: {field} contains an invalid value")
    return value


def build_project(decision: dict[str, Any]) -> dict[str, Any]:
    repo = require_string(decision.get("repo"), field="repo", repo="decision")
    if REPOSITORY_RE.fullmatch(repo) is None:
        raise ValueError(f"{repo}: invalid repository")

    group = decision.get("group")
    if group not in ALLOWED_GROUPS:
        raise ValueError(f"{repo}: unsupported curation group {group!r}")

    feature_candidate = decision.get("feature_candidate")
    if not isinstance(feature_candidate, bool):
        raise ValueError(f"{repo}: feature_candidate must be a boolean")
    if feature_candidate and group != "good_hydra_usage":
        raise ValueError(f"{repo}: featured projects must have good Hydra usage")

    reviewed_at = require_string(
        decision.get("decided_at"), field="decided_at", repo=repo
    )
    if DATE_RE.fullmatch(reviewed_at) is None:
        raise ValueError(f"{repo}: decided_at must use YYYY-MM-DD")

    listing = decision.get("listing")
    if not isinstance(listing, dict):
        raise ValueError(f"{repo}: included decisions must contain a listing")
    unknown = set(listing) - LISTING_FIELDS - OPTIONAL_LISTING_FIELDS
    missing = LISTING_FIELDS - set(listing)
    if unknown or missing:
        raise ValueError(
            f"{repo}: listing fields must be {sorted(LISTING_FIELDS)!r} "
            f"with optional {sorted(OPTIONAL_LISTING_FIELDS)!r}"
        )

    kind = require_string(listing.get("kind"), field="listing.kind", repo=repo)
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"{repo}: unsupported project kind {kind!r}")

    tags = require_sorted_strings(
        listing.get("tags"), field="listing.tags", repo=repo, pattern=TAG_RE
    )
    if not tags:
        raise ValueError(f"{repo}: listing.tags must not be empty")
    relationships = require_sorted_strings(
        listing.get("relationships"),
        field="listing.relationships",
        repo=repo,
        allowed=ALLOWED_RELATIONSHIPS,
    )

    url = require_string(listing.get("url"), field="listing.url", repo=repo)
    if not url.startswith("https://"):
        raise ValueError(f"{repo}: listing.url must use HTTPS")

    homepage = None
    if "homepage" in listing:
        homepage = require_string(
            listing.get("homepage"), field="listing.homepage", repo=repo
        )
        if not homepage.startswith("https://"):
            raise ValueError(f"{repo}: listing.homepage must use HTTPS")
        if homepage == url:
            raise ValueError(f"{repo}: listing.homepage must differ from listing.url")

    return {
        "repository": repo,
        "name": require_string(listing.get("name"), field="listing.name", repo=repo),
        "url": url,
        **({"homepage": homepage} if homepage is not None else {}),
        "description": require_string(
            listing.get("description"), field="listing.description", repo=repo
        ),
        "kind": kind,
        "type": require_string(listing.get("type"), field="listing.type", repo=repo),
        "tags": tags,
        "relationships": relationships,
        "group": group,
        "featureCandidate": feature_candidate,
        "reviewedAt": reviewed_at,
    }


def build_payload(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    repositories = set()
    projects = []
    for decision in decisions:
        repo = require_string(decision.get("repo"), field="repo", repo="decision")
        if repo in repositories:
            raise ValueError(f"duplicate repository decision: {repo}")
        repositories.add(repo)

        disposition = decision.get("decision")
        if disposition not in ALLOWED_DECISIONS:
            raise ValueError(f"{repo}: unsupported decision {disposition!r}")
        if disposition == "exclude":
            if "listing" in decision:
                raise ValueError(
                    f"{repo}: excluded decisions must not contain a listing"
                )
            continue
        projects.append(build_project(decision))

    projects.sort(
        key=lambda project: (project["name"].casefold(), project["repository"])
    )
    names = [project["name"] for project in projects]
    urls = [project["url"] for project in projects]
    if len(names) != len(set(names)):
        raise ValueError("included project names must be unique")
    if len(urls) != len(set(urls)):
        raise ValueError("included project URLs must be unique")
    return {"schemaVersion": 2, "projects": projects}


def render_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2) + "\n"


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail instead of writing when the generated output is missing or stale",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_payload(read_decisions(args.decisions))
    rendered = render_payload(payload)
    if args.check:
        if not args.out.exists() or args.out.read_text(encoding="utf-8") != rendered:
            raise SystemExit(
                f"{args.out} is stale; regenerate it with {Path(__file__).name}"
            )
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.out.with_name(f".{args.out.name}.tmp")
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(args.out)
    print(
        f"projects={len(payload['projects'])} "
        f"featured={sum(project['featureCandidate'] for project in payload['projects'])} "
        f"output={args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
