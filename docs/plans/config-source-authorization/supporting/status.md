# Design status

## Current position

On 2026-11-02 the owner requested alignment with the updated `swe:design`.
Migration is complete. Start at the living [overview](../overview.md); its table
is generated from canonical [slices.json](../slices.json). The engineering
[implementation plan](../implementation-plan.md) retains sole plan-key ownership
and binds the exact inventory hash. The installed package helper renders/checks
the table; no local renderer or second execution tracker was introduced.

All nine slice definitions, dependencies, ownership, acceptance and estimates
are preserved. All implementation remains pending. The accepted requirements
and HLD are byte-for-byte unchanged. The pre-migration plan is retained once as
historical text, not a competing current owner/inventory. See
[migration evidence](inventory-extraction.md).

Fresh current-agent affected review completed clean in round 3 with zero
findings, covering the plan, overview and automatically expanded inventory.
The helper verified both upstream authorities as reviewed-current, finalized
the report and completed durable clean closeout. It refreshed the plan sidecar
to bind all three current target files and both design dependencies. Original
reports/approvals remain history; no stamp was manually edited or transferred.

The retained checkpoint `f01-s33-block-the-responsible-final-lld-approval` now
awaits final human plan approval. No product implementation, commit, push,
publication, installed-workflow edit or new delivery campaign occurred.
Committed baseline, numeric news paths and growth-policy readiness remain
future authorized delivery prerequisites.

## Previous layout checkpoint

The following records describe earlier exact documents and checkpoints. Their
pending-work statements are historical; the current position above governs.

The owner requested a clearer implementation-plan layout before final approval:
plain-language goals, HLD and implementation summaries, then a status/ID/
description/production/test table. That revision is prepared for owner reading.
Current plan SHA256:
`65b3061a8f880cbd52b9a59315accfb17c96494d1fea4cedb804941986c4ec0a`.
All nine implementation slices are pending. A comparison with the pre-edit
document verified unchanged canonical inventory, detailed engineering, estimate
values/rules and delivery checks. The accepted requirements/HLD are unchanged.
Round 2 below covers the earlier plan bytes; the helper-owned sidecar has not
been edited or represented as a review of this layout revision. Review refresh
and final approval remain pending. The owner subsequently agreed to prepare
the [local AWD-config memo](awd-config-living-design-overview.md) before changing
the workflow or migrating this design. It covers the living agent-maintained
overview, standalone inventory and generated table. The memo has not been sent;
no workflow changes or design migration occurred.

