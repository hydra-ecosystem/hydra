# Config-source research

This is the canonical supporting summary for this design. It records observations
and their limits; it is not an approval, review stamp, or product specification.

## Existing implementation

The authoring checkout's current revision is recorded in [status](status.md).
Relevant inspected paths are:

- `hydra/main.py`: `hydra.main()` owns initialization around application startup
  and separately accepts an execution whitelist.
- `hydra/initialize.py`: the initializer variants select config sources. The list
  initializer validates ordered URI input but does not currently authorize or
  prohibit additional sources selected by config contents.
- `hydra/compose.py`: `compose()` uses the shared config loader; removing the
  `hydra` node from the returned result happens after composition.
- `hydra/_internal/config_loader_impl.py`: config/override `hydra.searchpath`
  entries are appended before source reinitialization and availability checks.
- `hydra/_internal/config_repository.py`: constructing a source calls the selected
  provider class. Checks after that construction can be too late.
- `hydra/_internal/core_plugins/importlib_resources_config_source.py`: the
  package-backed source imports its package to locate YAML resources.
- `hydra/_internal/core_plugins/structured_config_source.py`: a nonempty module
  name is imported in the constructor; the empty built-in source reads already
  registered ConfigStore entries.
- `hydra/_internal/core_plugins/file_config_source.py`: filesystem YAML lookup is
  a different mechanism from selecting a Python-backed config source. Do not
  infer a filesystem containment guarantee from a source URI list.
- `website/docs/advanced/search_path/hydra_searchpath.md`: config-selected sources
  are currently added after initialization sources. The list initializer is not
  currently an authorization boundary.

