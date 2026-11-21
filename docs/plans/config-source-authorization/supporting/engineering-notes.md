# Detailed-design evidence

Inputs are the approved requirements and HLD. Their exact hashes remain in
[status](status.md); detailed authoring does not edit either input.
The refreshed plan uses requirements
`2052ba2d84fc04b98c5485b1561dcab752840b1e3f0e131908233566b98241e7`
and HLD `4aac3ec633f26ff49327e0374f5fdbb96a592815011e90a62d1ee5c2dfa03a48`.

## Inspected foundations

`SearchPathElement` currently carries provider/path only. `ConfigSearchPathImpl`
copies and exposes a mutable list. `ConfigRepository.initialize_sources()` resolves
and constructs each source. `_process_config_searchpath()` copies the path, appends
config/override entries, reinitializes sources and calls availability methods.
These are the concrete source/provenance integration points.
Literal caller selections need invocation provenance retained before aliases are
expanded; saved/config-authored entries remain requests. Private typed origin
markers preserve the public element/override APIs and survive deep copies;
matching a provider string is not authority.

`Plugins` currently discovers in its constructor. Registration populates
`SourcesRegistry` too. Initializer cleanup restores GlobalHydra alone. Lifecycle
cleanup can therefore land independently by making registry construction lazy,
keeping discovery on consumers, and restoring the two plugin-owned maps.
The later authorization code can reuse that same scope rather than add a second
registry lifecycle.

The existing execution context supports additive grants, explicit replacement,
unsafe sentinel serialization and overlapping policy contexts. Preserve those
behaviors through the shared implementation. Existing internal-object guards
identify objects defined under `hydra._internal`; the new ContextVar identity must
also join the existing protected-object snapshot. Public aliases must resolve
to those protected implementations rather than introduce unguarded wrappers.

Worker source inspection confirms that Joblib and Submitit restore singleton
state before run_job; Joblib currently calls setup_globals first. BasicLauncher
also composes sweep configs. All three receiving paths need the policy installed
before these operations. A launcher capability declaration plus the existing
trusted transport can expose missing integration without a signing protocol.

## Bounded probe

Run [engineering-probe.py](engineering-probe.py) with the repo-local interpreter.
The canonical observed output is [engineering-probe-results.json](engineering-probe-results.json).
On Python 3.14.0, directory-backed resources are pathlib paths, zip-backed
resources are zipfile.Path with package-relative `at`, and EntryPoint.module/attr
can be inspected without importing the selected module. No process or payload
was executed. This probes standard-library foundations, not the proposed guards.

The current stdlib FileReader and ZipReader return those two root types.
CompatibilityFiles retains rooted ResourceReader access; preserving its existing
single-string join is important because its SpecPath accepts one argument.
Pure namespace roots are already rejected by Hydra's regular-package check;
a regular package under a namespace parent remains supported. Existing
`tests/test_pkg_config_source.py` covers source, compiled initializer, zip and
namespace-parent packages. Those tests were inspected, not rerun for this design.
No Windows, supported-version matrix, compiled build or performance result is claimed.

The refreshed probe also registers a dataclass in ConfigStore and passes it as
instantiate input. Each conversion calls its harmless default factory once.
This is why the config-load guard must cover ConfigStore conversion and
instantiate's structured-input conversion, not only file/package readers.
The probe modifies only its disposable process state and temporary resource
files. It does not implement the guard, grant permissions, or execute a payload.

## Engineering choices and publication prerequisite

Reuse one private authorization module for effective policy, lifecycle and worker
state, plus one small root-check helper shared by built-in source implementations.
Keep existing test modules. Exact selector parsing, path normalization, registry
restoration, provenance copies and worker ordering are resolved in the plan;
no upstream policy correction or new owner tradeoff was needed.
The regular public module, per-field replace marker, per-category release
defaults, config-load guard and entry-name selectors now follow the approved
HLD. Context-local registration overlays use immutable payload replacement so
copied contexts do not share mutable grant sets. Worker fallback is allowed only
when every relevant category is LEGACY; Basic/Joblib/Submitit own the receiving
integration and other launchers must satisfy the contract before checked use.

Containment, lifecycle cleanup and namespace warnings can land independently.
Keep authorization commits together until source/plugin checks, workers and the
public activation are integrated. Do not publish a restricted-mode promise from
an intermediate commit. This avoids temporary flags or duplicated implementations.

Issue/PR numbers have not been allocated for this feature. Opening an issue or PR
is outside authoring authorization. News fragments remain required at delivery.
Before admitting a delivery slice, allocate the authorized publication identifiers,
add its exact numeric fragment path to the owning inventory item, and refresh the
affected plan review. Do not invent an issue number or commit a placeholder file.
This is external publication data, not an unresolved runtime rule or permission
to begin delivery. Uncommitted documents and growth-policy readiness are separate
pre-delivery prerequisites.