The owner approved the revised HLD with "Go ahead." after the clean combined
general/DBB round 3. The exact accepted HLD remains SHA256
`4aac3ec633f26ff49327e0374f5fdbb96a592815011e90a62d1ee5c2dfa03a48`;
the accepted requirements remain SHA256
`2052ba2d84fc04b98c5485b1561dcab752840b1e3f0e131908233566b98241e7`.
See the [approval record](hld-api-discussion.md#owner-acceptance-hld-after-dbb-challenge).

The [implementation plan](../implementation-plan.md) is refreshed against both
accepted inputs. It retains the same plan identity and nine slice IDs, with four
proposed PR groups. The new engineering covers the approved public module API,
per-category defaults/replacement, literal CLI/Compose source provenance, plugin
entry-point names, config-load/conversion guards and worker restoration. Updated
incremental estimates are 1,475–2,275 production lines and 1,360–2,220 test-code
lines. The refreshed current-agent detailed-plan review completed clean in
round 2, with zero findings, for the pre-layout revision recorded below. Final
human plan approval is pending.

The structural audit passed: nine unique ordered slices, valid dependency order,
all owned paths existing or explicitly planned, correct estimate totals and
unchanged accepted input hashes. The harmless structured-conversion probe passed;
both ConfigStore registration and instantiate conversion execute default factories.
The [engineering evidence](engineering-notes.md) records the guard placement.
These are design checks, not product implementation or runtime security validation.

Retain checkpoint `f01-s33-block-the-responsible-final-lld-approval` for final
human approval. Whole-plan review used the existing allowance. No commit,
product implementation, publication or delivery campaign is
authorized. All design files remain local and uncommitted; committed baseline,
numeric news paths and growth-policy readiness remain future prerequisites.

## Refreshed detailed-plan review: round 2, 2026-11-01

- Helper invocation: `run_5b4b0mwc3jj4qsy8ccbd6xtg51-plan-api-refresh`.
- Target SHA256:
  `d033609319582d1386b31c9960aceff727246e9069ad46884b9fcd9abfc7c00d`.
- Exact accepted requirements/HLD are unchanged and both helper-validated as
  reviewed-current, without an authority override.
- Target manifest:
  `831646fe34ce1d081e8c739dd724a5f761a94eba9b2b1af347fdae75b2156638`.
- Baseline manifest:
  `443490b6e67bcc83bf0028601a3329de995f602d12dd625dcfecf81d378af29a`.
- Immutable report: `temp/reviews/implementation-plan/rounds/round-02.md`;
  SHA256 `25103d05d60c55de9c44979f4b433b45f5c87de624b9114563b12997e989d5d2`.
- Result: clean; no findings, fix claims, dispositions or target edits during
  review. This is current-agent review, not independent-worker or DBB review.
  The completed DBB challenge covers the accepted HLD only.
- The helper finalized the round, checked the clean predicate, registered the
  empty decision mapping and exact design dependencies, then finished durable
  clean closeout. Its version-5 plan sidecar binds the current bytes and both
  dependencies. Its committed-predecessor list is empty: these design documents
  are untracked. The trail retains immutable round 1 as historical evidence.
  No manual sidecar edits or human-approval claims.
- Structural audit also passed forty-one local design/support links; accepted
  inputs and all owned-path/dependency/estimate checks passed.
- No product tests, live Windows execution, worker integration validation or
  performance benchmark occurred. These remain implementation acceptance checks.
- Final owner approval, authorized publication identifiers/news paths, committed
  baseline and growth-policy readiness remain separate pending prerequisites.

## Earlier checkpoint history

The entries below retain earlier exact review and approval evidence. Statements
that work was pending describe those earlier checkpoints; the current position
above takes precedence. Original reports and helper-owned stamps are not edited
to imply approval of successor documents.

Current checkpoint: the public-API discussion is complete. Its final three
topics were settled, including the separately discussed legacy/unsafe nesting
cases; see [the decision record](hld-api-discussion.md). Requirements and HLD now
incorporate those accepted decisions. The revised HLD is ready for owner reading,
with [a shorter summary](hld-summary.md). The revised requirements have now
completed refreshed current-agent review clean in round 4, with zero findings.
The owner accepted that revision with "ok. whats next?" after the final
instantiate restriction. The agent stated that interpretation before proceeding.
The HLD has now completed refreshed current-agent review clean in round 2.
Its whole-document owner approval remains pending. The implementation plan is explicitly
superseded and awaits refreshed upstream approval before its engineering and
inventory are revised.

The owner explicitly approved the bounded DBB challenge before HLD approval.
The configured native `dbb` reviewer completed the existing HLD trail's round 3
clean, with zero findings. The general component is also clean. The helper
validated the original specialist report and actual launch, finalized the combined
round, and completed durable clean closeout with DBB evidence. No design bytes
changed. Whole-HLD owner approval remains the next gate.

During approval discussion, the owner clarified that no configuration form
(YAML, dataclass or resulting DictConfig) carries grant authority. This is a
Hydra-boundary promise, not a Python sandbox. The requirements and HLD now
incorporate that clarification, including the distinction between ConfigStore
data registration and authorization changes during config loading. The owner
also required authorization APIs to be non-whitelistable instantiate targets;
R8/AC13 and the HLD now state that explicitly. Round 4 covers the current
requirements; earlier rounds remain exact historical evidence.

Retain the existing correction/approval checkpoint
`f01-s33-block-the-responsible-final-lld-approval`. All three prior reviews were
clean for their exact earlier bytes. Their original records and earlier human
approvals remain history. The helper has refreshed the requirements sidecar for
the reviewed current bytes. The HLD sidecar has also been refreshed by the helper
with the exact accepted requirements dependency; only the plan stamp is stale.
No commit, product implementation or publication occurred. A committed delivery
baseline and growth-policy readiness have not been established or authorized.

The owner has returned and requested resumption after HLD authoring. Current revised
document hashes are recorded in the
[revision evidence](hld-authoring.md#authorization-api-instantiate-restriction-2026-11-01).
The earlier current-agent consistency check passed, including local links and
Python example syntax. The requirements now also have the completed refreshed
reviews recorded below. The detailed-plan refresh/review has not run.

Next steps on resumption, in order:

1. Requirements acceptance, refreshed general HLD review and the independent
   DBB challenge are complete. Combined round 3 is clean with zero findings.
2. Obtain whole-HLD owner approval. A clean combined review does not supply that
   human approval. There are no specialist findings requiring disposition.
3. Refresh the detailed implementation plan, affected slices, owned paths,
   acceptance checks and production/test estimates against both approved inputs.
   Review the plan and obtain the owner's approval.
4. If the owner later authorizes delivery, establish the committed design/support/
   sidecar baseline and growth-policy readiness before starting implementation.
   No commit, delivery campaign or product implementation is authorized now.

- Feature: config source authorization for Compose and framework-owned
  `hydra.main()` entry points.
- Design root: `docs/plans/config-source-authorization/`.
- Requirements: revised to reflect the accepted API decisions. Round 4 is clean
  for SHA256 `2052ba2d84fc04b98c5485b1561dcab752840b1e3f0e131908233566b98241e7`;
  the owner has accepted this revision in the recorded exchange. Earlier
  approval remains attached to the earlier bytes.
- The owner endorsed a shared source/execution authorization object, including
  context-manager use, and raised possible deprecation of the execution-only
  object. R8 and AC11-AC13 now record that direction; this is not approval of the
  complete requirements document at that earlier point.
- HLD: [revised architecture](../high-level-design.md) contains the consolidated
  API, source declarations, plugin selectors, release behavior and diagnostics.
  Current SHA256 `4aac3ec633f26ff49327e0374f5fdbb96a592815011e90a62d1ee5c2dfa03a48`
  completed round-2 current-agent review clean, with zero findings. Its exact
  requirements dependency is reviewed and owner-accepted. Human HLD approval
  and any additional specialist review are still separate and pending.
  The earlier revision completed formal review clean; owner accepted
  SHA256 `d1bb0bd672fc26cc83012c352fc2e2868354e8160eb98649f623f292b88e189c`
  with "hld sounds ok". The owner subsequently limited that acceptance to the
  architecture summary and reopened actual API/behavior approval. Neither the
  detailed plan nor implementation is approved.
- Implementation plan: [superseded detailed draft](../implementation-plan.md),
  not current implementation instructions. Its earlier formal review was clean;
  the changed APIs invalidate the affected engineering, readiness and estimates.
  It retains the only plan identity and provisional nine-slice inventory. The old
  estimates were incremental
  1,355–2,105 production lines and 1,280–2,100 test-code lines, including the specified
  integration/platform/failure work. Engineering evidence is retained in
  [engineering notes](engineering-notes.md). Numeric news paths await authorized
  issue/PR allocation and must be included in a refreshed plan before delivery.
- Product implementation and commits: not authorized by design authoring.
- The owner accepted basic containment with "good enough" after presentation of
  the concrete R10 proposal: per-source resolved-root checks, internal links
  allowed, external links refused, and no concurrent-replacement protection.
  R10 and AC17-AC20 record that individual requirements decision. It does not
  approve the full requirements document, implementation, or the HLD.
- Namespace deprecation warning and migration-guide usability are requirements
  R9 and AC14-AC15 only; no runtime, test, or published-guide changes were made.
- The owner clarified that work remains in planning and will likely span several
  pull requests. PR boundaries remain undecided until implementation planning.
- Workflow: `run_5b4b0mwc3jj4qsy8ccbd6xtg51`, invoked through `swe:design`.
- Security reviewer selection on the original design invocation remains `default`.
  The owner explicitly approved an additional `dbb` HLD review invocation at the
  retained correction checkpoint. That combined review is now complete and clean.
- Governing external review documents passed to the workflow: `none`.
- Requirements review closeout: `durable`, scope kind `path`, exact target
  `requirements.md`, non-PR delivery context. The baseline remains null; process instructions, research,
  approval records, and implementation files are review context, not normative
  subject-matter authorities. Trusted helper records stay outside the repository;
  any final document sidecar is helper-owned and does not authorize a commit.
- Completed requirements helper run:
  `run_5b4b0mwc3jj4qsy8ccbd6xtg51-requirements-f01-f02`, round 1.
  Trail: `/home/omry/dev/hydra/temp/reviews/requirements`.
  External authority/input root:
  `/home/omry/.local/state/awd/swe-review-authority/runs/run_5b4b0mwc3jj4qsy8ccbd6xtg51-requirements-f01-f02`.
  Target manifest identity:
  `64c4751bfe711ecc4f37074144f2c56221869c68a983c705fd9410a7ac6ae878`.
  No design-document dependencies are declared. The required eventual sidecar is
  `.review/requirements.md` beside the requirements file; it now records clean closeout.
  The existing review loop has ten rounds; no new allowance is introduced.
- Requirements scope and approval gate completed using the owner's exact approval.
- The draft now incorporates the plugin investigation and subsequent decisions.
  R11-R14 and AC21-AC25 record plugin authorization, context cleanup, workers, and
  the namespace switch. The owner has now handed the review back and approved
  proceeding. HLD authoring has now completed; see [authoring evidence](hld-authoring.md).

## Completed DBB HLD review: round 3, 2026-11-01

- User approved the proposed bounded specialist challenge with "yes".
- Helper invocation: `run_5b4b0mwc3jj4qsy8ccbd6xtg51-hld-dbb`.
- Original authority root: `/home/omry/.local/state/awd/swe-review-authority`.
- The configured `dbb` role was available through the native host. The fresh
  native agent handle returned by the host is `/root/config_authorization_hld_dbb`;
  this canonical handle is retained as reviewer and reviewer_session_id. No
  parent history or earlier findings were supplied to the specialist.
- Frozen request identity:
  `627a7e8a7767d601adb56633d0487121ef4dd15337aa316fc5c1b88a2933c113`.
- Target and requirements are unchanged from round 2, with their exact manifests
  preserved. Selected review profile is full; applicable validation receipt is
  null. Pre-launch replay froze these inputs; actual launch binding was then
  retained through the helper before review.
- Original immutable report path:
  `/home/omry/.local/state/awd/swe-review-authority/runs/run_5b4b0mwc3jj4qsy8ccbd6xtg51-hld-dbb/security-report-r3.json`.
- Original DBB report SHA256:
  `24ccde2335beb798bcd2cfba6aa02eae7014e90d66860ef0945d8c85cf3afa42`.
- Specialist outcome: clean, zero findings. Both specialist and coordinator
  independently checked the report with the read-only security_report_binding
  validator. Original report bytes were not changed.
- General-component evidence: `temp/reviews/high-level-design/scratch/round-03-general-review.md`.
  No general findings identified. Combined round report:
  `temp/reviews/high-level-design/rounds/round-03.md`, SHA256
  `6b9839d0adc3316a43f110d285abe0dcb4023405d982522bfb91cf5b88f0a85c`.
- Combined result: clean. The helper finalized against the original DBB report,
  validated the clean predicate, completed durable closeout and refreshed the
  HLD sidecar with DBB evidence and the exact requirements dependency.
- Closeout reports security_review_incomplete=false and
  security_review_requires_restart=false. Active review ownership is released.
- Scope limits: HLD assessment only; no production implementation or dynamic
  security tests. Platform/resource-loader/worker/origin/rollback/performance
  details remain LLD work. The specialist's native revision query was blocked by
  its sandbox; it checked retained manifests, while the coordinator independently
  confirmed the actual Sapling revision matches the frozen reviewed revision.
- A preliminary lookup in an empty per-run authority area could not validate the
  existing requirements proof. It allocated no round. The approved existing
  authority store then verified the exact requirements as reviewed-current with
  no authority override or additional human confirmation.
- The review uses the existing ten-round allowance, not a fresh interview or
  delivery campaign. Product implementation, commits and scope expansion remain
  unauthorized.

## Completed general HLD review: round 2, 2026-11-01

- Helper invocation: `run_5b4b0mwc3jj4qsy8ccbd6xtg51-hld-api-refresh`.
- Existing HLD trail/allowance retained; original round 1 is unchanged.
- Target SHA256:
  `4aac3ec633f26ff49327e0374f5fdbb96a592815011e90a62d1ee5c2dfa03a48`.
- Governing requirements SHA256:
  `2052ba2d84fc04b98c5485b1561dcab752840b1e3f0e131908233566b98241e7`.
- Target manifest:
  `fe5ed233aec626f5038a2a19eee8d6940dba8843e5114eb24fdb684774f89f1f`.
- Baseline manifest:
  `38aff8ec44eeb7f5f040ba87345e39d3170851b9d7cc6ae71270bc29ac011bb4`.
- Immutable report: `temp/reviews/high-level-design/rounds/round-02.md`, SHA256
  `471ddcda627a77c396585243eb07b3970f15f410f10a6e519743bbfdb18776ea`.
- Result: clean, zero findings, current-agent HLD review. Not independent or DBB.
- Helper validated the baseline as reviewed-current, finished clean durable
  closeout and issued the HLD sidecar with its exact design dependency.
- Seven local links and five Python examples passed read-only document checks.
- Requirements/HLD bytes did not change during review. Nothing was implemented,
  committed, benchmarked or tested on Windows. The detailed plan stays stale.

## Requirements review: round 4, 2026-11-01

The owner required the authorization API to be blocked from instantiate. R8 and
AC13 now specify non-whitelistable public/canonical identities, aliases and
policy construction/context/helper targets. Ordinary grants cannot permit them;
the separate explicit unsafe execution opt-out retains its established meaning.

- Helper invocation:
  `run_5b4b0mwc3jj4qsy8ccbd6xtg51-requirements-auth-api`.
- Existing trail and allowance retained; rounds 1–3 are unchanged.
- Result: clean current-agent requirements review, zero findings; not DBB.
- Requirements SHA256:
  `2052ba2d84fc04b98c5485b1561dcab752840b1e3f0e131908233566b98241e7`.
- Target manifest:
  `8495a611b51f05cbfb1e30ac1a5ad052b719b837d6b2cf374f3de7bfb40b9ac9`.
- Report: `temp/reviews/requirements/rounds/round-04.md`, SHA256
  `ff9afad347e5151a18aa02d9b6dac920cc0a7ebb9166eb2d5b0d28406dd60ea5`.
- Helper validated clean durable closeout and refreshed the requirements sidecar.
  Structural/link/example checks passed. No runtime enforcement is claimed.
- Owner acceptance of this requirements revision has now been recorded; the
  refreshed HLD review is complete as described above.

## Earlier corrected requirements review: round 3, 2026-11-01

- Existing parent workflow and review trail are retained; the ten-round allowance
  was not restarted. Rounds 1 and 2 and their reports are unchanged.
- Helper invocation:
  `run_5b4b0mwc3jj4qsy8ccbd6xtg51-requirements-config-forms`.
- Result: clean, zero findings. Current-agent review, not independent or DBB.
- Exact requirements SHA256:
  `b0055f81858206f95486ef7072133656ed4fbf81f92c86ec76a153a3308ac296`.
- Target manifest:
  `28fe8104861b43eca24230495a985948bbf5d3deaaff427cd6ecb75d5223955b`.
- Immutable report: `temp/reviews/requirements/rounds/round-03.md`, SHA256
  `223f4b4102e872d87ea517a07c1111436c659744b72ce8dd945670ba5e8b710e`.
- The helper validated and finished durable clean closeout, updated the current
  requirements sidecar and released active review ownership. No manual stamp
  edit, product change or implementation is claimed.
- Read-only checks: 14 requirements, 25 acceptance criteria, seven local links
  and five Python example syntax checks across requirements/HLD. No competing
  slice inventory or plan identity was introduced.
- Exact whole-document requirements acceptance remains pending. The owner's
  "sg" accepted the explained operational requirements, not the then-unwritten
  corrected whole document. HLD review is next after that requirements gate.

## Earlier refreshed requirements review: round 2, 2026-11-01

- Parent workflow remains `run_5b4b0mwc3jj4qsy8ccbd6xtg51`; no new design
  composition, interview allowance, or delivery campaign was started.
- Review helper invocation:
  `run_5b4b0mwc3jj4qsy8ccbd6xtg51-requirements-api-refresh`.
- Existing trail: `temp/reviews/requirements`, round 2. Round 1 is preserved.
- Result: clean, zero findings. Current-agent review, not independent or DBB.
- Exact target SHA256:
  `08f17ec6127b5dd3b311f271c0f3e275aa5e0552c7387ea2daf5d8f75a32fa1b`.
- Target manifest:
  `4da92d85fe4c6cf3dfc3dac43089d966ef284533655bb7926a82b8b265a80dcf`.
- Immutable report: `temp/reviews/requirements/rounds/round-02.md`, SHA256
  `56ed519dd4230f2ad9e91ca567948b496e3d87bfcb39bffc3e94f29ec56d8a7e`.
- Helper validated the clean predicate and durable closeout, issued the current
  requirements sidecar, and released active review ownership. No manual stamp
  edit or product modification occurred.
- Read-only structural check: 14 sequential requirements, 25 acceptance criteria,
  four resolving local links, no competing plan identity or slice inventory.
- Next gate: owner acceptance of the exact requirements revision. HLD review and
  a possible later explicitly selected security challenge are not yet complete.

## Bounded requirements-phase synthesis

Trusted application code, caller selections, and a surrounding authorization
context establish the policy before initialization. Restricted plugin discovery
checks permission before importing external code. Authorized search-path plugins
can declare trusted sources; ordinary composed config can only request sources
that already have permission. Filesystem and package config operations apply
their own source-root containment checks. Logging and instantiation use the
separate execution grants, including local call-specific grants.

Worker bootstrap receives policy before rebuilding singleton/plugin state.
Initialization contexts restore prior Hydra-owned registry visibility and
permissions, including on failure. Denials precede the protected import/read;
an unsafe source grant does not imply permission in another category or an
unstated containment bypass. Authorized Python's effects are not rolled back.

This is a synthesis of accepted requirements, not an approved architecture.
The finite engineering investigations are retained in research; no additional
architectural mechanism or owner approval is claimed here.

The accepted discussion expanded the initial import-only proposal to all sources,
plugin lifecycle/worker policy, and basic package/filesystem containment. No
further scope is added now. The architecture should reuse one policy foundation,
existing initialization/search paths, and entry-point metadata; it must not add
an organization bootstrap subsystem or filesystem sandbox. Shared plugin
registry lifetime is the principal integration risk to resolve in the HLD.

## Repository baseline

The shared Sapling checkout was clean, including no reported untracked work,
before design authoring. Its current commit was
`0f3c68503317a2caaa99e6ebd334a76622bd5bee` ("Block asyncio targets on the legacy
path (#3585)"). This is an observed authoring baseline, not a claim that it is
the latest remote revision or a selected implementation-delivery baseline.

New design files remain local and uncommitted. No accepted-document baseline,
delivery-sidecar setup, or growth-policy readiness is claimed.

## Requirements round proposal

Use the planning conversation already held. The approved summary proposed zero
additional interview questions for this round. No further questioning is needed
before the requirements review; unsolicited owner discussion is retained as
requirements evidence, not reconstructed as a new interview round.
The phase approval must cover the exact presented requirements summary. A new
material owner question requires explicit disposition and, if a new interview
round is needed, a separately agreed finite allowance.

The named agenda is source authority, framework and Compose usability, the
caller-controlled unsafe option, and migration behavior. Exact CLI names, policy
matching, activation mechanics, and delivery sequencing remain engineering work
for the HLD and implementation plan, subject to their later approval gates.

Questioning is closed for this round. No further interview question is scheduled.
This does not establish architecture or implementation readiness. API names, source/plugin identity
matching, per-category field representation, and registry/worker mechanics are
engineering design work. Other rollout releases and any additional unsafe
capability remain owner decisions at the relevant later design gate; no new
permission or bypass is inferred to close the interview. Organization-specific
bootstrap and concurrent-filesystem-tampering protection remain out of scope.

## Retained decisions and proposals

- Users may provide uninstalled source trees through `PYTHONPATH`; a package
  installation or editable install must not be required.
- Frameworks must support users choosing config locations at runtime even when
  the framework owns `hydra.main()`.
- Source permission is distinct from execution permission for instantiated
  targets and Hydra-configured logging.
- One authorization object should carry all three permission categories, with one
  context mechanism and independent grants. Possible `execution_whitelist()`
  deprecation, final names, and argument migration need HLD decisions; no
  execution-whitelist deprecation/removal release has been selected.
- In the restricted design, config content and `compose(overrides=...)` cannot
  grant permission for their own additional sources.
- The Python caller may explicitly use
  `compose(..., unsafe_allow_undeclared_config_sources=True)`. The option is
  false by default, affects only that composition, and does not disable target
  execution authorization.
- Diagnostics should link to a web page explaining source and execution
  authorization, with both CLI and Python migration examples.
- The previously discussed repeatable `--config-source` spelling and staged
  rollout are proposals, not existing Hydra behavior or approved release plans.
- The owner decided all config sources require authorization, including
  filesystem and custom sources. This replaces the initial import-only proposal.
  Trusted declarations count as grants; selecting configs within a source does
  not require separate permission.
- Automatic plugin discovery can execute unselected namespace modules from an
  uninstalled source directory before primary composition. The investigation and
  harmless probe results are retained in [research](research.md). Plugin
  authorization is now part of the shared-policy design in R11-R14. PR boundaries
  remain undecided. No runtime behavior has been changed.

The owner approved automatic source grants for programmatic additions by an
authorized SearchPathPlugin. R1 and AC16 preserve the existing platform activation
mechanism and distinguish its declarations from ordinary composed YAML.
All-source authorization is recorded as accepted scope. After putting the
containment rollout discussion on hold and reviewing the existing immediate
Defaults List errors, the owner chose an immediate containment breaking change
in Hydra 1.4 and accepted package-resource containment, including archives. R10
records those decisions. The source/plugin authorization rollout and containment
unsafe-option interaction remain separate decisions. No plugin implementation
or new review campaign is authorized.

## Approval and review evidence

### Detailed-plan review inputs

Target: `implementation-plan.md`, SHA256
`f863970a28714dd6508427bf1661ec0088f95300fbf1c3a85637d9d98d3cf291`.
Target manifest: `dfd344e3e95034f1a9aa12eadf8de88d34b87a5e6aa6313a2701dac48b2d67c9`.
Both approved requirements and HLD are explicit baseline authorities and design
dependencies. Baseline manifest:
`909eca43a15ad4af03c4e0888867b5ea485e93cafd03a8f84e85b3c46dec8b11`.
Helper run: `run_5b4b0mwc3jj4qsy8ccbd6xtg51-plan-f01-f06`.
Trail: `/home/omry/dev/hydra/temp/reviews/implementation-plan`.
Authority/input root:
`/home/omry/.local/state/awd/swe-review-authority/runs/run_5b4b0mwc3jj4qsy8ccbd6xtg51-plan-f01-f06`.
The helper classifies both upstream authorities as reviewed-current. Closeout is
durable/path, security selection default, first round of the existing ten-round
limit. Standardized target metadata is explicitly pinned with --plan-document.
The helper produced [the version-5 plan sidecar](../.review/implementation-plan.md),
binding the plan identity, exact bytes and both upstream dependencies. Round 1
completed clean with zero findings, fixes or standing decisions. Immutable report:
`temp/reviews/implementation-plan/rounds/round-01.md`, SHA256
`a1fedae08af42a1a119b6a241e31e3a5a6398bbb778471134d3a5cbadb7751ae`.
This was current-agent review, not an independent worker or DBB pass. Retained
probes establish selected standard-library foundations only; product tests,
Windows execution, benchmarks and supported-version runs have not been performed.
The sole plan key is `config-source-authorization`, convention `hierarchical-v1`.
The pinned combined function's single-file arguments are overridden by the
owner's separate-document requirements. Research/probes/process are context,
not competing normative baselines. No new delivery campaign is opened.

### HLD review inputs

The separate HLD review uses the owner's layout override: target
`high-level-design.md`, baseline and sole explicit design dependency
`requirements.md`. The combined function's single-file bindings are not used
as permission to overwrite requirements or omit their baseline role.
Target SHA256: `d1bb0bd672fc26cc83012c352fc2e2868354e8160eb98649f623f292b88e189c`.
Target manifest: `8a66349068a9a3bb1f79bc71b40c7bb1fb0a20d4dd26a47198dce1adfa0015dc`.
Baseline manifest: `46717b67390222db5981e4cf0fac80ac639b58bbd6e57e46a69cddffdd5ec1bb`.
Helper run: `run_5b4b0mwc3jj4qsy8ccbd6xtg51-hld-f01-f04`.
Trail: `/home/omry/dev/hydra/temp/reviews/high-level-design`.
External input/authority root:
`/home/omry/.local/state/awd/swe-review-authority/runs/run_5b4b0mwc3jj4qsy8ccbd6xtg51-hld-f01-f04`.
The helper confirmed the requirements authority as reviewed-current. Review is
durable/path, security selection default, one round used from the existing ten-round
limit. The helper produced [the HLD sidecar](../.review/high-level-design.md),
binding the final HLD and requirements dependency. Round 1 completed clean with
zero findings, fixes, standing rejected/deferred decisions, or runtime probes.
Immutable report: `temp/reviews/high-level-design/rounds/round-01.md`, SHA256
`d1e7823df05f96bfe162f60afd42fc9f32e189fb2cabd35a333935c400ff6f52`.
This was current-agent review, not an independent worker or DBB review.
Operational instructions and research remain context, not competing baselines.

### Requirements approval and completed review

After reading the linked documents and the shorter inline overview, the owner
said: "go ahead. all good." This approves the consolidated requirements scope
and the proposed zero-additional-question round, and hands execution back for
formal requirements review followed by HLD authoring if that review is clean.
It does not approve a future HLD, implementation plan, implementation, or commit.

Approved requirements SHA256:
`d8d3d7f1772d35329bb76a836a1f06595947bb5bc4f838ec38c2f6d3336c471d`.
Approved summary SHA256:
`8c98e414f84dc04a5d3472549e80158a335b4fdedc3f39e91006286348339136`.
The named agenda is all-source and plugin authorization, framework/Compose use,
platform declarations, local execution grants, lifecycle/worker propagation,
namespace migration, and basic containment with immediate 1.4 errors.

The current-agent formal requirements review completed clean, with zero findings,
on the unchanged approved bytes. It was not an independent worker or DBB review.
The helper finalized round 1 and issued the durable
[requirements sidecar](../.review/requirements.md). The immutable report is
`temp/reviews/requirements/rounds/round-01.md`, SHA256
`953e8edbeb4c21c5837f5d74dc50838f43f5c3b5019ac37298f36c54ac19b913`.
Trusted authority records remain in their existing external storage. No fixes,
standing rejected/deferred decisions, runtime tests, commits, or publication
occurred. HLD approval was subsequently recorded above; final-plan approval remains pending.

Structural checks cover fourteen requirement groups, twenty-five acceptance
criteria, the current file inventory and local links. All seventeen design/support
and helper-owned sidecar files are untracked; no tracked product files changed.
These checks are not independent review, runtime validation, or a committed
delivery baseline.

See [process constraints](process.md) and [research](research.md).
