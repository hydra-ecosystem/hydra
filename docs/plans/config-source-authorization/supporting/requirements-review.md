# Requirements author self-check

Historical snapshot before consolidated owner approval and formal review.
For the current phase result, see [design status](status.md).

This is an author self-check of the consolidated requirements draft. It is not an
independent review, a trusted stamp, or human acceptance. The workflow's formal
requirements review remains pending after exact requirements approval.

## Checks

- The document states its outcome, actors, trust assumptions, scope, exclusions,
  and observable acceptance without requiring the planning conversation.
- Framework users can supply plain YAML directories or uninstalled Python source
  packages. Availability and authorization are explicitly different.
- Compose config/override entries cannot self-authorize. The exact unsafe Python
  option previously discussed is retained with invocation-local scope.
- Source permission does not bypass the existing target execution policy.
- R1 and AC16 record the owner's platform decision: programmatic source additions
  by an authorized SearchPathPlugin count as source grants. Ordinary composed
  YAML and source precedence cannot make additional declarations authoritative.
- The shared authorization object keeps separate source, plugin, and execution grants.
  It requires context restoration and preserves execution-only semantics in any
  compatibility adapter. Deprecation is an HLD decision, not an approved change.
- Authorization must precede construction/availability imports, not merely final
  config delivery. Equivalent URI spellings are called out for HLD resolution.
- Compatibility behavior is distinguished from actual enforcement. Immediate
  containment errors in 1.4 reflect the owner's decision; other release/default
  decisions remain open.
- R9 requires a visible warning for successful legacy namespace discovery and a
  useful migration guide, without warning migrated plugins solely for retaining
  their namespace package. This is planned work, not a runtime change.
- R10 and AC17-AC20 specify the accepted basic filesystem/package containment. They
  distinguish it from source authorization and concurrent-tampering protection.
  Per-source link handling and immediate 1.4 errors are accepted requirements.
  Unsafe-option interactions require HLD decisions; no runtime validation is
  claimed.
- Requirements contain requirement/acceptance identifiers, not implementation
  slices or `plan_key` front matter.
- R11-R14 and AC21-AC25 cover authorization before plugin imports, explicit
  registration, lifecycle cleanup, worker propagation, and the namespace switch.
  Cached discovery is explicitly distinguished from current permission.
- No HLD or implementation-plan draft is represented as complete before its
  prerequisite approval. Their exact future paths and ownership are retained in
  [process constraints](process.md).
- Existing trusted review storage is not copied or replaced with local approval
  artifacts. The authoring baseline and uncommitted status are explicit.

## Open disposition before acceptance

The owner accepted authorization for all config sources. Basic containment
is also accepted as an individual requirement. The complete requirements remain a
draft until the remaining dispositions and exact summary are approved.
The HLD will resolve matching, interfaces, activation, and plugin integration;
the draft does not pretend those engineering decisions have been made.

The owner endorsed a shared authorization object and raised possible deprecation
of the existing execution whitelist object. R8 and AC11-AC13 record that direction.
The all-source decision replaces the initial import-focused scope. Platform
source grants are recorded in R1 and AC16. Package-resource containment and
immediate errors in 1.4 are now accepted in R10. The unsafe-option interaction
remains open. No current formal review is claimed.
