# Config source and plugin authorization

Architecture revised for owner review against the
[requirements](requirements.md). The
[owner decision history](supporting/hld-api-discussion.md) records the accepted
API choices and later clarifications. Earlier reviews
cover earlier document bytes; renewed review and whole-document approval are
pending. The APIs below specify planned behavior, not implemented functionality.

## The core

Most users declare their config sources once. Explicit Python declarations,
CLI source selections, and literal source-selection overrides add and authorize
their sources. No duplicate policy or config list is needed. Loaded configuration
can request additional sources, but those need existing grants. YAML, dataclass
configs and resulting DictConfig all carry no grant authority. Loading,
importing or converting a config must not expand Hydra authorization.

Use one policy for config sources, plugins, and the execution whitelist used by
instantiation and Hydra-configured logging. Establish it before initialization.
Authorized SearchPathPlugins can declare platform sources. Restore Hydra-owned
registries when initialization ends; propagate trusted policy before workers
discover plugins or compose configs. Authorized Python runs normally.

## Public Python API

Use a regular module. Export its constructor and helpers together:

```python
from hydra.authorization import AuthorizationPolicy, LEGACY, replace
```

Public signatures:

```text
AuthorizationPolicy(
    *,
    config_sources=None,
    plugins=None,
    execution_whitelist=None,
    legacy_plugin_discovery=None,
)

replace(grants)
```

The policy is immutable and reusable as a context manager or an `authorization=`
argument. There is no callable `hydra.authorization(...)` factory, `mode=`
argument, or separate shared-policy `reset=` list. Qualified access such as
`hydra.authorization.replace(...)` works through normal module imports.

| Field | Meaning |
| --- | --- |
| `config_sources` | Exact source URIs that configuration may request later. Grants alone do not add sources. |
| `plugins` | Installed `hydra.plugins` entry-point names, or explicit `module:Class` selectors. |
| `execution_whitelist` | Existing execution grants and patterns, covering instantiate and Hydra logging. Accepts the existing execution unsafe sentinel. |
| `legacy_plugin_discovery` | Inherited when None; False disables namespace scanning. Scanning is permitted only with a LEGACY plugin policy. |

Grant lists contain strings and are copied on construction. The existing
execution API retains its accepted input forms. Source/plugin permission does
not imply execution permission, and execution grants do not imply either one.

### Inheritance and replacement

| Value | Effect on that permission category |
| --- | --- |
| Omitted or None | Inherit. At the outermost boundary, use the release default. |
| A list | Add grants to an inherited list; under LEGACY, enable checks using this list. |
| `[]` | Add no grants; preserve an inherited list, or enable checks under LEGACY. |
| `replace([...])` | Replace inherited grants for this category. |
| `replace([])` | Clear inherited grants for this category. |
| `LEGACY` | Select deprecated legacy behavior in 1.4; reject in 1.5. |

Context exit restores the outer policy, including on exceptions. Replacing one
category does not change another. Ordinary additive execution grants preserve
an inherited `UNSAFE_DISABLE_EXECUTION_CHECKS`; replacement can enable checks.
Trusted source declarations and Hydra's built-in setup remain usable after a
grant-list replacement. A reset does not undo an initialization or past imports.

```python
policy = AuthorizationPolicy(
    config_sources=["pkg://app.conf"],
    plugins=["joblib"],
    execution_whitelist=replace(["app.Model"]),
)
```

Here the source grant does not activate `app.conf`. It permits configuration to
request that source later. The plugin grant selects which discovery imports are
permitted. The execution replacement applies only to execution permissions.

### Hydra entry points

Keep existing positional arguments and version-base behavior. Add these
keyword-only parameters:

| Interface | New parameters |
| --- | --- |
| `hydra.main()` | `config_search_path=None`, `authorization=None`, `unsafe_allow_undeclared_config_sources=False` |
| `hydra.initialize()` | `config_search_path=None`, `authorization=None` |
| `initialize_config_dir()` and `initialize_config_module()` | `authorization=None` |
| `hydra.compose()` | `authorization=None`, `unsafe_allow_undeclared_config_sources=False` |

