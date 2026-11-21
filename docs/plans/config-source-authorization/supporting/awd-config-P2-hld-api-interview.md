# P2: Settle and present user-facing APIs during HLD

To: AWD configuration agent
Priority: P2
Date: 2026-11-01
Affected workflow: `swe:design`, HLD authoring/review/approval and detailed planning.

## Problem

The Hydra config-source authorization design reached detailed planning and a
nine-slice inventory before the owner was clearly shown the actual API. The HLD
approval summary covered architecture, while API signatures and important public
semantics were buried in documents or completed during detailed planning.

The owner then encountered the proposed `hydra.authorization(...)` signature and
had to ask what its parameters meant. An architecture-summary approval had been
treated as acceptance of a user-facing contract that was not clearly presented.
This creates expensive downstream planning around unsettled product decisions.

Owner feedback:

> API and user facing behaviors should be finalized presented clearly during the high level design.

> Finalizing those is potentially another interview process.

Source conversation:
<t3-thread://v2/714d9612-7992-4d9f-aeae-6d77c2f5f81e/80f40859-ab9f-4eda-96de-4fdf146c0321>

## Requested change

Make the HLD phase responsible for settling the public contract with the owner.
Support a focused design interview when material API or user-behavior choices
remain open. Its purpose differs from the requirements interview: requirements
establish outcomes and constraints; the HLD discussion decides how users interact
with the feature. Do not require another interview when those decisions are
already settled and explicitly approved.

Prepare a concrete proposal before questioning. Present actual API/CLI shapes,
representative user journeys and examples, defaults, combination/reset rules,
failure behavior, compatibility and migration choices as applicable. Explain
meaningful alternatives and tradeoffs in plain language. A document link or an
architecture-only summary does not replace showing the public contract clearly.

When discussion is needed, retain it in the HLD phase with an agreed finite
question allowance. Preserve prior requirements decisions and their actual
approvals. Do not silently reset an interview allowance, restart the whole design,
or infer API approval from requirements/architecture approval.

The sequence should be: concrete HLD/API draft -> focused discussion if needed ->
revised, settled HLD -> current design review -> explicit human HLD approval ->
detailed implementation planning. The final HLD approval summary must expose the
important interfaces and user-visible behavior, not only internal architecture.

Detailed planning owns internals, tests, slices, dependencies and estimates.
If it reveals a new material API or user-behavior decision, return that decision
to the HLD phase, revise and refresh affected review/approval before dependent
planning continues. Preserve unaffected decisions and existing run history.

## Acceptance

- An unresolved material API/default/behavior choice prevents progression to
  detailed planning; the workflow routes it to the responsible HLD discussion.
- A settled public contract can proceed without a redundant interview, using
  actual approval of the exact current HLD/API.
- HLD approval presents the actual interface and representative behavior clearly;
  it cannot be satisfied solely by a file link, review stamp or broad summary.
- A late public-contract change refreshes the affected HLD review and human
  approval instead of silently becoming an implementation-plan decision.
- Workflow guidance, authoring/review criteria and focused workflow tests agree
  on this phase boundary. This request does not prescribe a new review engine,
  ledger schema or unconditional second interview.

This memo requests workflow work by the AWD configuration agent. It does not
authorize deployment or change the installed workflow. The Hydra API and slice
plan remain provisional pending a clear HLD-level API review with the owner.
