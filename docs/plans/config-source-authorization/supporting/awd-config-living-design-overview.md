# Living design overview and standalone slice inventory

To: AWD configuration agent
Date: 2026-11-01
Affected workflows: design authoring/review, delivery, replanning and automatic splitting.

## Problem

The Hydra implementation plan combines detailed engineering, an embedded JSON
slice inventory and a separately maintained summary table. It is difficult to
scan, and the table can drift when delivery or splitting changes the inventory.

The owner wants a readable front page that stays current throughout delivery.
It is **human-facing and agent-maintained**. Humans review decisions; they are
not responsible for maintaining the prose or table.

## Requested structure

Use one design directory containing:

```text
requirements.md
high-level-design.md
implementation-plan.md
overview.md
slices.json
supporting/
```

- `overview.md`: short, plain-language design goals, HLD summary and implementation
  summary, followed by the generated slice table. Include the next step and any
  decision waiting on the owner, with links to detailed documents.
- `slices.json`: the canonical machine-readable inventory. Move the embedded
  inventory here and include the data needed to render the table: full slice IDs,
  hierarchy, short descriptions, dependencies, status and separate production/test
  line ranges. Preserve existing ownership and acceptance information.
- `implementation-plan.md`: detailed engineering contracts and slice-specific
  explanation, referring to the standalone inventory without a second copy.
  Retain its sole `plan_key` ownership and explicitly reference the inventory.

Generate only the table. Agents maintain the prose as the agreed design and
implementation change. The first table column shows status, followed by full ID,
short description, production lines and test lines. Use readable markers such as
⏳ Pending, 🔄 Active and ✅ Done, mapped from existing lifecycle states.

## Updates and review

Update the overview and regenerate the table after implementation progress,
replanning, direction changes or automatic slice splitting. Splits must retain
hierarchical identity/history and show the current children, estimates and status.
Totals must not count both a superseded parent and its replacement children.
Keep the agreed incremental final-code estimation rules and count foundations once.

Reuse existing delivery state and rendering tools where possible. Do not introduce
a second execution tracker. A status marker must reflect actual execution evidence.
Updating the overview does not authorize a direction change or approve a replan.

Teach inventory readers, validators, design review and delivery admission to follow
the explicit inventory reference. Review evidence must bind both the engineering
plan and its canonical data. Resolve how routine progress changes affect review
freshness without presenting an old review as approval of changed slice definitions.
Preserve existing human approval gates and trusted external review records.

## Acceptance and adoption

- A reader can understand the goals, approach and progress from the overview.
- Editing canonical slice data regenerates the table without manual row edits.
- Completion, approved replanning and automatic splitting keep both prose and
  table current; IDs, status, estimates and totals remain consistent.
- Missing/invalid inventories and mismatched review bindings fail clearly.
- Existing embedded-inventory designs retain a supported migration path; moving
  the file does not silently transfer their review or approval.

Implement workflow support first. Then migrate this Hydra design and refresh its
affected review. Until then, its embedded inventory remains canonical. This memo
does not change the installed workflow, migrate the design, authorize product
implementation or send instructions to another agent.

Local example: [current implementation plan](../implementation-plan.md).
