# HLD API discussion

2026-11-03: the shared unsafe constant and `allowed_search_path_entries` name
are accepted. The specifications incorporate these API corrections; affected
reviews and final approvals are complete. The final sections record the decisions.
Earlier approvals retain their exact historical scope.

The owner subsequently approved the final requirements, HLD and plan and
authorized the committed design checkpoint and delivery. See
[current status](status.md) for the active work.

## Historical interview and approval record

The entries below describe the state at each interview or review checkpoint.
Statements about pending approval, an uncommitted draft or unstarted delivery
apply to that checkpoint only; they do not describe the current delivery state.

Status: public-API discussion completed; individual decisions below are accepted.
The HLD and matching requirements have been consolidated for renewed review.
The corrected requirements review is clean in round 4 and owner-accepted. The
refreshed general HLD review is clean in round 2. The explicitly approved DBB
challenge and combined round 3 are now also clean. The owner then approved the
revised HLD with "Go ahead." The detailed plan has been refreshed against the
accepted requirements/HLD; its renewed current-agent review is clean in round 2.
Final owner approval of the detailed plan remains pending.
The record below preserves the sequence, including proposals later superseded.
The earlier "hld sounds ok" accepted the architecture summary. The owner later
clarified that the actual API and user-facing behavior had not been clearly
presented for approval. Preserve that history without treating it as API acceptance.

The owner now requested: "lets have the discussion now."
Continue at the existing retained design correction/approval checkpoint
`f01-s33-block-the-responsible-final-lld-approval`. Do not start implementation,
reset the requirements interview or consumed review rounds, or change trusted
stamps to imply renewed approval. No new runtime interview allowance is claimed.

Start with category defaults and enforcement. Subsequent topics can address
source/plugin selectors, use at initialization and local contexts, reset/unsafe
behavior, and CLI/migration/namespace discovery. Discuss one decision at a time;
retain actual owner answers before updating normative specifications.

## Accepted: execution_whitelist naming

Use `execution_whitelist` for the shared API's execution field. It covers both
instantiation and Hydra-configured logging. The owner rejected the proposed
`execution_targets` wording, explained that the terminology had already moved
away from targets, and confirmed keeping `execution_whitelist` with "yes".
Future API proposals use the agreed spelling. This naming approval does not
accept the list-enforcement model, remove mode, or settle reset/unsafe behavior.

## Accepted direction: explicit LEGACY marker

The owner requested `LEGACY` for current legacy behavior. In 1.4, legacy is the
default and emits a deprecation warning. The owner asked whether 1.5 should
default to empty lists; that transition is under discussion, not yet recorded
as a settled release decision. Omitted nested fields must continue to inherit;
version defaults concern the outermost policy rather than silently relaxing an
existing enclosing whitelist. Whether explicit LEGACY remains available in 1.5
is a separate open question, including consistency with the previously planned
removal of legacy execution behavior.

The agent clarified that mode was a proposed compatibility/restricted parameter,
not an existing Hydra parameter. An explicit LEGACY value would make that
separate parameter unnecessary. No normative document was changed by discussion.

## Open: unauthorized plugin discovery and diagnostics

The owner requested explicit user-visible behavior for unauthorized namespace
and entry-point plugins. Proposed behavior: skip unselected external imports,
do not abort merely because a plugin is installed, and explain refusals when a
plugin or its configuration is requested. Entry-point metadata can be listed
without importing the plugin; a legacy namespace scan cannot safely supply an
equivalent complete class inventory without importing packages.

Concrete inspected case: Joblib's launcher module imports its config module,
whose ConfigStore registration provides hydra/launcher=joblib. Skipping that import
can therefore fail at config lookup before Hydra sees a launcher class target.
Diagnostics must account for that earlier failure. Metadata does not generally
map every plugin to the config names it would register, so do not claim certainty
that a skipped plugin caused a missing option. Show relevant discovery status and
authorization guidance without importing the plugin to find out.

These plugin UX recommendations remain proposals. The original per-category
proposal below is retained as discussion history; it does not override LEGACY.

## Earlier proposal: list arguments activate their category's checks

Propose using the existing execution-whitelist model for all three categories:
an explicit list establishes that category's whitelist, an empty list adds no
allowed entries, and None/omission inherits that category. Existing trusted
declarations and inherited grants still apply under the eventual combination
rules. With no inherited policy, 1.4 compatibility remains for omitted categories.
This is a proposal, not an accepted default or a release decision.