`config_path` remains optional and declares the primary source. The additional
`config_search_path` list uses source URIs, including existing `caller://`
resolution. Paths use the existing caller/decorator location, not a later job
working directory. Absolute file URIs keep existing native path validation.
Assemble application sources as primary first, then list order. First match
wins; existing plugin hooks and CLI insertion positions remain unchanged.

```python
@hydra.main(
    config_path="conf",
    config_name="train",
    config_search_path=["pkg://shared.conf", "file:///work/configs"],
    authorization=AuthorizationPolicy(plugins=["joblib"]),
)
def app(cfg):
    ...
```

```python
with hydra.initialize(
    config_path="conf",
    config_search_path=["pkg://shared.conf"],
    authorization=policy,
):
    cfg = hydra.compose(config_name="train")
```

Deprecate `initialize_config_search_path()` as an adapter to `initialize()`.
Its ordered sources and caller-relative URI behavior stay intact. Warn with
the replacement call; no removal release is selected. It remains usable in its
existing global and context forms during deprecation.

Compose uses the initialized search path and can explicitly select additional
sources through its existing overrides:

```python
cfg = hydra.compose(
    config_name="train",
    overrides=["hydra.searchpath=[pkg://experiment.conf]"],
)
```

That literal selection adds and authorizes the source for this call. No policy
copy or new Compose `config_search_path` parameter is required. Callers own the
trust of override strings they pass. A Compose policy cannot retroactively
authorize plugin discovery; plugin changes require a new initialization scope.

### Existing execution APIs

Keep `hydra.utils.execution_whitelist()`, its `reset=True` operation, existing
execution arguments, and local `_execution_whitelist_` instantiate grants as
execution-only adapters. Do not deprecate them in this feature. Logging uses
the same effective execution field. Local grants remain usable under a shared
policy without changing source or plugin permissions.

Supplying both an explicit `authorization=` policy and the old
`execution_whitelist=` argument on the same call is an error before imports or
initialization. Require consolidation into the policy. An omitted old argument
is not a conflict. Preserve explicit argument presence rather than letting a
defaulted old value invalidate every policy use. This rule does not reject
surrounding contexts or execution grants on separate local instantiate calls.

Include the shared policy and registry-control interfaces in Hydra's checks
against configuration selecting or mutating authorization state. A policy object
created by configuration is not trusted caller authority. This protects Hydra's
own boundaries without claiming to contain authorized application Python.

Explicitly block the `hydra.authorization` API from configuration-driven
`instantiate()` using the existing non-whitelistable policy-control mechanism.
Cover AuthorizationPolicy construction, its context/mutation entry points and
the replace helper, including canonical implementation identities and resolved
aliases. An exact or wildcard whitelist cannot authorize them. Keep public-path
and resolved-identity checks together so renaming an import does not grant
access. Focused regression coverage must verify this boundary while retaining
normal trusted Python API use. The existing explicit execution unsafe opt-out
continues to disable execution checks; ordinary grants never have that effect.

## Command line and configuration

Existing `--config-path` and `--config-dir` selections activate and authorize
their sources. So do literal `hydra.searchpath=[...]` overrides, with the same
authority on the CLI and in Compose. Do not add `--config-source`.

Authorize plugins with entry-point names, comma-separated values, repeated
flags, or a combination of both:

```text
python app.py --config-dir /work/configs --config-name train \
  --authorize-plugin joblib,colorlog
```

`--authorize-plugin joblib --authorize-plugin colorlog` is equivalent. Python
uses the same selectors: `AuthorizationPolicy(plugins=["joblib", "colorlog"])`.
For a plugin without an entry point, use `module:Class`. Ambiguous entry-point
names fail before importing any candidate. Ordinary plugin config selections
do not grant plugin permission or execution-whitelist permission.

Config source declarations request permission. They do not grant it. Preserve
origin through alias expansion: this config cannot authorize `extra.conf` merely
because the caller invokes `fast`:

```yaml
hydra:
  aliases:
    fast: "hydra.searchpath=[pkg://extra.conf]"
```

