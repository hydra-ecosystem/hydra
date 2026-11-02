# Config source and plugin authorization: overview

## Design goals

Let applications and framework users choose which config sources and plugins
Hydra may load. Declare a source once; do not require a second permission list.
Loaded configs cannot grant themselves more permissions. Keep config file reads
and directory listings inside the selected source root.

These checks control Hydra's own loading and execution paths. They do not sandbox
Python code. The full [requirements](requirements.md) define the agreed boundary.

## High-level design summary

Use one `AuthorizationPolicy` for config sources, plugins and the execution
whitelist used by instantiate and logging. Each category has separate grants.
`allowed_search_path_entries` permits configuration to request locations;
`config_search_path` on main/initialize selects and authorizes them.
Check permission before importing a plugin or initializing a config source.
Explicit Python, CLI and Compose source selections also authorize those sources;
config-defined selections need an existing grant.

Use `UNSAFE_DISABLE_AUTHORIZATION_CHECKS` in a policy field to opt that category
out explicitly. The same constant works in all three categories in 1.4 and 1.5.
Source containment and plugin discovery settings still apply. No separate
unsafe-source flag is added to main or Compose.

Restore policy and plugin registries when an initialization scope ends. Give
workers the same policy before Hydra restores state or loads plugins and configs.
In Hydra 1.4, legacy behavior remains the default with migration warnings;
explicit lists enable checks.
Hydra 1.5 defaults to empty grants and rejects legacy mode. Source-root escapes
are errors starting in 1.4. See the full [high-level design](high-level-design.md).

## Implementation summary

Build the work in nine slices, grouped into four proposed PRs:

1. Keep filesystem and package config access inside each source root (1–2).
2. Restore plugin registries and avoid unrelated imports during registration (3).
3. Warn namespace-plugin authors and explain entry-point migration (4).
4. Add the shared policy, source/plugin checks, worker support and public APIs (5–9).

The first three groups can land separately. Keep the final group together until
the complete authorization flow works; do not publish intermediate commits as a
complete feature. Do not add temporary feature flags or alternate implementations
to land them separately.

## Slices

Status: ⏳ Pending · 🔄 Active · ✅ Done. All slices are pending; implementation
has not started. The table is generated from the canonical [slice inventory](slices.json).

<!-- awd:slice-table:start -->
| Status | Slice ID | Short description | Production lines | Test lines |
| --- | --- | --- | ---: | ---: |
| ⏳ Pending | `config-source-authorization/1` | Keep filesystem config access inside its source root. | 70–110 | 90–150 |
| ⏳ Pending | `config-source-authorization/2` | Keep package and archive config access inside its source root. | 80–130 | 120–200 |
| ⏳ Pending | `config-source-authorization/3` | Restore plugin registries when initialization ends or fails. | 120–180 | 140–220 |
| ⏳ Pending | `config-source-authorization/4` | Warn namespace-plugin authors and guide entry-point migration. | 45–75 | 50–90 |
| ⏳ Pending | `config-source-authorization/5` | Share authorization state while preserving execution APIs. | 240–360 | 200–320 |
| ⏳ Pending | `config-source-authorization/6` | Select authorized plugins before importing them. | 180–280 | 200–320 |
| ⏳ Pending | `config-source-authorization/7` | Check config sources and stop config loading from granting permissions. | 230–350 | 220–360 |
| ⏳ Pending | `config-source-authorization/8` | Give workers the policy before they restore Hydra state. | 210–330 | 180–300 |
| ⏳ Pending | `config-source-authorization/9` | Expose and document the integrated Python and CLI APIs. | 300–460 | 160–260 |
| | **Project total** | Current slices; replaced parents excluded. | **1,475–2,275** | **1,360–2,220** |
<!-- awd:slice-table:end -->

Estimates are incremental final delivered lines; shared code counts once. See
the [estimate rules and basis](implementation-plan.md#estimates).

## Next step

Requirements review and general/DBB HLD review are clean, and the owner approved
the consolidated HLD. Refresh the implementation-plan review and obtain final
plan approval, followed by the committed delivery baseline.
The public tracking issue is [#3606](https://github.com/hydra-ecosystem/hydra/issues/3606),
and news paths are pinned in the slice inventory. No delivery campaign has been
opened and no Hydra implementation has started. This revision is uncommitted;
earlier review stamps cover their exact historical versions.

Agents maintain this page as implementation progresses or the plan changes,
including reviewed replanning and automatic splitting. The installed AWD helper
generates only the slice table. During delivery, it reads progress from the
existing managed campaign state; planning states in JSON are not progress flags.
An overview update does not approve a replan or new work.

Detailed documents: [requirements](requirements.md),
[high-level design](high-level-design.md),
[implementation plan](implementation-plan.md).
Review and approval history: [supporting status](supporting/status.md).
