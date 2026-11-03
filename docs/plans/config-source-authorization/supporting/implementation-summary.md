# Historical implementation-plan approval summary

This records the earlier API-correction draft. Its pending-review, publication
and approval statements are historical. The current [status](status.md) and
[overview](../overview.md) govern the approved plan and next delivery step.

Read the living [overview](../overview.md) for goals, approach, proposed PR groups
and the generated slice table. The [engineering plan](../implementation-plan.md)
references the canonical [schema-2 inventory](../slices.json).

The owner accepted the shared `UNSAFE_DISABLE_AUTHORIZATION_CHECKS` value and
`allowed_search_path_entries` name. Current requirements/HLD/plan and slice
acceptance incorporate those changes, remove the parallel unsafe-source flag,
and make Compose reject plugin requests requiring new discovery. All nine IDs,
owned paths, dependencies, statuses and estimates remain unchanged.

The earlier extraction review completed clean in round 3; its sidecar covers
that exact historical version. The current API correction requires refreshed
affected reviews and approvals. See the [decision record](hld-api-discussion.md#accepted-correction-authorize-search-path-entries)
and [earlier migration evidence](inventory-extraction.md).

Basic, Joblib and Submitit carry the planned worker contract. Other launchers must
adopt it before checked use. Live Windows containment, supported-version validation,
worker integration and performance remain implementation checks.

Before delivery, allocate authorized publication identifiers and exact core/plugin
news paths, refresh affected review, then establish the committed design/support/
sidecar baseline and existing growth-policy setup. The original design checkpoint
is commit `407ccfb38f83`; the API correction is local and uncommitted. No Hydra
implementation or delivery campaign has started. The public issue is still a draft.

Approval question: approve this corrected implementation plan and slice inventory?
This is final design acceptance, not permission to commit, implement or publish.
