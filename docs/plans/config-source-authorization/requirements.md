# Config source and plugin authorization

Status: revised for the owner's accepted public-API decisions; renewed document
review and approval are pending. This document does not authorize implementation
or a release. Decisions and earlier approval history are retained in
[the API discussion](supporting/hld-api-discussion.md).

## Intended outcome

Allow applications and frameworks to control which configuration
sources Hydra may initialize during composition. A user must be able to supply
their own config locations to a framework that owns `hydra.main()`, without
editing the framework or installing a Python package.

Let trusted application, user, and platform setup also control which external
plugins Hydra imports and uses. Plugin discovery and source composition must
share the authorization lifecycle while keeping their permissions separate.

Permission must come from the application or its caller. A loaded configuration
must not grant itself permission to introduce additional config sources.
This applies to every configuration form, including YAML, dataclass configs,
and the DictConfig produced from them. Loading, importing or converting a
configuration does not give it authority to expand Hydra's policy.

## Problem and trust boundary

Hydra can load YAML from filesystem directories or Python packages, and can use
structured configs registered by Python code. Selecting `pkg://package` imports
the package, including its initializer. Selecting `structured://module` imports
that module for registration. Config-supplied `hydra.searchpath` entries currently
reach those imports through both `compose()` and `hydra.main()`.

Python code is trusted once the application or caller explicitly selects it as
a source. That code runs normally and can import dependencies or have other
effects. This feature controls Hydra's source-selection boundary; it does not
sandbox Python or prevent all behavior reachable through authorized code.
Hydra must distinguish config data registration from authorization changes at
its own APIs. Arbitrary Python execution remains outside the containment promise.
Permission identifies intended selection; it does not authenticate code resolved
through Python's import system or protect against replacement of Hydra itself.

Source authorization is separate from execution authorization for `instantiate()`
and Hydra-configured logging. Neither permission silently supplies the other.

## Scope

All config sources require authorization, including `file://`, `pkg://`,
`structured://`, and sources provided by custom plugins. Sources explicitly
declared by trusted initialization code, Hydra's built-in setup, dedicated user
selections, or authorized SearchPathPlugin declarations count as authorized.
Config-supplied additions must already have permission. This covers primary
configs and composition overrides, framework-owned entry points, and Compose.
Selecting an individual config or group within an authorized source does not
require a separate source grant.

Ordinary filesystem and package YAML loading remain supported, with the basic
containment checks specified in R10 for those sources.
A directory selection does not authorize Python package or module imports merely
because config files in that directory request them. The proposal does not
introduce process-wide filesystem isolation or an arbitrary-file-access policy.

Source authorization and containment are separate checks. Basic containment
checks config paths within a selected filesystem or package source even if that
source was selected explicitly by trusted initialization code.

The policy authorizes config search-path entries such as `pkg://foo.bar`.
These identify locations; the scheme selects the ConfigSource implementation.
Authorization of a custom implementation plugin remains a separate permission.

## Required behavior

### R1. Separate source selection from source permission

In checked operation, sources requested by loaded config content must already
be authorized. An explicit source selection from trusted initialization code,
CLI source flags, or a literal `hydra.searchpath` override supplied through the
CLI or `compose(overrides=...)` both activates and authorizes that source. Do not
require callers to copy the same selection into a permission list. Callers are
responsible for which override inputs they pass to Compose.

A config-defined alias that expands into a source selection does not supply
authorization. Configuration-derived interpolated source values likewise cannot
grant themselves authority; this rule does not require adding new interpolation
support. Track the source of a declaration rather than treating all expanded
overrides as caller-authored. Merely being importable, installed, or already
imported does not itself grant permission for an additional source.

Sources explicitly declared by trusted initialization and framework code must
remain usable without requiring a duplicate list of the same permissions.
Sources added programmatically by an authorized SearchPathPlugin are likewise
automatically authorized. This preserves platform activation through a
search-path plugin, including organization sources that supply higher-priority
`hydra/env` defaults, without introducing a separate platform activation system.

This authority comes from the authorized plugin's declaration. An ordinary
composed config value, an environment-profile name, or source precedence cannot
grant permission for an additional source. The HLD must define how plugin-added
sources and the built-in ConfigStore source participate without letting
config-supplied requests inherit that trust.

### R2. Preserve simple framework usage

