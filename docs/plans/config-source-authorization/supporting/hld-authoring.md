# Architecture authoring evidence

Historical evidence for the architecture before the public-API discussion.
The revised HLD incorporates the later owner decisions recorded in
[the API discussion](hld-api-discussion.md). The original proposals below are
retained as history and do not override that revised specification.

Input: [approved requirements](../requirements.md), SHA256
`d8d3d7f1772d35329bb76a836a1f06595947bb5bc4f838ec38c2f6d3336c471d`.
Output: `../high-level-design.md`, a new separate file under the owner's explicit
override. The combined workflow's requirements-file output argument does not
authorize editing accepted requirements as architecture.

## Existing primitives inspected

- `hydra/_internal/execution_policy.py`: ContextVar-based effective whitelist,
  additive combination, explicit reset, reusable policy context, unsafe sentinel.
- `hydra/main.py`, `hydra/initialize.py`, `hydra/compose.py`: decorator context
  begins before discovery; initializer constructors perform initialization;
  Compose uses an initialized Hydra. Initializer exit restores GlobalHydra only.
- `hydra/core/plugins.py`: eager singleton discovery imports the namespace,
  walks packages, then loads all entry points. Explicit registration currently
  reaches that initialization first. Registration populates SourcesRegistry.
- `hydra/core/singleton.py`, `hydra/_internal/sources_registry.py`: independent
  plugin/source-type state; worker set_state invokes discovery eagerly.
- `hydra/_internal/config_search_path_impl.py`,
  `hydra/_internal/config_repository.py`,
  `hydra/_internal/config_loader_impl.py`: mutable search-path entries carry
  provider labels, not trusted provenance; repository creates sources directly;
  primary config and CLI overrides can add paths and reinitialize the repository.
- `hydra/_internal/core_plugins/{file_config_source,importlib_resources_config_source,structured_config_source}.py`:
  filesystem realpath calls lack ancestry checks; package resources can use
  filesystem or archive Traversables; named structured sources import modules.
- `hydra/types.py`, `hydra/core/utils.py`, BasicLauncher, Joblib and Submitit:
  HydraContext already transports execution state; worker discovery currently
  precedes run_job's execution context. Setup and singleton restore ordering differ.
- `hydra/_internal/utils.py`: existing config-path/config-dir selection, argument
  parsing before Hydra creation, and ordered source initialization can be reused.

These are source-inspection facts, not runtime validation of the proposed design.
No product code, runtime probe, dependency installation, or benchmark was needed
to settle an architecture-level feasibility claim. Resource-loader coverage and
worker transport remain finite engineering investigations in the HLD.

## Choices proposed for the HLD approval gate

Keep one authorization foundation. Use exact source identities and exact plugin
module/class selectors; do not add wildcard source/plugin grants. Restricted
operation must avoid a namespace walk that imports unknown descendants. Explicit
legacy plugin selections can load their named class directly. Preserve discovery
of all legacy plugins in compatibility operation with warnings and an independent
scan-disable switch. Keep namespace-package code usable through entry points.

Retain the old execution whitelist as a thin execution-only adapter without a
deprecation warning in this feature. Add no unsafe plugin bypass; compatibility
mode provides the migration path. The specifically requested unsafe source option
never bypasses plugin checks or containment. These are proposals for the HLD
gate, not new owner-approved policy. No release/default-removal date is selected.

Compared simpler alternatives: removing all config-supplied sources breaks the
accepted framework journey; installation-only authorization excludes legitimate
source checkouts and does not authenticate code; class filtering after discovery
is too late; ContextVar-only lifecycle cleanup leaves registry authority behind;
separate policy systems duplicate combination and transport rules. No new service,
plugin authenticity database, organization bootstrap, or native sandbox is needed.

## Consolidated API revision: 2026-11-01

The owner completed the API discussion and authorized the next HLD update.
Requirements were first checked against the accepted decisions and revised only
for those decisions. The HLD was then checked against the revised requirements.
This was a current-agent consistency check, not a new formal stamped review,
an independent review, or DBB validation.