That would remove the separate mode parameter. A caller controls only the
categories it supplies, so execution-only use does not change source/plugin
behavior. The tradeoff is that callers must supply each category they intend
to restrict; the presence of the shared object alone does not restrict all three.

Ask the owner whether to use this per-category model or retain a separate
source/plugin mode switch. Reset, opt-out and namespace details are not silently
decided by this proposal. No normative document or review sidecar changed yet.

## Accepted: hydra.main config_search_path declaration

The owner accepted the proposed `hydra.main(config_search_path=...)` argument
with "seems ok". It accepts a sequence of source URIs, adds those sources in
their listed order, and authorizes them. No duplicate YAML search-path entry or
separate authorization grant is required. This provides the multi-source
counterpart to `initialize_config_search_path()`.

`config_path` retains its existing primary-source role. `config_search_path`
supplies additional sources. The authorization object's `config_sources` field
continues to grant permission without adding sources, for cases where YAML
selects a source later. Declaring a source through trusted Python or an explicit
CLI source-selection option should be the common one-step path.

Example accepted for the API discussion:

```python
@hydra.main(
    config_path="conf",
    config_name="train",
    config_search_path=["pkg://shared.conf", "file:///work/configs"],
)
def app(cfg):
    ...
```

This accepts the argument and its add-and-authorize behavior. It does not approve
the complete HLD or implementation plan. Exact placement relative to other
additional sources, URI/path-resolution details, and CLI interactions must be
made explicit in the refreshed HLD. No product implementation, normative
specification, or trusted review record was changed by this discussion entry.

## Accepted: unified initialize declaration and initializer deprecation

The owner accepted adding `config_search_path` to `hydra.initialize()` alongside
its optional `config_path`. The primary source and additional source declarations
have the same roles as in the accepted `hydra.main()` proposal. Explicitly
declared sources are both added and authorized; no duplicate YAML declaration
or separate permission grant is required.

Both forms are supported by the proposed unified interface:

```python
with hydra.initialize(config_search_path=["pkg://shared.conf"]):
    cfg = hydra.compose(config_name="train")

with hydra.initialize(
    config_path="conf",
    config_search_path=["pkg://shared.conf"],
):
    cfg = hydra.compose(config_name="train")
```

The owner explicitly chose to deprecate the new
`initialize_config_search_path()` API. Retain it as a compatibility adapter to
`initialize()` with a deprecation warning and migration guidance. Preserve its
existing ordered-source and caller-relative URI behavior through the adapter.
The warning text and removal release remain to be specified; no removal date
was approved. No additional source-declaration argument for `compose()` has
been approved; it uses the initialized search path.

This records the owner's API decision. Product implementation, normative
specification updates, and renewed reviews remain pending.

## Accepted: additive nesting and per-category replace marker

The owner confirmed that nested authorization adds grants by default, matching
the existing execution-whitelist behavior. An outer source grant A and an inner
source grant B make A and B available inside the inner scope. Exiting that scope
restores the outer policy.

The owner proposed and approved a per-field `replace(...)` marker instead of
the earlier shared API's separate `reset` category list. It replaces inherited
grants for only the marked category. Other categories retain their normal
inheritance and additive behavior. Use the accepted `execution_whitelist` field
name, including when applying the marker:

```python
policy = hydra.authorization(
    config_sources=["pkg://app.conf"],
    plugins=[],
    execution_whitelist=replace(["app.Model"]),
)
```

Here, the source list adds a grant, `plugins=[]` adds no grants and retains
inherited plugin grants, and the execution list replaces inherited execution
grants with `app.Model`. `replace([])` clears inherited grants for its category.
Context exit restores the outer policy. Documentation must state the difference
between an empty additive list and an empty replacement list explicitly.

This replaces the separate-reset proposal for the new shared API; it does not
remove the existing execution API's compatibility surface. The marker's public
import location, its interaction with LEGACY and unsafe values, and the existing
execution adapters remain to be finalized. Replacing grant lists does not
silently decide whether initialization declarations can be revoked or undo
imports already performed. No product code or trusted review record was changed.

## Accepted: regular authorization module API

The owner approved a regular `hydra.authorization` module exposing
`AuthorizationPolicy`, `replace`, and `LEGACY`. Use the constructor directly;
do not also provide a callable `hydra.authorization(...)` factory. This
supersedes the factory spelling in earlier examples in this discussion.