A user can select a directory of YAML files using the framework's normal Hydra
CLI, without a package install, `__init__.py`, or an edit to framework Python code.
Users can activate and authorize multiple sources at launch through existing
source-selection flags and list-valued `hydra.searchpath` overrides.

Uninstalled code exposed through an existing `PYTHONPATH` or editable checkout
must work when its config source is authorized. `PYTHONPATH` supplies import
availability, not authorization. Hydra must not silently add a config-selected
directory to Python's import path as a consequence of this feature.

Reuse `--config-path`, `--config-dir`, and explicit `hydra.searchpath` overrides.
Do not add the previously proposed `--config-source` flag.

### R3. Support the same boundary in Compose

Add `config_search_path` to `hydra.main()` and `initialize()`, alongside optional
`config_path`. The primary source comes first, followed by the additional sources
in their listed order, before existing plugin adjustments. First match wins.
Explicit declarations add and authorize their sources. Existing single-source
initializers continue to authorize their supplied source. Preserve existing
plugin hooks and CLI insertion positions.

Deprecate `initialize_config_search_path()` as a compatibility adapter to
`initialize()`, with a warning and migration guidance, preserving ordered-source
and caller-relative URI behavior. Its removal release is not selected.

Explicit Compose source-selection overrides have the same authority as explicit
CLI overrides. Config-derived selections require an existing grant in either
path. Compose declaration grants are call-scoped and cannot authorize a later
call. No additional Compose `config_search_path` parameter is needed.

### R4. Check before source initialization

In restricted operation, reject an undeclared source before
constructing or initializing that source, checking its availability, or importing
its selected package/module.
Do not perform an import to find out whether the source is authorized.

Loading an authorized source is not authority to expand permissions. Through
Hydra's grant-making APIs, a config-load/import operation must not install
additional grants or make authorizing plugin registrations. Registering config
data in ConfigStore remains allowed. This restriction applies at Hydra's own
boundaries; it does not promise to contain arbitrary imported Python code.

Equivalent URI spellings must not bypass the check. The HLD must explicitly
define source normalization and matching, including whether any descendant
permission exists; no wildcard or prefix permission is implied by this draft.
The decision must apply consistently to normal composition and inspection paths.

### R5. Keep explicit opt-outs in the authorization policy

Export one `UNSAFE_DISABLE_AUTHORIZATION_CHECKS` constant for use independently
in the policy's search-path, plugin and execution fields. The receiving field
identifies the category whose authorization checks are disabled. Support this
explicit value in both 1.4 and 1.5. Preserve the existing execution unsafe
constant as a compatibility alias with its existing behavior.

A source opt-out uses
`AuthorizationPolicy(allowed_search_path_entries=UNSAFE_DISABLE_AUTHORIZATION_CHECKS)`.
Pass it through the existing authorization argument or context. Do not add a
separate main/Compose unsafe-source flag. The opt-out follows normal policy
lifetime and restoration: an explicit Compose policy affects that call; a main
policy affects that invocation; initializer policy belongs to its session.

Config content and config overrides cannot enable an opt-out. Disabling one
category's authorization does not disable another category's checks. Source
containment, plugin discovery settings and ordinary validity checks still apply.

### R6. Make denial and migration understandable

A denial or migration warning identifies the requested source and the caller's
available way to authorize it. Diagnostics link to one web page explaining
source authorization and existing execution authorization, their different
effects, and examples for framework CLIs and Compose callers.

The guidance must not tell an application to copy every requested permission
from an untrusted config without evaluating it. It must explain that authorizing
a Python-backed source accepts the selected package/module's normal Python
initialization behavior, including parent-package imports.

### R7. Permit a staged migration

Hydra 1.4 defaults each permission category to LEGACY, with visible deprecation
warnings and migration guidance. An explicit list opts its category into checks,
including under inherited LEGACY. Warnings alone are not an enforcement boundary.

Hydra 1.5 defaults the three categories to empty grant lists and rejects explicit
LEGACY values. Trusted declarations and Hydra's built-in components remain
available. The shared explicit unsafe value remains supported in every category.

Absence of an unsafe opt-out must not be misrepresented as enforcement while a
category is LEGACY. The containment rollout is separate: R10 requires
immediate errors in Hydra 1.4. Removing automatic namespace scanning is distinct
from allowing explicitly authorized classes under `hydra_plugins`.

