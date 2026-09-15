# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

import json
from pathlib import Path
from types import SimpleNamespace

import refresh_landscape_metadata as refresh


def test_default_input_uses_analyzer_output() -> None:
    assert refresh.DEFAULT_INPUT.name == "hydra-project-analysis-v1.ndjson"


def test_read_repositories_keeps_successful_unique_rows(tmp_path: Path) -> None:
    source = tmp_path / "analysis.ndjson"
    source.write_text(
        '{"repo":"example/one","status":"ok"}\n'
        '{"repo":"example/two","status":"error"}\n'
        '{"repo":"example/one","status":"ok"}\n',
        encoding="utf-8",
    )
    assert refresh.read_repositories(source) == ["example/one"]


def test_read_repositories_accepts_included_decisions(tmp_path: Path) -> None:
    source = tmp_path / "decisions.json"
    source.write_text(
        json.dumps(
            [
                {"repo": "example/included", "decision": "include"},
                {"repo": "example/excluded", "decision": "exclude"},
            ]
        ),
        encoding="utf-8",
    )
    assert refresh.read_repositories(source) == ["example/included"]


def test_parse_response_preserves_live_maintenance_evidence() -> None:
    payload = {
        "data": {
            "r0": {
                "nameWithOwner": "example/project",
                "url": "https://github.com/example/project",
                "homepageUrl": "https://example.com",
                "description": "Example",
                "isFork": False,
                "isArchived": False,
                "stargazerCount": 100,
                "pushedAt": "2026-07-23T09:20:37Z",
                "updatedAt": "2026-07-24T00:00:00Z",
                "createdAt": "2020-01-01T00:00:00Z",
                "defaultBranchRef": {
                    "name": "main",
                    "target": {
                        "oid": "a" * 40,
                        "committedDate": "2026-07-23T09:19:55Z",
                    },
                },
                "latestRelease": {
                    "tagName": "1.2.3",
                    "publishedAt": "2026-07-23T09:20:37Z",
                    "url": "https://github.com/example/project/releases/tag/1.2.3",
                },
                "parent": None,
            }
        }
    }
    row = refresh.parse_response(
        ["example/project"],
        payload,
        fetched_at="2026-07-31T00:00:00+00:00",
    )[0]
    assert row["status"] == "ok"
    assert row["stars"] == 100
    assert row["homepage"] == "https://example.com"
    assert row["default_branch"]["committed_at"] == "2026-07-23T09:19:55Z"
    assert row["default_branch"]["commit_url"].endswith(f"/commit/{'a' * 40}")
    assert row["latest_release"]["tag"] == "1.2.3"


def test_query_requests_the_repository_homepage() -> None:
    assert "homepageUrl" in refresh.build_query(["example/project"])


def test_unset_homepages_are_recorded_as_none() -> None:
    for value in (None, "", "   "):
        assert refresh.normalize_homepage(value) is None


def test_homepage_is_recorded_without_surrounding_whitespace() -> None:
    assert (
        refresh.normalize_homepage("  https://example.com  ") == "https://example.com"
    )


def test_fetch_batch_uses_one_graphql_request(
    monkeypatch,
) -> None:
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "data": {
                        "r0": {
                            "nameWithOwner": "example/project",
                            "url": "https://github.com/example/project",
                            "description": None,
                            "isFork": False,
                            "isArchived": False,
                            "stargazerCount": 1,
                            "pushedAt": None,
                            "updatedAt": None,
                            "createdAt": None,
                            "defaultBranchRef": None,
                            "latestRelease": None,
                            "parent": None,
                        }
                    }
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(refresh.subprocess, "run", fake_run)
    rows = refresh.fetch_batch(
        ["example/project"],
        gh_bin="gh",
        timeout=30,
        fetched_at="2026-07-31T00:00:00+00:00",
    )
    assert len(rows) == 1
    assert captured["command"][:3] == ["gh", "api", "graphql"]
