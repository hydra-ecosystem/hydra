# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

import json
from pathlib import Path

import build_landscape_review as review


def usage(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "repo": "example/project",
        "tree_sha": "a" * 40,
        "version_evidence": [],
        "documentation_hydra_evidence": [],
        "readme_hydra_snippets": [],
        "readme_hydra_status": "none",
        "documentation_hydra_status": "none",
    }
    value.update(overrides)
    return value


def test_read_decisions_reads_json_array(tmp_path: Path) -> None:
    path = tmp_path / "decisions.json"
    path.write_text(
        json.dumps([{"repo": "example/project", "decision": "include"}]),
        encoding="utf-8",
    )

    assert review.read_decisions(path) == {
        "example/project": {"repo": "example/project", "decision": "include"}
    }


def test_default_analysis_uses_analyzer_output() -> None:
    assert review.DEFAULT_ANALYSIS.name == "hydra-project-analysis-v1.ndjson"


def test_version_summary_recognizes_compatible_root_range() -> None:
    result = review.version_summary(
        {},
        usage(
            version_evidence=[
                {
                    "kind": "declaration",
                    "scope": "root",
                    "path": "pyproject.toml",
                    "source": "line:10",
                    "specifier": ">=1.3.2,<1.5",
                }
            ]
        ),
    )
    assert result["currency"] == "allows_1_4"
    assert result["root_specifiers"] == [">=1.3.2,<1.5"]
    assert result["evidence"][0]["url"].endswith("/pyproject.toml#L10")


def test_version_summary_recognizes_old_pin() -> None:
    result = review.version_summary(
        {},
        usage(
            version_evidence=[
                {
                    "kind": "declaration",
                    "scope": "root",
                    "path": "requirements.txt",
                    "source": "line:1",
                    "specifier": "==1.1.0",
                }
            ]
        ),
    )
    assert result["currency"] == "excludes_1_4"


def test_version_summary_reports_locked_versions() -> None:
    result = review.version_summary(
        {},
        usage(
            version_evidence=[
                {
                    "kind": "lock",
                    "path": "uv.lock",
                    "source": "package:hydra-core",
                    "resolved_version": "1.3.2",
                }
            ]
        ),
    )
    assert result["locked_versions"] == ["1.3.2"]


def test_version_summary_recognizes_poetry_caret_range() -> None:
    result = review.version_summary(
        {},
        usage(
            version_evidence=[
                {
                    "kind": "declaration",
                    "scope": "root",
                    "path": "pyproject.toml",
                    "source": "project.dependencies[1]",
                    "specifier": "^1.3.2",
                }
            ]
        ),
    )
    assert result["currency"] == "allows_1_4"


def test_version_summary_recognizes_poetry_tilde_ranges() -> None:
    assert review.specifier_support("~1") == "allows_1_4"
    assert review.specifier_support("~1.3") == "excludes_1_4"
    assert review.specifier_support("~1.3.2") == "excludes_1_4"


def test_version_summary_treats_direct_reference_as_unknown() -> None:
    result = review.version_summary(
        {},
        usage(
            version_evidence=[
                {
                    "kind": "declaration",
                    "scope": "root",
                    "path": "requirements.txt",
                    "source": "line:1",
                    "requirement": (
                        "hydra-core @ git+https://github.com/"
                        "facebookresearch/hydra.git@v1.1.0"
                    ),
                    "specifier": None,
                }
            ]
        ),
    )
    assert result["currency"] == "unknown"


def test_documentation_summary_keeps_linked_documentation() -> None:
    result = review.documentation_summary(
        {},
        usage(
            documentation_hydra_status="documented",
            documentation_hydra_evidence=[
                {
                    "kind": "documented",
                    "path": "docs/config.md",
                    "line": 4,
                    "text": "Hydra configures the application.",
                },
                {
                    "kind": "mentioned",
                    "path": "CHANGELOG.md",
                    "line": 2,
                    "text": "Updated Hydra.",
                },
            ],
        ),
    )
    assert result["documentation_status"] == "documented"
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["url"].endswith("/docs/config.md#L4")