### R8. Share one authorization object across permission categories

Provide one authorization object that holds separate source, plugin, and execution
permissions. Trusted callers can use that object as a context manager around
initialization, composition, and execution, or pass it explicitly to the relevant
Hydra interfaces. Source grants do not grant execution permission, and execution
grants do not grant source permission. Granting permission alone must not add a
source or change source lookup order.
Source and execution grants do not implicitly authorize external plugins.

Context-scoped permissions must support nesting and restoration, including after
exceptions, without becoming process-global grants. Export `AuthorizationPolicy`,
`replace`, `LEGACY` and `UNSAFE_DISABLE_AUTHORIZATION_CHECKS` from the regular
`hydra.authorization` module. Its grant fields are `allowed_search_path_entries`,
`plugins` and `execution_whitelist`. The first permits config-requested entries;
`config_search_path` on main/initialize selects and authorizes entries. Do not also
provide a callable `hydra.authorization(...)` factory.

Omitted or None fields inherit. Ordinary lists add grants; an empty list adds no
grants and does not clear an inherited list. `replace([...])` replaces inherited
grants only for its category; `replace([])` clears them. A list under LEGACY
enables checking. An inherited unsafe value remains active under additive
combination in every category and can be replaced with `replace([...])`. Restore the outer
policy on exit. Keep the existing execution context's `reset=True` behavior.

Preserve trusted Python callers' ability to authorize an individual
`instantiate()` call or establish a local execution authorization context, even
when initialization or `hydra.main()` supplies a broader policy. Retain the
existing execution whitelist's additive and explicit-reset semantics during
migration. A local execution-only grant or reset must not change source
or plugin permissions, mutate the enclosing policy, or leak into subsequent calls.

Evolve the existing policy foundation rather than introduce a parallel policy
system. Retain the existing execution-whitelist APIs as execution-only adapters
to the same foundation; this feature does not deprecate them. Supplying both an
explicit `authorization=` policy and the old `execution_whitelist=` argument on
one call is an error. Require consolidation into the policy, rather than merge
precedence. Nested execution contexts and local instantiate grants remain valid.

The authorization API must not be callable through configuration-driven
`instantiate()`. Treat its public and canonical implementation identities as
non-whitelistable policy controls, including AuthorizationPolicy construction,
context-entry or mutation operations, and the replace helper. An ordinary exact
or wildcard execution grant must not permit these targets. Apply the existing
resolved-identity protections to aliases rather than relying on public spelling
alone. Preserve the separate explicit unsafe execution opt-out; this requirement
does not redefine what disabling all execution checks means.

### R9. Warn authors about legacy namespace discovery

When a plugin relies on legacy `hydra_plugins` namespace discovery, emit a visible
deprecation warning that identifies the plugin and directs its author to declare
a `hydra.plugins` entry point. Include the migration guide URL:
https://hydra.cc/docs/upgrades/1.3_to_1.4/plugin_discovery/.

A migrated plugin may keep its module under `hydra_plugins`. Do not warn merely
because of that module name when the plugin has a working entry point. Retain
legacy namespace support during the documented compatibility period; this
requirement does not select its removal release.

The migration guide must give plugin authors a usable packaging example, explain
one entry point per concrete plugin class, preserve config-registration imports,
and explain reinstalling the package and verifying discovery. A warning for an
unscannable editable install does not replace the warning for successfully loaded
legacy plugins.

### R10. Basic containment for filesystem and package config sources

Assume that the Python environment and filesystem are trusted and that paths
are not maliciously changed during a config operation. Under that assumption,
config-controlled paths must not cause Hydra's built-in filesystem or package
config sources to read configuration content or list directories outside the
selected source root. Hydra 1.4 must reject containment violations immediately
as a breaking change, without a warning-only period before Hydra 1.5.

Resolve the source root against its initialization location and resolve requested
paths using native filesystem semantics. A candidate must resolve to that root
or a descendant of it. Use path components rather than a textual prefix. Apply
the rule consistently to loading, config/group lookup, and directory listing,
including inspection and completion paths. Inability to establish containment
must not allow an unchecked read or listing.

Allow symlinks and Windows junctions whose resolved targets remain inside the
selected source root; reject paths that escape it through links, traversal, or
absolute-path forms. The boundary is per source. A separate grant for
another source does not itself authorize following an escaping link to it.
Existing projects that share configs through such links will need migration
guidance for selecting the other source directly.

