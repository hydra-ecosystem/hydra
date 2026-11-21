# Authoring and approval constraints

These constraints apply the owner's explicit overrides to the installed
`swe:design` workflow. They do not update the shared workflow package and do not
depend on a pending combined-workflow update.

## Canonical artifacts

The owner explicitly requested migration to the updated `swe:design` layout on
2026-11-02. This replaces the original embedded-inventory layout while preserving
the existing run, accepted requirements/HLD and approval history.

- [Requirements](../requirements.md): standalone intended outcome, scope,
  constraints, and observable acceptance criteria.
- `../high-level-design.md`: architecture, major interfaces, choices, and
  tradeoffs against the accepted requirements; author after the requirements
  phase is accepted and reviewed.
- `../implementation-plan.md`: implementation details, ordered manageable slices,
  and estimates against both accepted upstream documents; author after HLD
  acceptance. This file alone owns `plan_key` front matter and explicitly binds
  the exact same-directory `slices.json` through its `slice_inventory` reference.
- [Slice inventory](../slices.json): schema-2 canonical definitions, preserving
  full IDs, hierarchy, planning states, roles, intents, ownership, dependencies
  and acceptance; display fields carry summaries and production/test ranges.
- [Overview](../overview.md): human-facing and agent-maintained goals, approach,
  implementation summary and next step. Its table is rendered by the installed
  `swe_design_overview.py` helper; delivery progress comes from the existing
  managed campaign, not mutable progress flags in the planning inventory.
- This `supporting/` directory: process records, historical discussion,
  investigations, superseded decisions, and estimate detail. Use relative links
  and one canonical copy of shared evidence. Do not create phase directories
  without a concrete need.

The retained run was started with the earlier single-document function. The
owner required separate phase documents and now explicitly requested adopting
the updated layout. Its original pins/history are retained. Each later standalone
authoring or review operation must receive its actual phase file and upstream
requirements/HLD paths; passing the requirements file as an HLD or plan output
would violate that override. The installed interview's temporary-record location
is likewise replaced by this directory.

## Approval discipline

Preserve an actual human decision at each major phase. A clean review, authored
file, interview closure, or earlier discussion does not imply phase approval.
Review requirements first. Review the HLD against accepted requirements and the
implementation plan against both accepted upstream documents. When an upstream
decision changes, refresh affected reviews and approvals. Never copy, rewrite,
or manually manufacture a trusted stamp to imply approval.

The installed requirements interview requests agreement on a finite question
allowance before additional questioning. Retain existing conversation decisions
and prepare a reviewable draft before soliciting permission. The proposed round
uses no additional interview questions. Approval of a requirements summary may
be retained later only if it actually covers the exact unchanged summary.

## Implementation plan requirements

Every slice must have a complete hierarchical ID, clear title, implementation
responsibility, owned paths, dependencies, and acceptance checks. Requirements
and HLD must not contain a competing delivery inventory.

Keep the requirements coherent across the feature while planning. The owner
expects delivery across several pull requests. The current proposal groups the
nine slices into containment, lifecycle, namespace migration and integrated
authorization. Grouping remains a proposal; no PR creation is authorized.

Estimate separate production-code and test-code line ranges for every slice.
State whether ranges are incremental and provide project totals. Count shared
foundations once. Estimate final delivered code, not additions plus removals.
Count nonblank physical lines, excluding comment-only lines; count docstrings
and multiline statements physically. Shipped configuration, workflow
instructions, and packaging are production. Test helpers and fixture generators
are tests. Exclude development documentation, static fixture data, generated
files, and dependencies. Do not provide time estimates without a request.

## Fresh delivery readiness

Before a fresh implementation delivery, verify that accepted documents, required
durable support, repository-owned sidecars, and growth-policy setup are committed
at the chosen baseline. Account for both tracked and untracked work. Keep trusted
review records in their existing external storage.

This condition does not authorize a commit now. If the documents are still
uncommitted, report that delivery readiness is unproved and wait for explicit
commit authorization. Authoring does not authorize product implementation,
publication, or a new delivery campaign.