The source needs a grant, or the caller must explicitly select its URI.
Configuration-derived interpolations likewise do not become grants. Preserve
existing interpolation support; this feature does not add new forms.

## Source authorization at the repository boundary

Reuse ConfigSearchPath and ConfigRepository. Before resolving a source class,
constructing it, calling availability methods, or importing its selected Python
module, the repository checks the requested source against the effective grants.
Inspection, completion, sweep composition and ordinary composition use this same
boundary. A cached repository must not skip a check required by the current call.

Trusted declarations produce grants in the receiving session or Compose call:

- Hydra's built-in sources, including its bare `structured://` ConfigStore source.
- Sources supplied by application initialization, CLI source flags, and literal
  CLI or Compose source-selection overrides.
- Entries added or changed programmatically by an authorized SearchPathPlugin.

Record this origin in Hydra-owned search-path state, not by interpreting provider
strings or YAML fields. Keep the current hook interface: capture the resulting
entries around each trusted search-path hook, including direct list edits.
Loaded configs and config-authored alias/interpolation selections enter as requests.
Capture literal caller declarations before expanding config-defined aliases.
The existing `from_shell` diagnostic flag and provider labels do not establish
authority. Preserve origins through copies, override parsing, sweeps and reruns;
persisted override strings alone are not trusted bootstrap grants. Initialization
declarations last for that session; Compose declarations last for that call.
Neither mutates the caller's policy object or authorizes an unrelated call.

Keep a config-load scope active around source loading, selected config-module
imports and structured-config conversion. Hydra's grant-making API paths must
reject attempts from that scope to install additional policy grants or register
plugins with authorizing effect. Constructing or returning a policy-looking data
object is not caller permission. ConfigStore data registration remains allowed.
Authorized SearchPathPlugin declaration hooks retain their separate trusted
setup role; config loading does not inherit that grant-making authority.
This is a check at Hydra's APIs, not a sandbox for Python import side effects,
arbitrary process execution, or deliberate mutation outside those APIs.

An authorized platform search-path plugin can therefore prepend its organization
source and supply `hydra/env` defaults. That profile's config cannot authorize an
additional source. Organizations arrange their own trusted plugin selection;
Hydra supplies no organization-name or installation-based automatic grant.

Use exact, conservative URI matching. Normalize using built-in string/path rules
before invoking any source implementation:

| Source | Authorization identity |
| --- | --- |
| `file://` or an existing bare filesystem path | Absolute lexical path, normalized by native path rules and pinned to the operation's original base directory. No `~` or environment expansion is implicit. |
| `pkg://` | Package name using the existing slash-to-dot and trailing-dot normalization. No import to compute identity. |
| `structured://module` | Exact validated module name; bare `structured://` is a distinct identity. |
| Custom scheme | Exact scheme and body string. Its implementation is not called to normalize an unauthorized request. |

Expand `caller://` through the existing trusted initializer mechanism before
matching. Do not introduce it as a config-controlled way to select a new caller.
No percent-decoding, wildcard, source-prefix or descendant grant is introduced.
For filesystem authorization, symlink aliases can require separate exact grants;
the resolved root used for containment is a separate step. Malformed or ambiguous
drive-relative paths fail rather than gaining a broader identity. Windows case
and separator normalization use native rules. Importability and caches are not
permission. Matching must be independent of source lookup precedence.

For a custom source, both its implementation plugin and the requested source URI
must be allowed. A trusted plugin may itself import dependencies or execute code;
Hydra does not mediate that Python behavior.

## Plugin selection before imports

Separate construction of the Plugins registry from external discovery. Obtaining
the registry for trusted `register(MyPlugin)` must not scan other plugins.
Trusted application registration adds the specific class and its permission to
the receiving scope;
outside an initialization scope it becomes part of the application baseline.
The config-load guard prevents source imports from using registration as a grant.