For `pkg://`, the boundary is the selected package's resource root, rather than
the whole Python installation or archive. Directory-backed packages use resolved
filesystem containment. Archive-backed packages use resource-path validation
within that package's subtree, without extracting the archive. Config paths must
not escape to another package or another subtree in the same archive. Normal
package imports and their side effects remain trusted Python behavior outside
the config-resource containment promise.

Support the project's existing Python versions and operating systems. Do not add
directory locks, native platform bindings, or protection against concurrent path
replacement under this requirement. It does not authenticate config contents,
restrict Python imports or authorized code's file operations, or claim physical
file provenance through hard links. Custom config sources and resource loaders
remain trusted code; this feature does not mediate their internal Python
execution. The HLD must account for existing resource-loader compatibility rather
than assume every package resource has a filesystem path.

The source-authorization compatibility mode must not postpone the required 1.4
containment errors. The HLD must define the source opt-out's interaction
with containment rather than silently make that option disable it. Runtime
overhead should be assessed against existing path resolution; no benchmark or
performance guarantee is claimed by these requirements.

### R11. Authorize external plugins before discovery imports them

Establish the effective policy at `hydra.main()` and throughout the initialize
family before external plugin discovery imports code. For Compose, authorization
must be available during initialization; passing a policy only to `compose()`
cannot retrospectively authorize discovery. Application declarations, surrounding
authorization contexts, and dedicated user selections must support framework
users choosing plugins without editing framework code. Ordinary config content
and config overrides cannot grant plugin permission.

Compose must reject a plugin-policy change requiring discovery outside the
initialized selection, before imports, with guidance to authorize during
initialization. Reusing or narrowing the initialized selection remains supported.

In restricted operation, do not import an unauthorized external plugin merely to
discover its classes or determine whether it is allowed. A cached class or module
is not evidence of permission in the current context. Hydra's own built-in
plugins remain part of trusted Hydra setup, without duplicate caller grants.

Explicit registration of a plugin class by trusted application setup authorizes
that class for use in the receiving scope. A config-load/import operation does
not gain this grant-making authority. Registration outside an initialization context
can establish an application baseline; registration inside one is scoped to it.
Explicit registration must not first trigger unrelated unauthorized discovery.
It does not authorize arbitrary config-selected execution targets. The HLD must
define plugin identities separately from source and execution permissions.
Use installed `hydra.plugins` entry-point names as the normal selector. Resolve
metadata and reject ambiguous names before importing plugin code. Also support
explicit `module:Class` selectors for plugins without an entry point. Python
policy lists and the CLI use the same selectors. Accept both comma-separated
values and repeated occurrences of `--authorize-plugin`. An ordinary explicit
grant covers the selected class. The shared unsafe value disables plugin
authorization while retaining plugin validation and discovery settings.

### R12. Restore Hydra-owned plugin state across initialization contexts

An initialization context must restore its previous Hydra-owned plugin registry
state, visibility, and permissions when it ends. The same cleanup is required
when initialization fails before context entry or an operation raises. Cached
registrations must not let a later, unrelated context use plugins or config-source
implementations that it has not authorized. Keep pre-existing application-level
registrations available when restoring the previous scope.

This requirement covers Hydra's registry and authorization lifecycle. It does
not unload Python modules or undo effects of trusted plugin imports, such as
arbitrary application-code mutations. The HLD must account for shared registry
state rather than assume Python context variables alone isolate it.

### R13. Propagate authorization before worker initialization

Multirun and launcher workers must receive the effective authorization through
trusted job/bootstrap state before plugin discovery, source initialization, or
composition. Preserve permission categories, namespace-discovery settings, and
their intended scope. Restoring singleton state must not trigger discovery before
the worker's policy is established. Job configuration or saved config data must not
become an authorization grant, and propagation must not silently broaden access.

The HLD must define the launcher integration contract and its migration guidance,
including how supported launchers retain policy across process boundaries.

### R14. Allow disabling legacy namespace discovery before import

Provide a policy switch to disable legacy `hydra_plugins` namespace discovery.
When enabled, Hydra must not import the namespace or walk its modules for that
discovery path, including during worker bootstrap. This does not prohibit an
authorized entry point or explicit registration merely because its module lives
under `hydra_plugins`. Normal imports made by trusted Python remain outside the
switch's scope.