```python
from hydra.authorization import AuthorizationPolicy, LEGACY, replace

policy = AuthorizationPolicy(
    config_sources=["pkg://app.conf"],
    execution_whitelist=replace(["app.Model"]),
)
```

Qualified module access, including `hydra.authorization.replace(...)`, is also
supported through normal Python module imports. The accepted per-category
inheritance and replacement semantics are unchanged. The marker's import
location is now settled; its LEGACY/unsafe interactions and compatibility with
existing execution arguments still need explicit decisions.

The owner clarified the policy's purpose as authorizing things that are not
explicitly "activated", correcting the earlier phrase "opted into". For config
sources, explicit trusted declarations through `config_path` or
`config_search_path` already add and authorize the source. A policy source grant
supplies additional permission for a source configuration may select later; the
grant alone does not add it to the search path. This does not introduce a general
rule that arbitrary configuration selections authorize themselves or that every
Python API call grants permissions. No product code, normative specification,
or trusted review record was changed.

## Accepted: explicit CLI source selection activates and authorizes

The owner explicitly extended and approved the activation rule for command-line
flags. Dedicated source-selection flags, including the existing `--config-path`
and `--config-dir` and the proposed additional-source flag, both activate and
authorize the sources they select. No duplicate YAML declaration or separate
policy grant is required. The new flag's exact spelling remains to be settled.

The initial agent interpretation excluded command-line `hydra.searchpath`
overrides. The owner corrected and approved the distinction below. Do not retain
that exclusion as an accepted requirement.

## Accepted: direct CLI hydra.searchpath selection also authorizes

An actual command-line `hydra.searchpath=[...]` override activates and authorizes
its selected sources, like dedicated source-selection flags. The owner approved
this with "yes". YAML search-path declarations and `compose(overrides=...)`
were distinguished in that discussion: Compose overrides initially remained
source requests, not authorization. The owner subsequently requested equal
Compose authority, as recorded below; that newer direction supersedes this
Compose exclusion. YAML itself still cannot grant authority.

Read-only feasibility inspection confirms separate entry points: `_run_hydra()`
receives parsed command-line arguments; `compose()` calls `compose_config()`
with `from_shell=False`. `_process_config_searchpath()` already identifies
search-path overrides before `repo.initialize_sources()`, but currently has no
trusted CLI-origin input. Its provider label "in command-line" also applies to
Compose overrides today and must not be used as evidence of authority.

Do not promote the existing `from_shell` diagnostic flag into an authorization
credential. It defaults to true on internal paths and is also true during sweep
recomposition. Capture trusted source grants at explicit invocation boundaries
and carry them in trusted policy/bootstrap state, keeping them distinct from
YAML and persisted rerun inputs. Alias expansion and interpolation
must preserve that distinction; exact behavior for configuration-derived source
values still needs to be presented during the API discussion. This is a source
inspection result, not implemented or runtime-tested authorization behavior.

This records accepted behavior and feasibility evidence without changing product
code, normative specifications, or trusted review records.

## Accepted: Compose overrides have CLI-equivalent authority

The owner requested that the `compose(overrides=...)` parameter have the same
authority as command-line overrides, then explicitly requested challenge and
suggested a later security review. After challenge, the owner explicitly
disposed the input-forwarding concern as the trusted caller's responsibility:
"its a concern but this is the trusted code's fault." This accepts the API trust
contract; it is not an already-reviewed security conclusion.

Under this direction, an explicit `hydra.searchpath=[...]` selection supplied
through Compose overrides both activates and authorizes its sources for that
call. No separate copy of the source list in AuthorizationPolicy is required.
This supersedes the earlier CLI-versus-Compose distinction. It also removes the
duplication used to motivate the agent's additional per-Compose
`config_search_path` proposal; that proposal was not approved. This source rule
does not automatically whitelist execution or authorize plugins selected by
ordinary config overrides. YAML still cannot grant itself source authority.

The accepted trust contract: an application forwarding external override strings
to Compose passes source-selection authority, not merely configuration data.
The trusted caller must decide which input to pass. Trusted Python can also
start another Hydra process with equivalent command-line overrides; Compose is
not a boundary for containing that code. Document this responsibility rather
than adding a special Compose restriction or another API to compensate for
unvalidated forwarding. Do not claim a Hydra exploit from a hypothetical
integration that violates this caller responsibility. A later review should
evaluate implementation against this explicit contract.