- Requirements SHA256:
  `08f17ec6127b5dd3b311f271c0f3e275aa5e0552c7387ea2daf5d8f75a32fa1b`.
- HLD SHA256:
  `c2e8ecd04eb177b9c1a472f803719e53dffa5883b6bdba8b86c09308665f6568`.

The check covered the accepted module API, per-field replacement, explicit
source declarations, equal CLI/Compose override authority, YAML-origin refusals,
entry-point-name plugin selection, argument conflicts, release defaults,
initializer deprecation, and source precedence. Existing containment, registry
restoration and worker-before-import requirements remain in the architecture.
The HLD now states diagnostic examples, including missing-config errors that
show skipped metadata without claiming which plugin would register that config.

A read-only document check resolved 23 local links and parsed seven Python code
examples with `ast.parse`; all passed. It also checked that requirements and HLD
contain neither plan_key front matter nor a competing slice inventory. Sapling
status showed only the existing untracked design directory, with no tracked
product changes. No product tests ran because this change only authors design
documents; the new API remains unimplemented.

The old helper records and sidecars were not rewritten. Observed sidecar hashes:

- Requirements: `6f336d2417f45bcc1eca8ea398711149d5a0d6d3d4fce1d5a06ad60db96b9556`.
- HLD: `268ebd838b43ec3816ec36a31a797ff00ca873f4e4003ce9a7f54c3bc89586a4`.
- Plan: `7155664232ad6eef44b8fc17c28aa1aae5fbaf983d10f5f25e07df3a0d05e1fb`.

Their old approvals and reviews do not apply to the revised document bytes.
The detailed plan received a superseded-status notice, not an engineering
refresh. The owner requested resumption tomorrow with next steps; no new
reviewer was launched, no review was stamped, and nothing was committed.

## Configuration-authority clarification: 2026-11-01

During requirements approval the owner clarified that YAML, dataclass configs
and DictConfig are all configuration, with no grant authority. The owner
confirmed the no-sandbox boundary and accepted the operational context-cleanup
and worker-ordering requirements. The requirements/HLD now generalize the
representation-specific wording and explicitly separate ConfigStore data
registration from grant expansion during Hydra-controlled config loading.

The HLD assigns a config-load scope to the existing policy/API boundaries so
loading or importing a source cannot itself authorize additional permissions.
This is planned API behavior, not runtime enforcement or containment of Python.
No product implementation or new public API was added by authoring this guard.

- Requirements SHA256:
  `b0055f81858206f95486ef7072133656ed4fbf81f92c86ec76a153a3308ac296`.
- HLD SHA256:
  `f569fc04808535869cb1041fe21c6af9ae1efdde453eaad9ab9ecbe16bd81b59`.
- Requirements round 3: clean current-agent review, zero findings, helper-validated
  durable closeout. Report SHA256:
  `223f4b4102e872d87ea517a07c1111436c659744b72ce8dd945670ba5e8b710e`.
- Structural checks passed for 14 requirements and 25 acceptance criteria;
  requirements/HLD local links and Python example syntax also passed.

Earlier exact review evidence is preserved. The requirements sidecar was updated
only by the review helper. The HLD's prior stamp is stale; its refreshed review
must use the corrected requirements after whole-document owner acceptance.
No commit, implementation, independent reviewer, DBB pass or publication occurred.

## Authorization-API instantiate restriction: 2026-11-01

The owner required explicit protection against calling authorization APIs from
instantiate. R8 and AC13 now require non-whitelistable public/canonical policy
controls and alias handling. The HLD assigns this to the existing execution
policy machinery, with focused regression coverage and normal trusted Python
use preserved. No new sandbox or separate policy engine is proposed.

- Requirements SHA256:
  `2052ba2d84fc04b98c5485b1561dcab752840b1e3f0e131908233566b98241e7`.
- HLD SHA256:
  `4aac3ec633f26ff49327e0374f5fdbb96a592815011e90a62d1ee5c2dfa03a48`.
