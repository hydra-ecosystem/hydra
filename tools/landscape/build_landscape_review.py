#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

"""Build a resumable, evidence-backed Hydra Landscape review queue."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from analyze_hydra_projects import is_user_documentation_path
from build_public_landscape import ALLOWED_DECISIONS
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
WORK_ROOT = REPO_ROOT / "temp" / "hydra-dependents"
DEFAULT_ANALYSIS = WORK_ROOT / "hydra-project-analysis-v1.ndjson"
DEFAULT_USAGE = WORK_ROOT / "hydra-usage-analysis-v2.ndjson"
DEFAULT_METADATA = WORK_ROOT / "hydra-landscape-repository-metadata-v1.ndjson"
DEFAULT_DECISIONS = ROOT / "data" / "decisions.json"
DEFAULT_OUT = WORK_ROOT / "hydra-landscape-review-v1.ndjson"
DEFAULT_MARKDOWN = WORK_ROOT / "hydra-landscape-review-next-batch.md"
TARGET_HYDRA_VERSION = Version("1.4.0")
HYDRA_REPOSITORIES = {"facebookresearch/hydra", "hydra-ecosystem/hydra"}
UTC = timezone.utc


def read_latest_rows(path: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return latest
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"{path}:{line_number}: invalid JSON: {error}"
                ) from error
            repo = row.get("repo")
            if not isinstance(repo, str) or not repo:
                raise ValueError(f"{path}:{line_number}: missing repository name")
            latest[repo] = row
    return latest


def read_decisions(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{path}: expected an array of objects")
    decisions = {}
    for index, row in enumerate(rows):
        repo = row.get("repo")
        if not isinstance(repo, str) or not repo:
            raise ValueError(f"{path}: decision {index} is missing a repository name")
        if repo in decisions:
            raise ValueError(f"{path}: duplicate repository decision: {repo}")
        decisions[repo] = row
    return decisions


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def blob_url(repo: str, revision: str, path: str, line: int | None) -> str:
    anchor = f"#L{line}" if line else ""
    return f"https://github.com/{repo}/blob/{revision}/{path}{anchor}"


def normalize_specifier(specifier: str) -> str:
    if specifier.startswith("~") and not specifier.startswith("~="):
        base = Version(specifier[1:])
        upper = (
            f"{base.major + 1}.0.0"
            if len(base.release) == 1
            else f"{base.major}.{base.minor + 1}.0"
        )
        return f">={base},<{upper}"
    if not specifier.startswith("^"):
        return specifier
    base = Version(specifier[1:])
    if base.major:
        upper = f"{base.major + 1}.0.0"
    elif base.minor:
        upper = f"0.{base.minor + 1}.0"
    else:
        upper = f"0.0.{base.micro + 1}"
    return f">={base},<{upper}"


def specifier_support(specifier: str | None) -> str:
    if not specifier:
        return "unbounded"
    try:
        normalized = normalize_specifier(specifier)
        return (
            "allows_1_4"
            if TARGET_HYDRA_VERSION in SpecifierSet(normalized)
            else "excludes_1_4"
        )
    except (InvalidSpecifier, InvalidVersion):
        return "unknown"


def declaration_support(item: dict[str, Any]) -> str:
    specifier = item.get("specifier")
    if specifier:
        return specifier_support(str(specifier))
    requirement = item.get("requirement")
    if isinstance(requirement, str):
        try:
            if Requirement(requirement).url is not None:
                return "unknown"
        except InvalidRequirement:
            return "unknown"
    return "unbounded"


def version_summary(analysis: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    declarations = [
        item
        for item in usage.get("version_evidence", [])
        if isinstance(item, dict) and item.get("kind") == "declaration"
    ]
    root = [item for item in declarations if item.get("scope") == "root"]
    locks = [
        item
        for item in usage.get("version_evidence", [])
        if isinstance(item, dict) and item.get("kind") == "lock"
    ]
    supports = {declaration_support(item) for item in root}
    if not root:
        currency = "no_root_declaration"
    elif len(supports) == 1:
        currency = supports.pop()
    else:
        currency = "mixed"

    revision = str(usage.get("tree_sha") or "HEAD")
    repo = str(usage["repo"])
    evidence: list[dict[str, Any]] = [
        item
        for item in analysis.get("evidence", [])
        if item.get("kind") == "dependency"
    ]
    for item in root + locks:
        line = (
            int(str(item["source"]).split(":", 1)[1])
            if str(item.get("source", "")).startswith("line:")
            else None
        )
        url = blob_url(repo, revision, str(item["path"]), line)
        if url not in {existing["url"] for existing in evidence}:
            evidence.append({**item, "line": line, "url": url})
    return {
        "currency": currency,
        "root_specifiers": sorted({str(item.get("specifier") or "*") for item in root}),
        "locked_versions": sorted(
            {
                str(item.get("resolved_version"))
                for item in locks
                if item.get("resolved_version") is not None
            }
        ),
        "evidence": evidence,
    }


def documentation_summary(
    analysis: dict[str, Any], usage: dict[str, Any]
) -> dict[str, Any]:
    repo = str(usage["repo"])
    revision = str(usage.get("tree_sha") or "HEAD")
    evidence: list[dict[str, Any]] = [
        item
        for item in analysis.get("evidence", [])
        if item.get("kind") == "documentation"
        and is_user_documentation_path(str(item.get("path", "")))
    ]
    readme_path = str(usage.get("readme_path") or "README.md")
    if is_user_documentation_path(readme_path):
        for item in usage.get("readme_hydra_snippets", []):
            if not isinstance(item, dict) or item.get("kind") != "documented":
                continue
            url = blob_url(
                repo,
                revision,
                readme_path,
                int(item["line"]) if item.get("line") else None,
            )
            if url not in {existing["url"] for existing in evidence}:
                evidence.append({**item, "path": readme_path, "url": url})
    for item in usage.get("documentation_hydra_evidence", []):
        if (
            not isinstance(item, dict)
            or item.get("kind") != "documented"
            or not is_user_documentation_path(str(item.get("path", "")))
        ):
            continue
        url = blob_url(
            repo,
            revision,
            str(item["path"]),
            int(item["line"]) if item.get("line") else None,
        )
        if url not in {existing["url"] for existing in evidence}:
            evidence.append({**item, "url": url})
    return {
        "readme_status": usage.get("readme_hydra_status", "unknown"),
        "documentation_status": "documented" if evidence else "none_found",
        "evidence": evidence,
    }


def maintenance_summary(
    analysis: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    fetched_at = parse_timestamp(metadata.get("fetched_at"))
    if fetched_at is None:
        raise ValueError(f"maintenance metadata has no fetch time: {analysis['repo']}")
    default_branch = metadata.get("default_branch") or {}
    committed_at = parse_timestamp(default_branch.get("committed_at"))
    pushed_at = parse_timestamp(metadata.get("pushed_at"))
    latest_release = metadata.get("latest_release")
    released_at = parse_timestamp(
        latest_release.get("published_at") if latest_release else None
    )
    days_since_default_branch_commit = (
        max(0, (fetched_at - committed_at).days) if committed_at is not None else None
    )
    days_since_push = (
        max(0, (fetched_at - pushed_at).days) if pushed_at is not None else None
    )
    days_since_release = (
        max(0, (fetched_at - released_at).days) if released_at is not None else None
    )
    return {
        "assessment": analysis.get("maintenance", "unknown"),
        "metadata_fetched_at": metadata["fetched_at"],
        "default_branch": default_branch,
        "days_since_default_branch_commit": days_since_default_branch_commit,
        "pushed_at": metadata.get("pushed_at"),
        "updated_at": metadata.get("updated_at"),
        "days_since_push": days_since_push,
        "latest_release": latest_release,
        "days_since_release": days_since_release,
        "archived": bool(metadata.get("archived")),
        "stars": metadata.get("stars"),
        "fork": bool(metadata.get("fork")),
        "parent": metadata.get("parent"),
        "url": metadata.get("url") or analysis.get("project_url"),
        "homepage": metadata.get("homepage"),
        "evidence": [
            item
            for item in analysis.get("evidence", [])
            if item.get("kind") == "maintenance"
        ],
    }


def evidence_gaps(record: dict[str, Any]) -> list[str]:
    gaps = []
    maintenance = record["maintenance"]
    documentation = record["documentation"]
    version = record["hydra_version"]
    if (
        maintenance["default_branch"].get("committed_at") is None
        and not maintenance["evidence"]
    ):
        gaps.append("maintenance")
    if not documentation["evidence"]:
        gaps.append("hydra_documentation")
    if version["currency"] == "no_root_declaration":
        gaps.append("root_hydra_version")
    if record["classification"] != "confirmed":
        gaps.append("confirmed_hydra_usage")
    if record["origin"] in {"unknown", "transitive", "vendored_or_copied"}:
        gaps.append("hydra_usage_origin")
    if record["repo"] in HYDRA_REPOSITORIES:
        gaps.append("hydra_itself")
    return gaps


def review_tier(record: dict[str, Any]) -> str:
    if record["repo"] in HYDRA_REPOSITORIES:
        return "likely_exclude"
    if record["provisional_disposition"] == "exclude":
        return "likely_exclude"
    if record["classification"] != "confirmed":
        return "needs_usage_review"
    if record["origin"] in {
        "adapted_upstream",
        "transitive",
        "vendored_or_copied",
    }:
        return "needs_lineage_review"
    if (
        record["maintenance"]["assessment"] in {"active", "minimally_maintained"}
        and not record["maintenance"]["archived"]
        and record["maintenance"]["days_since_default_branch_commit"] is not None
        and record["maintenance"]["days_since_default_branch_commit"] <= 730
        and record["documentation"]["evidence"]
        and record["hydra_version"]["currency"] in {"allows_1_4", "unbounded"}
    ):
        return "strong_candidate"
    return "candidate_needs_evidence"


TIER_PRIORITY = {
    "strong_candidate": 0,
    "candidate_needs_evidence": 1,
    "needs_usage_review": 2,
    "needs_lineage_review": 3,
    "likely_exclude": 4,
}


def build_record(
    analysis: dict[str, Any],
    usage: dict[str, Any],
    metadata: dict[str, Any],
    decision: dict[str, Any] | None,
) -> dict[str, Any]:
    record = {
        "repo": analysis["repo"],
        "project_name": analysis["project_name"],
        "project_url": analysis["project_url"],
        "category": analysis["category"],
        "domains": analysis["domains"],
        "summary": analysis["summary"],
        "relationships": analysis["relationships"],
        "reach": analysis["reach"],
        "origin": analysis["origin"],
        "classification": analysis["classification"],
        "confidence": analysis["confidence"],
        "provisional_disposition": analysis["disposition"],
        "provisional_rationale": analysis["rationale"],
        "maintenance": maintenance_summary(analysis, metadata),
        "documentation": documentation_summary(analysis, usage),
        "hydra_version": version_summary(analysis, usage),
        "evidence": analysis["evidence"],
        "unresolved_questions": analysis["unresolved_questions"],
        "decision": (decision or {}).get("decision", "pending"),
        "decision_note": (decision or {}).get("note"),
    }
    record["evidence_gaps"] = evidence_gaps(record)
    record["review_tier"] = review_tier(record)
    return record


def write_ndjson(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    temporary.replace(path)


def evidence_links(items: list[dict[str, Any]], limit: int = 3) -> str:
    links = []
    for item in items[:limit]:
        if not item.get("url"):
            continue
        label = str(item.get("path", "evidence"))
        if item.get("line"):
            label += f":{item['line']}"
        links.append(f"[{label}]({item['url']})")
    return ", ".join(links) if links else "none found"


def maintenance_markdown(maintenance: dict[str, Any]) -> str:
    default_branch = maintenance["default_branch"]
    commit_url = default_branch.get("commit_url") or maintenance["url"]
    committed_at = default_branch.get("committed_at") or "unknown"
    latest_release = maintenance["latest_release"]
    release = (
        f"[{latest_release['tag']} · {latest_release['published_at']}]"
        f"({latest_release['url']})"
        if latest_release
        else "none"
    )
    stars = maintenance["stars"] if maintenance["stars"] is not None else "unknown"
    homepage = maintenance.get("homepage")
    return (
        f"- **Maintenance:** {maintenance['assessment']} · "
        f"default-branch commit: [{committed_at}]({commit_url}) · "
        f"latest release: {release} · stars: {stars} · "
        f"homepage: {homepage or 'none'} · "
        f"metadata fetched: {maintenance['metadata_fetched_at']}"
    )


def write_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Hydra Landscape: next review batch",
        "",
        "AI dispositions and review tiers are routing aids, not maintainer decisions.",
        "",
    ]
    for row in rows:
        maintenance = row["maintenance"]
        documentation = row["documentation"]
        version = row["hydra_version"]
        lines.extend(
            [
                f"## {row['project_name']}",
                "",
                f"[{row['repo']}]({row['project_url']}) · "
                f"{row['category']} · {', '.join(row['domains'])}",
                "",
                f"- **Provisional:** {row['provisional_disposition']} · "
                f"{row['review_tier']} · decision: {row['decision']}",
                f"- **Hydra usage:** {row['classification']} · "
                f"{row['origin']} · {row['reach']} · "
                f"{', '.join(row['relationships']) or 'none'}",
                maintenance_markdown(maintenance),
                f"- **Hydra documentation:** "
                f"{documentation['documentation_status']} · "
                f"{evidence_links(documentation['evidence'])}",
                f"- **Hydra version:** {version['currency']} · "
                f"root: {', '.join(version['root_specifiers']) or 'none'} · "
                f"locked: {', '.join(version['locked_versions']) or 'none'} · "
                f"{evidence_links(version['evidence'])}",
                f"- **Other evidence:** {evidence_links(row['evidence'], limit=5)}",
                f"- **Evidence gaps:** {', '.join(row['evidence_gaps']) or 'none'}",
                "",
                row["summary"],
                "",
                f"Provisional rationale: {row['provisional_rationale']}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument("--usage", type=Path, default=DEFAULT_USAGE)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--batch-size", type=int, default=15)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be at least 1")
    analyses = read_latest_rows(args.analysis)
    usages = read_latest_rows(args.usage)
    decisions = read_decisions(args.decisions)
    metadata = read_latest_rows(args.metadata)

    invalid_decisions = {
        repo: row.get("decision")
        for repo, row in decisions.items()
        if row.get("decision") not in ALLOWED_DECISIONS
    }
    if invalid_decisions:
        raise ValueError(f"invalid decisions: {invalid_decisions}")

    rows = []
    for repo, analysis in analyses.items():
        if analysis.get("status") != "ok":
            continue
        if repo not in usages:
            raise ValueError(f"missing usage evidence for {repo}")
        if repo not in metadata or metadata[repo].get("status") != "ok":
            raise ValueError(f"missing current maintenance metadata for {repo}")
        record = build_record(
            analysis,
            usages[repo],
            metadata[repo],
            decisions.get(repo),
        )
        rows.append(record)
    rows.sort(
        key=lambda row: (
            row["decision"] != "pending",
            TIER_PRIORITY[row["review_tier"]],
            -(row["maintenance"]["stars"] or 0),
            row["repo"].lower(),
        )
    )
    write_ndjson(args.out, rows)
    pending = [row for row in rows if row["decision"] == "pending"]
    write_markdown(args.markdown, pending[: args.batch_size])
    print(
        f"reviewed={len(rows) - len(pending)} pending={len(pending)} "
        f"batch={min(args.batch_size, len(pending))} "
        f"queue={args.out} markdown={args.markdown}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