Also review whether configuration-controlled aliases or interpolations can
turn an apparently explicit invocation selection into a YAML-controlled grant,
and preserve call scoping and trusted worker propagation. These cases remain
unsettled. The owner said "maybe a tbb review later"; no reviewer was launched
and no reviewed outcome is claimed. Product code, normative specifications,
and trusted review records remain unchanged.

## Accepted: Hydra 1.5 empty defaults

The owner approved empty default grant lists for config sources, plugins, and
execution in Hydra 1.5 with "yes". Explicit declarations and trusted
source-selection overrides still activate and authorize their selected sources;
Hydra's built-in components remain available. These are outermost defaults:
omitted or None fields within an existing scope continue to inherit, and empty
additive lists do not erase inherited grants. Use `replace([])` when replacing
inherited grants with an empty list is intended.

This settles the 1.5 defaults question raised earlier in this discussion. It does
not decide whether explicit LEGACY values remain accepted in 1.5, change the
existing unsafe execution opt-out, or approve a removal release for deprecated
initializer adapters. No product code, normative specification, or trusted
review record was changed.

## Accepted: reject explicit LEGACY in Hydra 1.5

The owner approved making explicit LEGACY values an error in Hydra 1.5 for
config sources and plugins, matching the previously planned removal of legacy
execution mode. Empty defaults and removal of explicit legacy compatibility
are now both accepted for 1.5. This resolves the open question retained in the
earlier defaults discussion; LEGACY remains the deprecated 1.4 behavior.

This decision does not remove or extend the separately specified unsafe
opt-outs. Error wording and migration guidance must identify the required
explicit declarations or grants. No product code, normative specification,
or trusted review record was changed.

## Accepted: reuse existing CLI source selection

The owner approved dropping the proposed `--config-source` flag. Existing
source-selection flags (`--config-path`, `--config-dir`) and explicit
`hydra.searchpath=[...]` overrides already activate and authorize sources.
Do not introduce a second flag for the same purpose. This supersedes earlier
`--config-source` examples and references to a new additional-source flag in
this discussion and the provisional HLD/plan. It does not decide the spelling
or behavior of a plugin-authorization flag. No product code, normative
specification, or trusted review record was changed.

## Accepted: plugin selectors and CLI list forms

The agent proposed repeatable `--authorize-plugin module:Class`. The owner
questioned using an import selector instead of an entry-point name and explicitly
requested accepting comma-separated values. Record comma-separated CLI values
as required; this does not itself settle selector resolution or the flag name.

The owner accepted using `hydra.plugins` entry-point names as the normal
selector, resolving installed metadata before importing any selected code.
For example, `--authorize-plugin joblib,colorlog` would select those entry
points. Reject an ambiguous name before importing rather than choose an
arbitrary provider. Retain explicit `module:Class` selections for plugins with
no entry point, consistent with the existing uninstalled/namespace-plugin use
case. Apply the same selector vocabulary to `AuthorizationPolicy.plugins` so
the CLI and Python interfaces do not require different identifiers.

The owner approved the presented selector rules with "yes", including ambiguity
errors, explicit `module:Class` support, and the same selectors in Python and
the CLI. Both comma-separated values and repeatable `--authorize-plugin`
occurrences are accepted. These two examples have the same meaning:

```text
--authorize-plugin joblib,colorlog
--authorize-plugin joblib --authorize-plugin colorlog
```

The corresponding Python grant is
`AuthorizationPolicy(plugins=["joblib", "colorlog"])`. No product
implementation, normative specification, or trusted review record was changed.

## Accepted: same-call policy and execution argument are incompatible

The owner rejected the agent's proposal to merge an explicit `authorization=`
policy and the existing `execution_whitelist=` argument on the same call:
"incompatible. just raise an error. if they bothered to add policy they can be
bothered to consolidate." Require the caller to put those execution grants in
`AuthorizationPolicy.execution_whitelist`. Do not define same-call merge
precedence. Diagnose the invalid combination before imports or other
initialization side effects. This supersedes the provisional HLD's proposal to
apply the policy first and then the existing execution argument.

Existing calls using only the old execution argument remain supported. This
decision concerns two explicit arguments on one call; it does not forbid a
surrounding authorization context, nested existing execution-whitelist contexts,
or local `_execution_whitelist_` arguments to instantiate. Those retain the
agreed inheritance and local-scope requirements. How explicit None is detected
and whether it counts as supplying the old argument still needs to be specified;
do not treat a defaulted old parameter as a conflict with every new policy use.
No product code, normative specification, or trusted review record was changed.