def test_documentation_summary_keeps_documented_readme_snippet() -> None:
    result = review.documentation_summary(
        {},
        usage(
            readme_hydra_status="documented",
            readme_path="README.md",
            readme_hydra_snippets=[
                {
                    "kind": "documented",
                    "line": 12,
                    "text": "Configure training with Hydra overrides.",
                }
            ],
        ),
    )
    assert result["documentation_status"] == "documented"
    assert result["evidence"][0]["url"].endswith("/README.md#L12")


def test_documentation_summary_excludes_developer_only_files() -> None:
    result = review.documentation_summary(
        {},
        usage(
            documentation_hydra_status="documented",
            documentation_hydra_evidence=[
                {
                    "kind": "documented",
                    "path": "AGENTS.md",
                    "line": 4,
                    "text": "Hydra contributor instructions.",
                },
                {
                    "kind": "documented",
                    "path": "CHANGELOG.md",
                    "line": 2,
                    "text": "Updated Hydra.",
                },
            ],
        ),
    )
    assert result["documentation_status"] == "none_found"
    assert result["evidence"] == []


def test_maintenance_summary_exposes_repository_activity() -> None:
    result = review.maintenance_summary(
        {"maintenance": "active", "evidence": []},
        {
            "status": "ok",
            "fetched_at": "2026-07-31T00:00:00Z",
            "url": "https://github.com/example/project",
            "homepage": "https://example.com",
            "pushed_at": "2026-07-23T09:20:37Z",
            "updated_at": "2026-07-02T00:00:00Z",
            "stars": 100,
            "archived": False,
            "fork": False,
            "parent": None,
            "default_branch": {
                "name": "main",
                "head_oid": "a" * 40,
                "committed_at": "2026-07-23T09:19:55Z",
                "commit_url": f"https://github.com/example/project/commit/{'a' * 40}",
            },
            "latest_release": {
                "tag": "1.2.3",
                "published_at": "2026-07-23T09:20:37Z",
                "url": "https://github.com/example/project/releases/tag/1.2.3",
            },
        },
    )
    assert result["days_since_default_branch_commit"] == 7
    assert result["days_since_push"] == 7
    assert result["days_since_release"] == 7
    assert result["stars"] == 100
    assert not result["archived"]
    assert result["homepage"] == "https://example.com"
    assert "homepage: https://example.com" in review.maintenance_markdown(result)


def test_maintenance_markdown_reports_a_missing_homepage() -> None:
    result = review.maintenance_summary(
        {"maintenance": "active", "evidence": []},
        {
            "status": "ok",
            "fetched_at": "2026-07-31T00:00:00Z",
            "url": "https://github.com/example/project",
            "homepage": None,
            "pushed_at": None,
            "updated_at": None,
            "stars": None,
            "archived": False,
            "fork": False,
            "parent": None,
            "default_branch": {},
            "latest_release": None,
        },
    )
    assert result["homepage"] is None
    assert "homepage: none" in review.maintenance_markdown(result)


def test_adapted_usage_requires_lineage_review() -> None:
    record = {
        "repo": "example/project",
        "provisional_disposition": "include",
        "classification": "confirmed",
        "origin": "adapted_upstream",
        "maintenance": {
            "assessment": "active",
            "archived": False,
            "days_since_default_branch_commit": 10,
        },
        "documentation": {"evidence": [{"url": "https://example.com"}]},
        "hydra_version": {"currency": "allows_1_4"},
    }
    assert review.review_tier(record) == "needs_lineage_review"


def test_hydra_itself_is_not_a_landscape_candidate() -> None:
    for repo in review.HYDRA_REPOSITORIES:
        record = {
            "repo": repo,
            "provisional_disposition": "include",
            "classification": "confirmed",
            "origin": "native",
        }
        assert review.review_tier(record) == "likely_exclude"