- Requirements review round 4: clean current-agent review, zero findings.
- Immutable report SHA256:
  `ff9afad347e5151a18aa02d9b6dac920cc0a7ebb9166eb2d5b0d28406dd60ea5`.

The review helper refreshed the current requirements sidecar without changing
earlier rounds. HLD review, human document acceptance and implementation remain
separate. Structural/link/example checks passed; no runtime guard was built or
tested. The existing explicit unsafe execution opt-out remains unchanged.

## Refreshed HLD review: 2026-11-01

The owner accepted the corrected requirements with "ok. whats next?" following
the final instantiate-restriction addition and clean review. The agent stated
the interpretation before proceeding; the canonical acceptance record is in
[the decision history](hld-api-discussion.md#owner-acceptance-corrected-requirements).

The existing HLD review trail completed round 2 clean against the accepted
requirements. This was the current-agent review, not an independent or DBB pass.
No target or governing-document bytes were changed during review.

- HLD SHA256:
  `4aac3ec633f26ff49327e0374f5fdbb96a592815011e90a62d1ee5c2dfa03a48`.
- Requirements dependency SHA256:
  `2052ba2d84fc04b98c5485b1561dcab752840b1e3f0e131908233566b98241e7`.
- Report: `temp/reviews/high-level-design/rounds/round-02.md`, SHA256
  `471ddcda627a77c396585243eb07b3970f15f410f10a6e519743bbfdb18776ea`.

The helper verified the governing document as reviewed-current and issued the
HLD sidecar with that exact dependency after clean durable closeout. The original
HLD review round and requirements rounds remain unchanged. Structural link and
Python-example syntax checks passed; no runtime security or Windows validation
is claimed. Whole-HLD approval and any additional specialist challenge remain
pending. The stale detailed plan has not been refreshed; no implementation or
commit was made.

## Completed bounded DBB challenge: 2026-11-01

The owner explicitly approved the additional specialist pass. A fresh configured
native dbb agent reviewed the unchanged HLD against the accepted requirements.
No parent history, earlier findings or coordinator conclusions were supplied.
The exact native handle and launch were retained before review, under the
original private authority root. The original design invocation's selection
was not rewritten; this was a new review invocation within the existing trail
and allowance, not a new interview or delivery campaign.

- Review invocation: `run_5b4b0mwc3jj4qsy8ccbd6xtg51-hld-dbb`, HLD round 3.
- Frozen request identity:
  `627a7e8a7767d601adb56633d0487121ef4dd15337aa316fc5c1b88a2933c113`.
- Native reviewer/session handle: `/root/config_authorization_hld_dbb`.
- DBB report: `/home/omry/.local/state/awd/swe-review-authority/runs/run_5b4b0mwc3jj4qsy8ccbd6xtg51-hld-dbb/security-report-r3.json`.
- Original report SHA256:
  `24ccde2335beb798bcd2cfba6aa02eae7014e90d66860ef0945d8c85cf3afa42`.
- DBB outcome: clean, zero findings.
- General pass: separately completed after launch against the same frozen inputs,
  no additional findings; evidence in the existing trail's round-03 scratch note.
- Combined report: `temp/reviews/high-level-design/rounds/round-03.md`, SHA256
  `6b9839d0adc3316a43f110d285abe0dcb4023405d982522bfb91cf5b88f0a85c`.

The specialist and coordinator validated the original report read-only with the
helper's security_report_binding routine. The helper finalized both components,
validated clean status and issued the DBB-backed HLD sidecar with its exact
requirements dependency. Its closeout explicitly reports no incomplete security
review and no restart requirement. The report was not rewritten or substituted.

This is independent security review of an HLD, not dynamic exploit testing or an
implementation-ready proof. Explicit LLD platform/resource/worker/origin/rollback/
performance investigations remain. No target, baseline or product bytes changed;
no implementation, commit or publication occurred. Human HLD approval is the
next gate before the superseded detailed plan is refreshed.