## Owner clarification: all configuration forms carry no authority

During the resumed requirements approval, the owner challenged the shorthand
"YAML cannot authorize". Dataclass configs are also configuration and both forms
are transformed to DictConfig. The owner accepted the corrected boundary:
configuration cannot authorize additional sources or plugins regardless of its
representation. Loading or importing a config source must not itself confer
authority to expand Hydra's policy. Explicit trusted caller declarations, CLI
selections and Compose arguments are the grant-making boundaries already agreed.

The owner explicitly confirmed: "this is not a real sandbox". Keep the promise
at Hydra's authorization boundaries; do not turn it into an attempt to contain
arbitrary Python execution or establish trust based on YAML versus Python file
format. ConfigStore data registration is distinct from a permission grant.
The earlier agent statement that imported Python can explicitly grant authority
did not make that distinction adequately and must not be used as permission for
configuration to elevate itself through Hydra.

This clarification is recorded for the requirements/HLD wording refresh. The
round-2 requirements review remains evidence for its exact existing bytes, not
approval of a not-yet-written correction. No product code or review stamp was
changed, and no claim of runtime enforcement is made.

## Accepted: YAML-defined aliases do not grant source authority

The owner accepted this concrete example and disposition:

```yaml
hydra:
  aliases:
    fast: "hydra.searchpath=[pkg://extra.conf]"
```

Running `python app.py fast` expands the alias to a source-selection override,
but the actual source URI comes from YAML. The alias may request that source;
it requires an existing grant. In contrast, an explicit invocation override
`hydra.searchpath=[pkg://extra.conf]` activates and authorizes the source.
Apply the same origin rule to Compose overrides. Do not automatically promote
configuration-authored expansions into invocation authority.

This is an accepted design rule, not a claim of an existing exploit or runtime
enforcement. Alias syntax and literal expansion were checked in the current
source. Interpolated source values must follow the same no-self-authorization
boundary; do not add interpolation support where the existing API lacks it.
Product code, normative specifications, and trusted review records are unchanged.

## Accepted: explicit lists enable checks under inherited LEGACY

The owner approved an explicit grant list enabling authorization checks for
its category when the outer policy uses LEGACY. The concrete reviewed example
was an outer `AuthorizationPolicy(config_sources=LEGACY)` and an inner
`AuthorizationPolicy(config_sources=["pkg://app.conf"])`. In the inner scope,
configuration-requested sources need grants; `app.conf` has one. Other sources
need an additional grant or an explicit trusted declaration. Context exit
restores the outer legacy behavior. Empty lists likewise select checking with
no additional grants, preserving explicit declarations and Hydra's own sources.

This allows opting into checks using a list while 1.4 still defaults to LEGACY.
It does not change additive combination between two explicit lists or settle
inheritance of the separate execution unsafe sentinel. The agent previously
bundled those as one question; the owner required them to be discussed one at
a time. No product code, normative specification, or trusted review record was
changed.

## Settled: unsafe execution nesting follows additive/replace semantics

The owner clarified that this is already covered by the accepted general rule:
"this behves like normal whitelists. normal additive, unless replace". An inner
ordinary execution list adds permissions and does not cancel an inherited
UNSAFE_DISABLE_EXECUTION_CHECKS value. An inner `replace([...])` replaces that
inherited execution value and enables the corresponding checked list. Context
exit restores the outer policy. No additional unsafe-nesting mechanism is needed.

The existing execution-whitelist context already preserves the unsafe sentinel
during additive combination and uses `reset=True` for replacement. The new
marker supplies the shared API's replacement operation. This settles the
unsafe-inheritance question retained above. No product code, normative
specification, or trusted review record was changed.

## Accepted: source precedence

The owner accepted the final remaining decision: initialize the source list with
the primary `config_path`, when present, followed by `config_search_path` entries
in their listed order. Lookup uses the first match. Additional declarations are
fallbacks to the application's primary source. SearchPathPlugins retain their
existing ability to adjust the search path; CLI additions keep their existing
positions. Do not change those hooks or CLI ordering as part of this rule.