With plugin checks active, enumerate `hydra.plugins` entry-point metadata without
loading entries. Resolve name selectors to their module/class identity and reject
unknown or ambiguous names before calling `load()`. Explicit `module:Class`
selectors match that identity or select the named class directly. Preserve
uninstalled and namespace-only code without an unrestricted namespace walk.
Ignore unselected installed entries without importing them; do not abort merely
because an unrelated unauthorized plugin is installed. Refuse a later request
to use an unselected external plugin.
Validate that the selected object is a concrete Plugin, then register it.
Do not treat every class discovered in that module as authorized for use.
Normal imports of parent packages and dependencies belong to the explicitly
selected Python code's trusted behavior. An entry-point name is a selector
resolved through installed metadata; it does not authenticate the installation.
Carry resolved identities through trusted worker state to prevent name resolution
from silently selecting a different plugin there.

In 1.4, plugin LEGACY retains automatic namespace and entry-point discovery.
Warn before otherwise unauthorized imports; distinguish migration warnings
from refusal with checks active. If scanning is disabled, do not import the
namespace or walk its modules for discovery. Named selections and authorized
entry points may still import code located under `hydra_plugins`.

After compatibility discovery, emit one visible deprecation warning per
successfully loaded namespace-only plugin, with its identity and the
[plugin migration guide](https://hydra.cc/docs/upgrades/1.3_to_1.4/plugin_discovery/).
Use valid entry-point coverage to avoid warning migrated classes. Do not decide
coverage by module prefix or distribution name alone. Keep existing import-error
diagnostics; a broken entry point is not evidence of successful migration.
The guide must cover packaging, one entry per concrete class, registration
imports, reinstalling, and `--info plugins` verification.

Before Hydra discovers, lists, resolves, or instantiates a registered external
plugin, use the receiving scope's permission. Previous discovery or a cached
class is insufficient. Core Hydra plugins need no extra grant. Automatic internal
instantiation of an authorized launcher/sweeper remains trusted Hydra behavior;
it does not grant arbitrary config-selected execution targets.

## Initialization and restoration

Create one internal initialization scope that owns effective authorization plus
the Hydra-owned registry state it changes. Reuse current ContextVar token handling
for grants, and explicitly save/restore GlobalHydra, Plugins maps/visibility, and
SourcesRegistry types. Snapshot Hydra-owned containers, retaining Python class
references; do not deep-copy arbitrary application objects as an isolation scheme.

Initializer constructors enter this scope before their first discovery call.
`__enter__` must not be the first protection point. Successful context exit and
constructor failure both restore the prior state. A global initializer retains
its scope until Hydra is cleared; clearing must release that scope. Preserve
pre-existing application registrations. A temporary nested initializer, where
current Hydra initialization rules permit it, restores the outer state.

Do not introduce simultaneous independent initializers sharing these global
registries. ContextVar-local permissions alone cannot provide that isolation.
Existing initialization restrictions remain. Python imports, ConfigStore content
registered by trusted Python, and arbitrary import effects are not rolled back;
their presence must never substitute for a later source or plugin grant.

Each Compose call resolves policy from the initialized session, surrounding
authorization context, and explicit call argument, in that order. It uses a fresh
call scope and restores it on success or failure. Plugin/source implementation
visibility cannot broaden just because a Compose policy contains plugin grants;
initialization is the place to change discovery. Repository caches are scoped or
revalidated so an earlier unsafe call cannot authorize the next restricted call.
Trusted source declarations belong to the receiving session, alongside its
policy. Grant replacements do not remove that session's explicitly selected
sources or Hydra's own sources; they replace inherited grants for additional
config-requested sources. Starting a different source selection uses a new
initialization session. A narrower caller policy must not reuse an already-created
source as permission for a new undeclared URI.

For `hydra.main()`, enter policy after argument parsing but before Hydra creation,
then retain it through discovery, composition, Hydra logging, launch and task
execution. Decorator policy, surrounding context and trusted CLI selections feed
that scope. The cfg-passthrough path still establishes execution policy but does
not pretend it performed composition or source validation.

## Workers receive trusted state

Extend the existing HydraContext/launcher bootstrap path with the resolved shared
policy, trusted declaration grants, explicit registration identities/classes and
namespace setting. This is trusted Python bootstrap state, not fields in job config
or `hydra.runtime.config_sources`. No new credential or signing protocol is needed
for the launchers' already-trusted Python transport.

Worker entry installs that state before `Singleton.set_state()`, plugin discovery,
source reconstruction, sweep composition, or logging. Singleton restoration
must use the receiving scope rather than automatically rediscover every installed
plugin. Local BasicLauncher jobs establish and restore the same effective scope.
Joblib and Submitit require explicit integration at their current restore points.
Reused workers restore their previous Hydra-owned policy/registry state after a
job, including failure. No worker-local broadening is inferred from cached state.

A missing/unsupported bootstrap contract fails before protected operations in
restricted operation. Compatibility launchers may retain old behavior with a
clear warning; they must not claim restricted protection. Third-party launcher
guidance must explain transport, ordering and restoration, including resubmission.
Cross-machine filesystem layout remains an application/launcher concern; any
trusted path remapping must update selections and grants together, never from YAML.

## Containment stays independent

Containment is always active for built-in filesystem and package sources. In 1.4,
a violation raises an error before config-content reads or directory listing,
even in compatibility mode or with an explicit source grant.

Resolve a filesystem source root once at initialization. At every load, lookup,
or listing, resolve the candidate and check native component ancestry against
that root. Include filenames after extension normalization and children reached
while enumerating groups. Allow links resolving inside the root; reject outside
links, traversal and absolute escapes. Another authorized source never widens
this root. Directory inspection and completion use these same operations.

For package sources, authorize the package before importing it. Resolve its
resource root when first initializing its resources. Directory-backed resources
use filesystem checks. Archive-backed resources validate relative components
within the selected package subtree and do not extract the archive. Validate
paths before joining and listing child names before further traversal. Another
package inside the same archive is outside this boundary.

Keep resource traversal behind a small internal helper used by all built-in pkg
operations. Use existing resource APIs, with concrete filesystem/archive handling
where needed. Trusted virtual loaders must retain rooted traversal; if Hydra
cannot establish the required root relationship, fail explicitly before read or
listing. Do not silently convert an unknown Traversable to a filesystem path.
Exact loader coverage is a finite LLD investigation and must be settled before
claiming implementation readiness.

The filesystem and import environment are trusted and stable for an operation.
This design does not close concurrent replacement races, authenticate contents,
prove hard-link provenance, or constrain authorized Python's file operations.
There are no directory locks or native platform bindings. Most filesystem paths
already use realpath; added ancestry checks and repeated candidate resolution
need measurement, not a claimed performance guarantee.

## Unsafe use, migration and diagnostics

Apply defaults per category, only when no enclosing policy supplies that value:

| Release | Default source, plugin and execution grants | Explicit LEGACY |
| --- | --- | --- |
| 1.4 | LEGACY, with visible deprecation warnings | Accepted with a warning |
| 1.5 | Empty lists | Error with migration guidance |

An explicit list opts its category into checks in 1.4. Other omitted categories
still inherit. Empty grants do not remove explicit source declarations, trusted
plugin registration, or Hydra's built-in components. Namespace package modules
remain usable through authorized entry points and explicit class selectors;
removing legacy authorization is not a ban on the package name `hydra_plugins`.

The Python-only `unsafe_allow_undeclared_config_sources=True` option lasts for
one main invocation or one Compose call. It defaults to false, does not add
lasting grants, and never disables plugin, execution, or containment checks.
In LEGACY source operation, false does not imply enforcement. An explicit unsafe
call is reported honestly as unsafe. Keep the existing separate execution unsafe
sentinel. Add no new unsafe plugin bypass in this design.

Provide one authorization guide at the proposed
`https://hydra.cc/docs/advanced/authorization/` URL. Explain source/plugin selection
and execution grants separately, with CLI and Compose examples. Denials identify
the request, active category checks, and a suitable trusted way to authorize it.
Explain parent imports and the caller's responsibility for override inputs.
Document external-link migration by selecting the target as a separate source.
Never suggest a source unsafe option to fix containment errors.

Diagnostic examples establish the behavior and required information; wording
may follow the project's style without changing the stated remedy:

```text
Config source 'pkg://extra.conf' is not authorized.
Add it to AuthorizationPolicy(config_sources=["pkg://extra.conf"]), or
select it explicitly through initialization or a CLI/Compose source override.
See https://hydra.cc/docs/advanced/authorization/.
```

For an identifiable unauthorized plugin, show its name and exact CLI remedy
before import. In LEGACY, make this a visible migration warning and continue;
with plugin checks active, refuse the requested use:

```text
Plugin 'joblib' is not authorized.
Use --authorize-plugin joblib or AuthorizationPolicy(plugins=["joblib"]).
See https://hydra.cc/docs/advanced/authorization/.
```

A skipped plugin may register its configs during import. Config lookup can
therefore fail before Hydra knows the requested plugin class. Append discovery
status without claiming that a particular skipped plugin caused the missing
config, and do not import it to make the diagnosis:

```text
Config 'hydra/launcher/joblib' was not found.
Installed plugin entry points skipped because they are not authorized: joblib.
Authorize the intended plugin with --authorize-plugin NAME.
See https://hydra.cc/docs/advanced/authorization/.
```

For namespace-only code, explain that scanning is disabled and show the explicit
`module:Class` authorization form. Do not invent a class inventory by scanning.
An ambiguous entry-point name lists candidate identities and asks for an exact
class selector. A same-call policy/execution-argument conflict tells the caller
to consolidate into `AuthorizationPolicy.execution_whitelist`. A 1.5 LEGACY
error directs migration to explicit declarations and grants.

Containment errors are immediate in 1.4. Product docs and user-facing news
fragments accompany implementation, including the initializer deprecation.

## Coverage and remaining engineering work

| Accepted requirements | Architecture responsibility |
| --- | --- |
| R1–R4; AC1–AC7, AC16 | Exact source grants, declaration origins, CLI/init selection, repository check before initialization. |
| R5–R7; AC8–AC10, AC20 | Scoped unsafe source option, honest mode diagnostics, migration guide, separate containment rollout. |
| R8; AC11–AC13, AC25 | Shared policy/context, per-category replacement, execution-only adapters and same-call argument conflict. |
| R9, R11, R14; AC14–AC15, AC21, AC24 | Exact plugin selection before imports, entry points, legacy warning and scan switch. |
| R10; AC17–AC20 | Resolved filesystem roots and rooted package resources on every read/lookup/list path. |
| R12; AC12, AC22 | Initialization transaction and explicit Hydra-owned registry restoration. |
| R13; AC23 | Trusted worker bootstrap before singleton restore and discovery. |

Detailed planning must refresh the stale API-dependent slices and resolve these
bounded engineering questions before claiming implementation readiness:

- Define internal policy serialization and replacement transport, preserve old
  execution-adapter behavior, and detect conflicting explicit arguments before
  side effects. The public API and behavior above are the design inputs.
- Specify search-path origin retention across direct hook edits, repository
  copies, alias expansion, schema handling, caches, reruns and worker bootstrap.
  Retain literal CLI/Compose authority without making YAML authoritative.
- Inventory package Traversable implementations on supported Python versions,
  including archives and trusted virtual loaders. Confirm their root checks;
  missing loader support requires explicit disposition, not unchecked access.
- Prove registry rollback through failed construction, clear, explicit registration
  and permitted nesting. Any simultaneous-initializer proposal needs a new owner
  decision rather than relying on context variables alone.
- Resolve selector parsing, repeated/comma-separated flag normalization,
  duplicate handling and warning deduplication without pre-authorization imports.
  Preserve the specified ambiguity error; no authenticity guarantee is added.
- Resolve worker transport and restoration for Basic, Joblib and Submitit,
  including resubmission and missing-policy failures before imports.
- Assess containment overhead using representative config/group/list operations;
  resolve Windows drive, UNC and junction checks on Windows. No benchmark result
  or live platform validation is claimed by this architecture.

These investigations own engineering detail, not a delivery inventory. The later
implementation plan alone will define slices, owned paths, dependencies and
production/test estimates. See [authoring evidence](supporting/hld-authoring.md)
for the inspected primitives and simpler alternatives. Requirements were aligned
to the owner's accepted API decisions. Renew affected reviews and obtain
whole-document owner approval before refreshing the detailed plan.
