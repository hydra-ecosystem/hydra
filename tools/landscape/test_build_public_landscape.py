# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

import json
from pathlib import Path

import build_public_landscape as landscape
import pytest


def included_listing(**overrides: object) -> dict[str, object]:
    listing: dict[str, object] = {
        "name": "Example",
        "url": "https://github.com/example/project",
        "description": "An example Hydra application.",
        "kind": "application",
        "type": "Application",
        "tags": ["robotics", "simulation"],
        "relationships": ["integrates"],
    }
    listing.update(overrides)
    return listing


def included_decision(**overrides: object) -> dict[str, object]:
    decision: dict[str, object] = {
        "repo": "example/project",
        "decision": "include",
        "group": "good_hydra_usage",
        "feature_candidate": True,
        "decided_at": "2026-08-10",
        "listing": included_listing(),
    }
    decision.update(overrides)
    return decision


def test_build_project_maps_canonical_decision_fields() -> None:
    assert landscape.build_project(included_decision()) == {
        "repository": "example/project",
        "name": "Example",
        "url": "https://github.com/example/project",
        "description": "An example Hydra application.",
        "kind": "application",
        "type": "Application",
        "tags": ["robotics", "simulation"],
        "relationships": ["integrates"],
        "group": "good_hydra_usage",
        "featureCandidate": True,
        "reviewedAt": "2026-08-10",
    }


def test_build_project_keeps_an_optional_homepage() -> None:
    project = landscape.build_project(
        included_decision(listing=included_listing(homepage="https://example.com"))
    )

    assert project["homepage"] == "https://example.com"
    assert project["url"] == "https://github.com/example/project"


def test_build_project_omits_the_homepage_key_when_absent() -> None:
    assert "homepage" not in landscape.build_project(included_decision())


def test_homepage_must_use_https() -> None:
    decision = included_decision(
        listing=included_listing(homepage="http://example.com")
    )

    with pytest.raises(ValueError, match="listing.homepage must use HTTPS"):
        landscape.build_project(decision)


def test_homepage_must_not_repeat_the_repository_url() -> None:
    decision = included_decision(
        listing=included_listing(homepage="https://github.com/example/project")
    )

    with pytest.raises(ValueError, match="must differ from listing.url"):
        landscape.build_project(decision)


def test_homepage_must_be_a_non_empty_string() -> None:
    decision = included_decision(listing=included_listing(homepage="   "))

    with pytest.raises(ValueError, match="listing.homepage must be a non-empty string"):
        landscape.build_project(decision)


def test_unknown_listing_fields_are_still_rejected() -> None:
    decision = included_decision(listing=included_listing(unexpected="value"))

    with pytest.raises(ValueError, match="listing fields must be"):
        landscape.build_project(decision)


def test_missing_required_listing_fields_are_still_rejected() -> None:
    listing = included_listing()
    del listing["url"]

    with pytest.raises(ValueError, match="listing fields must be"):
        landscape.build_project(included_decision(listing=listing))


def test_build_payload_omits_excluded_decisions() -> None:
    payload = landscape.build_payload(
        [
            {"repo": "example/excluded", "decision": "exclude"},
            included_decision(),
        ]
    )

    assert payload["schemaVersion"] == 2
    assert [project["repository"] for project in payload["projects"]] == [
        "example/project"
    ]


def test_featured_project_requires_good_hydra_usage() -> None:
    with pytest.raises(ValueError, match="must have good Hydra usage"):
        landscape.build_project(included_decision(group="powered_by_hydra"))


def test_excluded_decision_cannot_contain_a_listing() -> None:
    with pytest.raises(ValueError, match="must not contain a listing"):
        landscape.build_payload(
            [
                {
                    "repo": "example/excluded",
                    "decision": "exclude",
                    "listing": {},
                }
            ]
        )


def test_check_mode_rejects_stale_generated_output(tmp_path: Path) -> None:
    decisions = tmp_path / "decisions.json"
    decisions.write_text(json.dumps([included_decision()]) + "\n", encoding="utf-8")
    output = tmp_path / "landscape.json"

    assert landscape.main(["--decisions", str(decisions), "--out", str(output)]) == 0
    assert (
        landscape.main(["--decisions", str(decisions), "--out", str(output), "--check"])
        == 0
    )

    output.write_text("{}\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="is stale"):
        landscape.main(["--decisions", str(decisions), "--out", str(output), "--check"])