For example, `config_path="conf"` and
`config_search_path=["pkg://shared.conf", "file:///fallback"]` establish the
application-source order `conf`, `shared.conf`, `/fallback` before plugin
adjustments. This reuses the current ordered-source initialization foundation
and preserves the deprecated initializer's list behavior through its adapter.

The owner requested progress labels in X/TOTAL form; this was presented as
3/3 from the remaining-decision list. The three topics (indirect source
selections, nested legacy/unsafe behavior, source precedence) are now settled.
The nested behavior topic required separate questions at the owner's request;
do not describe those as one combined approval.

The public API discussion is complete enough to refresh the specifications and
present the consolidated HLD for owner review. These individual decisions do
not constitute approval of that not-yet-refreshed HLD or implementation plan.
No product code, normative specification, or trusted review record was changed.

## Required: authorization API is blocked from instantiate

The owner explicitly required blocking the authorization API from instantiate.
R8, AC13 and the HLD now state the non-whitelistable boundary for the public
authorization namespace and canonical implementation identities, including
policy construction, context/mutation entry points, helpers and resolved aliases.
Ordinary exact or wildcard grants cannot authorize those policy controls.
The existing explicit unsafe execution opt-out remains separate; its promise
of disabling checks was not changed by this requirement.

The refreshed requirements review is clean in round 4 for the new exact bytes;
the sidecar was issued by the helper. This is a requirements-level result, not
runtime verification or a new implementation. No product code was changed.

## Owner acceptance: corrected requirements

After the authorization-API instantiate restriction was added and the refreshed
requirements review was reported clean, the owner replied "ok. whats next?".
In that context this accepts the updated requirements and authorizes the next
design phase, HLD review. The agent stated this interpretation before starting
that review. The accepted requirements SHA256 is
`2052ba2d84fc04b98c5485b1561dcab752840b1e3f0e131908233566b98241e7`.
The document had completed clean current-agent review in round 4. This acceptance
does not approve the revised HLD, detailed plan, commit or implementation.

## Owner acceptance: HLD after DBB challenge

After the clean combined general/DBB review, the owner asked for next steps.
The agent stated that HLD approval comes next, followed by detailed-plan refresh,
review and final plan approval, with commits and implementation separate. The
owner replied "Go ahead." This approves the reviewed HLD and authorizes detailed
plan authoring/review. Accepted HLD SHA256:
`4aac3ec633f26ff49327e0374f5fdbb96a592815011e90a62d1ee5c2dfa03a48`.
Its accepted requirements dependency remains
`2052ba2d84fc04b98c5485b1561dcab752840b1e3f0e131908233566b98241e7`.
The detailed plan, commit, delivery campaign and product implementation remain
unapproved.

## Accepted correction: shared authorization opt-out

During review of the public issue draft, the owner questioned the separate
unsafe-source argument and asked about other confusing API interactions.
The owner confirmed that the lack of a plugin opt-out was not intentional and
requested one shared constant. After rejecting the vague name UNSAFE and
discussing one versus several constants, the owner accepted the proposal with
"ok".

Use `UNSAFE_DISABLE_AUTHORIZATION_CHECKS` as the shared opt-out value in each
permission category. The receiving policy field scopes its effect. It remains
available in 1.4 and 1.5. Preserve `UNSAFE_DISABLE_EXECUTION_CHECKS` as a
compatibility alias. Additive lists preserve an inherited unsafe value;
`replace([...])` enables checking again. Source containment and plugin discovery
settings retain their independent effect.

The proposed API correction moves source opt-out into the policy and removes the
parallel main/Compose unsafe-source argument. The owner also agreed that Compose
must report plugin changes requiring new discovery as an error, with guidance to
authorize during initialization. The error-versus-warning discussion retained
errors under checked source policy: 1.4 default LEGACY warns/continues, explicit
source grants enable checks, and 1.5 enables checking by default.

Renaming `config_sources` to `allowed_config_sources` was proposed but has not
been accepted. Do not treat approval of the shared constant as approval of that
rename. Requirements/HLD/plan updates and their affected reviews remain pending;
this decision record changes no product code or trusted stamp.

## Accepted correction: authorize search-path entries

The initial `allowed_config_sources` proposal was clearer about permission, but
the owner corrected the terminology: `pkg://foo.bar` identifies a config
search-path entry, rather than a ConfigSource plugin. The agent proposed
`allowed_search_path_entries`; the owner replied "better".