Expose `legacy_plugin_discovery` on the policy. Its omitted value inherits;
automatic scanning is allowed by default only under the 1.4 LEGACY plugin
policy. The shared unsafe value does not itself enable namespace scanning;
an explicit scan request still needs a permissive plugin policy, and False
always disables the scan. Checked plugin selection never requires an
unrestricted namespace walk.
Once namespace discovery is removed, this switch may become a deprecated no-op.
Removing legacy authorization does not remove explicit `module:Class` use of
namespace packages; no package-namespace removal release is selected here.

## Observable acceptance criteria

- **AC1:** A framework-owned `hydra.main()` can compose a user's YAML directory
  without an installation step or source changes to the framework.
- **AC2:** Multiple explicitly authorized package/module config sources work,
  including code in an uninstalled source checkout made importable by the user.
- **AC3:** An undeclared source supplied by configuration is refused in restricted
  operation before initialization or availability checks. This covers filesystem,
  package, named structured, and custom sources, including pre-import refusal
  for sources that import Python. YAML, dataclass configs and their resulting
  DictConfig do not acquire grant authority from loading or conversion. Grant
  expansion attempted through Hydra APIs during config loading is rejected;
  registering config data in ConfigStore remains usable.
- **AC4:** Literal source selections supplied through Compose or CLI
  `hydra.searchpath` overrides activate and authorize the selected sources.
  Config-defined aliases or interpolations cannot turn a config-derived selection
  into a grant. Prior imports do not supply permission. A call's declaration
  grant does not authorize an unrelated later Compose call.
- **AC5:** Explicitly authorized filesystem-YAML sources and previously registered
  structured configs remain usable. Selecting a YAML folder does not authorize
  a Python source requested by its contents.
- **AC6:** Main and initialize accept `config_search_path` alongside optional
  `config_path`, without duplicate permission entries. The primary source
  precedes the additional list, preserving list order and existing plugin/CLI
  behavior. The deprecated list initializer forwards with migration guidance.
- **AC7:** Source denial occurs before initialization, including cases where
  composition would later fail for an unrelated reason. Equivalent source URI
  spellings cannot evade a denial.
- **AC8:** Passing the shared unsafe value in an explicit Compose policy's
  `allowed_search_path_entries` field permits that call's otherwise undeclared
  entries; the next restricted call refuses them. Config data and overrides
  cannot enable it. Main/initializer/context use follows normal policy scope.
- **AC9:** Granting source permission or disabling source authorization does not
  authorize an otherwise denied instantiated target or logging target.
- **AC10:** In 1.4, LEGACY retains old selection behavior with deprecation
  warnings; explicit lists enable checks under inherited LEGACY. In 1.5, default
  grants are empty and explicit LEGACY is rejected. Diagnostics state which
  checks apply and provide a documentation link and caller-specific example.
- **AC11:** A caller can use one authorization context for source checks during
  initialization/composition and execution checks during instantiate or logging.
  Each permission field works independently; source grants alone do not add
  sources or alter lookup order. Call-specific and nested-context execution
  grants retain their additive and explicit-reset behavior under an entry-point
  policy, without changing source grants or later calls' permissions.
- **AC12:** Nested authorization contexts restore their previous permissions on
  normal exit and exceptions. Lists add grants, while `replace([...])` replaces
  only its category; `[]` retains an inherited list and `replace([])` clears it.
  An additive list preserves an inherited unsafe value in any category;
  replacement can enable checks. No permission leaks into unrelated contexts.
- **AC13:** Existing execution-whitelist adapters retain execution-only behavior
  through the shared implementation. Supplying both a policy and the old
  execution argument on one call is an error before side effects, with guidance
  to consolidate. Local instantiate grants and nested execution contexts remain
  supported and do not silently authorize config sources.
  With execution checks enabled, instantiate rejects authorization-API targets
  even under exact grants or aliases, before they can create or enter a policy.
  The old execution unsafe constant aliases the shared value. No parallel
  main/Compose unsafe-source argument is introduced.
- **AC14:** A successfully discovered namespace-only plugin remains available and
  emits a visible deprecation warning identifying it and linking to the migration
  guide. A plugin with a working entry point does not receive that warning merely
  because its code remains in `hydra_plugins`.