The original source-searchpath feature included Compose tests in
[commit 5647661f1202e4058ddef9e5d2b5228d42f421db](https://github.com/hydra-ecosystem/hydra/commit/5647661f1202e4058ddef9e5d2b5228d42f421db),
committed 2021-03-05. Compose support was not a separate recent addition.

The ordered list initializer was introduced in
[commit 89807176e21946657b94b6908d0692dd5de24546](https://github.com/hydra-ecosystem/hydra/commit/89807176e21946657b94b6908d0692dd5de24546),
committed 2026-09-28. It is a useful existing primitive, not a completed source
authorization implementation.

## Real usage and trust assumptions

- [Hydra's 1.3 searchpath example](https://github.com/hydra-ecosystem/hydra/blob/v1.3.7/website/versioned_docs/version-1.3/advanced/search_path.md)
  selects `pkg://additional_conf` from a package beside the app script.
- [tuPlan Garage's setup and launch instructions](https://github.com/autonomousvision/tuplan_garage/blob/b51d5d04fac1bd4389653b9ab2ff73ea88f435a3/README.md#L104)
  use an editable checkout and package config sources.
- [mmlearn's user guide](https://github.com/VectorInstitute/mmlearn/blob/6edd2108e5d09713a13c2b256a99e858d1f77abc/docs/user_guide.md#L247)
  describes a user config package whose initializer imports components for
  registration. `pkg://` can therefore expose YAML and cause dataclass
  registrations during initialization.
- [MatterGen's checkpoint info](https://github.com/microsoft/mattergen/blob/92423660a8bd70e83679086e88f88596d484dc16/mattergen/common/utils/data_classes.py#L49)
  downloads model config YAML and composes it through the config property.
  Model loading is not limited to direct OmegaConf loading.
- [FAIRChem's inference loader](https://github.com/facebookresearch/fairchem/blob/1d408a1138ddfb76e0a9d64e2e055d73339fbeba/src/fairchem/core/units/mlip_unit/utils.py#L40)
  directly instantiates saved checkpoint config. It illustrates a different
  model-loading path; it does not establish ecosystem prevalence.

These are pinned source observations, not full application executions, claims
about every version, or evidence of an unintended security effect. The broader
prior survey was deliberately selected and does not establish what most users
do. This design does not require that statistical claim.

## Python path and startup distinction

`pkg://` and named `structured://` use Python import availability, which can
include user source trees exposed through `PYTHONPATH`. Such code need not be
installed. Config-source selection does not itself install code or necessarily
add a new Python import path.

[Python's site documentation](https://docs.python.org/3.14/library/site.html)
describes executable `.pth` lines in processed site directories. A `.pth` file
in an arbitrary source directory is not executed merely because the directory
is importable. The design cannot justify a permission grant by equating those
two kinds of access.

## Automatic plugin imports

An owner-requested follow-up inspected `hydra/core/plugins.py`,
`hydra/_internal/utils.py`, and the plugin development/migration guides before
advancing requirements or architecture approval.

`Plugins` initializes during config searchpath construction, before the primary
config is composed. Discovery imports eligible modules under the importable
`hydra_plugins` namespace and then inspects their contents for plugin classes.
A module need not define a valid plugin class for its top-level code to have
already executed. This namespace can include uninstalled source directories on
the Python import path.

The current checkout additionally loads every discovered `hydra.plugins` entry
point with `entry_point.load()`, which imports its target module before class
validation. Registered plugin discovery is therefore also code execution,
including for plugins that the application does not subsequently select.
SearchPathPlugin objects are then instantiated and their searchpath hooks run
before primary config composition.

A harmless fresh-subprocess check created only a local namespace module named
`hydra_plugins/source_authorization_probe.py`, containing:

```python
import builtins
builtins.HYDRA_AUTODISCOVERY_SENTINEL = True
```

The child ran from that temporary source directory using `python -m`, imported
Hydra, verified the sentinel was initially absent, and called
`initialize(config_path=None)`. The sentinel became true during initialization.
No config was composed, no plugin was selected, no plugin class was defined,
and no probe distribution was installed. This occurred with both extracted
Hydra 1.3.7 wheel source and the current authoring checkout, which reported
1.4.0rc4. `PYTHONPATH` selected the Hydra source version; the probe directory
was available through the ordinary module invocation's working-directory path.
The probe used no process/shell payload, network access, or harmful action.

This confirms ambient plugin import reachability, not an end-to-end consumer
exploit. Under a threat model that trusts auto-discovered plugin code, it is an
existing trust assumption. If an attacker can create a discoverable plugin on
the process's import path, config-source authorization cannot prevent that
earlier execution. A YAML-only source policy must not claim otherwise.

[Plugin discovery implementation](https://github.com/hydra-ecosystem/hydra/blob/main/hydra/core/plugins.py)
and the [migration guide](https://github.com/hydra-ecosystem/hydra/blob/main/website/docs/upgrades/1.3_to_1.4/plugin_discovery.md)
document the namespace scan and entry-point support. Namespace discovery is
deprecated in 1.4; the guide says it may be removed in a later release, not that
it has already been removed or that a particular removal version is committed.

This investigation raised whether discovery would remain trusted ambient code.
Subsequent owner discussion added explicit plugin controls, context cleanup,
worker propagation, and a namespace-discovery switch to the shared-policy design
in R11-R14. The investigation itself did not establish policy or phase approval.
Config-selected imports outside plugin discovery remain a separate check within
the same design.

## Basic containment feasibility

The current `hydra/_internal/core_plugins/file_config_source.py` already resolves
paths with `os.path.realpath()` in `load_config()`, `is_group()`, `is_config()`,
and `list()`. It does not check resolved ancestry against the selected source
root. This supports considering an incremental path check for a trusted, stable
filesystem; it is not evidence of an existing containment guarantee.

Python documents native path resolution and its platform-specific behavior in
[os.path.realpath](https://docs.python.org/3.14/library/os.path.html#os.path.realpath).
Lexical ancestry alone does not resolve links or traversal, as explained in
[pathlib](https://docs.python.org/3.14/library/pathlib.html#pathlib.PurePath.is_relative_to).
A resolve/check/open sequence is not an atomic containment operation against
concurrent filesystem replacement.

The owner accepted R10's per-source containment: internal links allowed and
external links refused. No implementation, performance benchmark, or live
Windows validation has been run for that requirement. Expectations of modest
incremental overhead are an engineering assessment, not a measured result.

The owner subsequently accepted containment for `pkg://` resources and immediate
containment errors in Hydra 1.4. The current package source uses
`importlib.resources.files(package).joinpath(config_path)`, supporting both
directory and archive resources. Python documents the abstract resource model in
[importlib.resources](https://docs.python.org/3.14/library/importlib.resources.html).
The implementation must therefore distinguish a physical directory root from a
package subtree in an archive; granting a package source does not imply granting
the whole archive. No implementation or runtime benchmark has been performed.

## Finite engineering investigations for later phases

- Trace every built-in entry point that initializes or inspects config sources,
  including reinitialization, contexts, plugins, and help/inspection calls.
- Define exact source-grant identity, URI normalization, and any descendant
  matching using current source semantics, without importing to authorize.
- Determine where explicit source selections are retained separately from
  config-supplied requests and how per-call opt-out state is restored.
- Define a coherent compatibility/restricted-mode transition and caller-specific
  diagnostic examples without committing to a release schedule.
- Resolve existing source-plugin integration and current Python registration
  behavior without claiming to sandbox trusted plugin code.
- Trace plugin/sources registries and worker singleton restoration; identify
  where authorization must be established before discovery and how prior scope
  visibility is restored, including failed initialization.
- Specify directory and archive resource-root checks across existing platforms,
  with the accepted immediate 1.4 containment errors and stable-filesystem limit.

These investigations belong to the approved HLD/implementation-plan phases.
They are not permission to begin product implementation.