Use `allowed_search_path_entries` for the policy field. It permits config-requested
location entries. Keep `config_search_path` on main/initialize for selecting and
authorizing entries. No behavior change to selection/grants is implied by the
rename, and no compatibility alias is needed for either unimplemented earlier
policy-field name.

The revised requirements, HLD, engineering plan, canonical slice acceptance and
overview now incorporate this name, the shared opt-out and Compose's discovery
error. Slice IDs, dependencies, owned paths, statuses and line estimates are
unchanged. Existing stamps attest earlier exact documents; no fresh review or
approval of the corrected document set is claimed. No issue was posted and no
product implementation started.

## Authorized: post the issue and refresh affected reviews

The owner approved posting the prepared issue, pinning its number in the existing
news paths and continuing delivery preparation. The issue was posted as
[#3606](https://github.com/hydra-ecosystem/hydra/issues/3606), then read back through
`gh`. The nine slice IDs, dependencies, behavior and estimates remain unchanged;
only the approved news ownership paths were added. Requirements round 5 is clean
for the corrected exact bytes. HLD round 4 is under fresh general/DBB review.
This records authorization for the requested actions, not a new whole-document
approval or a completed delivery admission.

## Reviewed correction: initialize-family adapter

DBB found that the HLD interface table omitted authorization=None from deprecated
initialize_config_search_path(). The accepted R11/AC25 requirement already covers
that initializer. The coordinator accepted the narrow correction within that
requirement: add the parameter and explicitly forward it unchanged before
discovery. The HLD and corresponding plan detail now state this. No new public
policy decision or runtime implementation was introduced.

The same retained DBB reviewer verified the fix clean. Current HLD SHA256:
`507c52bfdf4c4f6b0d568543c016955aadfe88921457d5998cbad034f3cc7d52`.
The helper completed general/DBB durable clean closeout in round 6. The intervening
round 5 records a failed coordinator manifest selection, with no specialist
report or clean claim. Full evidence is retained in the existing review trail
and external authority area; allowances and original reports were not reset.
Whole-HLD owner approval is still pending and is not supplied by these reviews.

## Owner acceptance: consolidated API-corrected HLD

After the agent reported clean general/DBB HLD review and listed HLD approval,
refreshed plan review/approval and a committed baseline as the remaining gates,
the owner replied "approved". This accepts the consolidated HLD SHA256
`507c52bfdf4c4f6b0d568543c016955aadfe88921457d5998cbad034f3cc7d52`
and authorizes the dependent implementation-plan review. Its reviewed requirements
dependency is SHA256
`9a0bada60222ef2a95ec00d6a5086217502986581368174127ec061f31a2eabf`.
The previously accepted API decisions and design scope are unchanged.
Final plan approval and committed delivery readiness remain separate gates.

## Disposition: plan review worker and measurement findings

The agent presented the two plan-review findings and a concrete scoped patch.
The owner asked about affected launchers and plugin changes, then directed use
of the existing shared launcher suite. After that coverage was recorded, the
owner replied "ok.". The agent stated its interpretation before applying the
prepared worker-fallback and measurement-owner corrections and continuing the
same retained DBB review.

The correction requires bootstrap support when namespace scanning is explicitly
disabled, even if the grant categories are LEGACY; otherwise dispatch fails.
Slices 1/2 own the already-required bounded containment overhead observations.
Slice 8 names the existing LauncherTestSuite for common worker-policy checks.
This preserves public API signatures, slice IDs/dependencies and estimates.
It is a plan-contract correction, not an implementation or performance result.
Final whole-plan approval remains a separate gate after review verification.

## Owner acceptance: final reviewed plan and implementation start

After clean general/DBB round-5 closeout, the agent presented the final plan,
unchanged nine-slice scope and production/test totals, and asked: "Approve the
final plan so I can commit the design and start slice 1?" The owner replied "yes".
This approves plan SHA256
`d173afd90cd02c23b9bd0c176f3215ae549b5786ff0ee32cc78e42ff2a589e45`,
inventory SHA256
`59cc1c05b1b8bd3199f63dd35bdedf5fe93ede5e32ba63e6e119252ad59acdca`
and the reviewed overview SHA256
`f09d1ca40eddcd593fdf60b707be9f4c073a432e3dbe19f81c967a1abd3038a7`.
It authorizes the scoped design checkpoint and starting slice 1 under the existing
delivery workflow. Required baseline, admission, implementation validation and
review gates still apply. It does not authorize merging PRs or cutting a release.