- **AC15:** Following the migration guide lets a plugin author declare the entry
  point, retain configuration registration, reinstall, and verify discovery
  without relying on legacy namespace discovery.
- **AC16:** An authorized SearchPathPlugin can add an organization config source
  and supply higher-priority `hydra/env` defaults without a duplicate source grant.
  An additional undeclared source requested by ordinary composed configuration,
  including that environment profile's config, remains subject to authorization.
- **AC17:** Files and groups beneath a filesystem or package source root remain
  usable, including filesystem links resolving within it. In Hydra 1.4, paths
  escaping the source root produce an immediate error before config-content
  reads or directory listings through that source.
- **AC18:** Traversal, absolute-path escapes, and sibling directories
  with a shared textual prefix are rejected. Applicable Windows drive, UNC, and
  junction cases are covered on Windows; symlink cases are covered where supported.
  Archive-backed package lookups cannot reach siblings outside the selected
  package's resource subtree, even inside the same archive.
- **AC19:** Config/group lookup and listing cannot bypass a refusal
  enforced during loading. A separate authorization for another root does not
  permit a link escaping the selected source's root.
- **AC20:** Documentation states the stable-filesystem assumption,
  explains migration for external shared-config links, calls out immediate 1.4
  containment errors, and identifies the unsafe-option behavior accepted by the
  HLD. It does not claim protection against concurrent filesystem replacement.
- **AC21:** Unauthorized external plugins are refused before discovery imports
  them. Trusted application registration authorizes its class without unrelated
  unauthorized discovery; built-in Hydra plugins need no duplicate grants.
  Entry-point-name selectors work in policies and comma-separated or repeated
  CLI arguments. Ambiguous names fail before importing any candidate plugin.
  The shared unsafe plugin value permits otherwise unauthorized entry-point
  loads while retaining class validation and namespace discovery settings.
  Compose rejects changes requiring new discovery before importing anything.
- **AC22:** Normal context exit, exceptions, and failed initialization restore
  prior Hydra-owned plugin registry visibility and permissions. Later contexts
  cannot inherit authority merely from cached registrations or imports.
- **AC23:** Supported worker/bootstrap paths establish the effective policy
  before discovery and composition, without converting job config data into grants or
  broadening the originating permissions.
- **AC24:** Disabling legacy namespace discovery prevents Hydra's namespace-scan
  imports. Authorized entry-point plugins can still reside under `hydra_plugins`.
- **AC25:** Framework-owned `hydra.main()` and the initialize family accept the
  shared policy before source/plugin initialization. Execution-only local
  grants or resets do not change source or plugin permissions.

## Constraints and exclusions

- Reuse existing source-selection and initialization mechanisms where possible.
  Do not introduce a second registry that callers must maintain in parallel with
  their config-source list without a demonstrated need.
- Organizations are responsible for arranging trusted startup authorization of
  their plugins through Hydra's general authorization interface. Designing an
  organization-specific automatic authorization or discovery mechanism is out of
  scope; organization membership or naming does not itself grant permission.
- Do not require config packages to reside in site-packages or require users to
  understand packaging. A `.pth` startup-execution argument does not establish
  that arbitrary importable development directories are already compromised.
- Do not interpret execution-target grants as source grants. Both permission
  categories may share an authorization object and context mechanism.
- Authorized plugins, custom source implementations, import hooks, registered
  resolvers, and authorized Python code remain trusted. This feature does not
  infer every custom plugin's import behavior or mediate its internal execution.
  The exact integration and honest limits must be documented by the HLD.
- Do not change supported Python versions, CI matrices, packaging, release
  automation, source lookup precedence, or existing execution-policy promises
  merely to implement this feature.
- Product documentation and a user-facing news fragment belong to the eventual
  implementation. These planning files alone are developer documentation.

## Approval boundary and next work

Acceptance of these requirements must explicitly cover all-source authorization,
framework usability, Compose boundary and unsafe option, shared authorization
object, plugin lifecycle and worker propagation, staged migration, and the
accepted basic containment boundary.
An accepted requirements document is not an architecture approval or an
implementation-ready plan.

The HLD must resolve major interfaces, matching/normalization, trusted source
provenance, migration activation, and operation scope. The implementation plan
must resolve the engineering details and own the only delivery slice inventory
and code estimates. See [process constraints](supporting/process.md),
[current status](supporting/status.md), and [research](supporting/research.md).
