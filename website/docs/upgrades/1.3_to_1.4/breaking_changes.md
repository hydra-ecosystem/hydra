---
id: breaking_changes
title: Current breaking changes
---

This page is the current migration inventory for Hydra 1.4 and OmegaConf 2.4.
It is derived from Hydra's news fragments and OmegaConf's release notes, may
change, and may not yet be complete. The final release notes will be the
authoritative list.

## Hydra 1.4

- Python 3.7, 3.8, and 3.9 are no longer supported. Hydra requires Python 3.10
  or newer.
- The unsupported Torchrun launcher and the `contrib` plugin area have been
  removed.
- The experimental `on_compose_config` callback has been removed. It was never
  included in a stable Hydra release, but was available in Hydra 1.4
  development versions from February 2025 through July 2026.
- The experimental `LogJobReturnCallback` is now a warning-emitting no-op.
  Hydra logs task exceptions to per-job logs without it. Logging successful
  return values is deliberately no longer built in; log them in your
  application or a custom `on_job_end` callback if needed. Remove the callback
  from your configuration; it will be removed in Hydra 1.5.
- Parent traversal in Defaults List config paths is no longer accepted.
- Backslashes in Defaults List config paths are no longer accepted. `/` is the
  only supported config group separator. Paths that used `\` previously
  composed on Windows only, where the operating system resolved the backslash
  as a filesystem separator.
- Defaults List options containing `/` are normalized to a nested config group.
  For example, `foo: bar/baz` becomes `foo/bar: baz`, changing the override key
  to `foo/bar` and the default package to `foo.bar`. See
  [Slash in default option normalization](/docs/upgrades/1.3_to_1.4/slash_in_default).
- Defaults List interpolations can reference selected config groups, including
  relocated groups, but cannot invoke OmegaConf resolvers. Move resolver-based
  selection into application code or pass a concrete config-group override.
- The optional `hydra.mode` is no longer effective when set in a config other
  than the primary config. A conflicting mode from a config group raises an
  error rather than being silently ignored. Interpolations that require
  Defaults List composition also cannot select the mode. Move such a value to
  the primary config or pass `hydra.mode=RUN` or `hydra.mode=MULTIRUN` on the
  command line.

### Deprecations

- `version_base` is deprecated and will be removed in Hydra 1.5. Explicit values,
  including `None`, emit `Hydra15MigrationWarning`; values below `"1.3"` are
  rejected. Omit it when running on Hydra 1.4. See
  [Preparing for Hydra 1.4](/docs/upgrades/1.3_to_1.4/prepare_for_1_4)
  for applications that still need to run on Hydra 1.3.
- Using `_target_: functools.partial` is deprecated. Set `_target_` to the
  effective callable and use `_partial_: true` instead. Direct
  `functools.partial` targets will become an error in Hydra 1.5.
- `hydra.job.override_dirname` is deprecated. Replace
  `${hydra.job.override_dirname}` with `${hydra_override_dirname:}`. See
  [hydra.job.override_dirname](/docs/upgrades/1.3_to_1.4/hydra_job_override_dirname).
- Legacy `hydra_plugins` namespace scanning is deprecated. Register plugins
  through [entry points](/docs/upgrades/1.3_to_1.4/plugin_discovery).

### Execution whitelist

Resolving config-selected Python targets without an execution whitelist supplied
by trusted Python code emits a warning in Hydra 1.4 and will become an error in
Hydra 1.5. This applies to `instantiate()` and Python logging configured by
Hydra. See the [execution whitelist migration guide](/docs/upgrades/1.3_to_1.4/execution_whitelist).

Logging configuration remains trusted. The whitelist controls callable selection;
it does not restrict where log files are written.

### Range sweep casting

`int(range(...))` and `float(range(...))` now cast each generated value,
preserving the element count and duplicates. Previously they cast the range's
`start`, `stop`, and `step`, which could change the sequence or truncate the step
to zero.

| Expression | Hydra 1.3 | Hydra 1.4 |
| --- | --- | --- |
| `int(range(0,5,1.5))` | `[0,1,2,3,4]` | `[0,1,3,4]` |
| `int(range(0,1.1))` | `[0]` | `[0,1]` |
| `int(range(0,1,0.1))` | Zero-step error | Ten zeros |

To keep the former sequence in the first example, use `range(0,5,1)` explicitly.

Casting preserves the `RangeSweep` and its original bounds and step. The cast
is applied lazily during iteration. Code using the override parser should
enumerate it with `Override.sweep_iterator()` to obtain the transformed values.
Nested casts are applied in order. Ordinary, uncast ranges retain their
existing behavior. Sweeper integrations should consume the transformed values
through `Override.sweep_iterator()` rather than reconstructing a cast range
from its bounds and step.

### Optuna range sweeps

The Optuna Sweeper now preserves a range's discrete values and exclusive stop,
including descending and sorted float ranges. Previously, `range(1,3)` could
sample `3`; it now permits only `1` and `2`. Use `range(1,4)` to retain that
former search space. Empty ranges and zero steps are rejected.

Cast ranges use categorical distributions containing the generated, cast
values. This supports the core element-wise casting behavior described above.
GridSampler now includes all values in a discrete distribution, including its
upper endpoint and singleton distributions.

At floating-point precision boundaries where an exact numeric Optuna
distribution is not representable, the sweeper preserves the range values in
a categorical distribution. Ordinary representable uncast ranges remain
numeric; the precision fallback may enumerate the affected range.

### ConfigStore registrations

Replacing an existing ConfigStore registration without an explicit `replace`
argument emits `Hydra15MigrationWarning` in Hydra 1.4. Replacement still happens,
unless warnings are configured as errors. Set `replace=True` for intentional
replacement or `replace=False` to reject collisions. Omitting `replace` on a
collision will become an error in Hydra 1.5. See
[ConfigStore collision handling](/docs/upgrades/1.3_to_1.4/config_store_collisions).

This can also warn when the main script registers configs at module level and
is later imported by name, for example to resolve an instantiation target.
Python loads it separately as `__main__` and as the named module, repeating the
registrations. Move registrations into `if __name__ == "__main__":` before
calling the Hydra task. See
[Registering configs in the main script](/docs/upgrades/1.3_to_1.4/config_store_collisions#registering-configs-in-the-main-script).

### Hydra 1.1 compatibility behavior

`version_base="1.1"` is no longer accepted, and the following legacy behavior
has been removed:

- Omitting `config_path` no longer adds the calling directory to the config
  search path.
- `hydra.job.chdir` defaults to `False`.
- Config files using the `.yml` extension are rejected; use `.yaml`.
- The old `{group: option, optional: true}` Defaults List syntax is rejected;
  use `optional group: option`.
- Defaults List entries that replace Hydra config groups require the
  `override` keyword.
- Indexed Defaults List interpolations such as `${defaults.0.dataset}` are no
  longer accepted.
- `_group_` and `_name_` are no longer expanded as symbolic package values.
- The `strict` argument to `hydra.compose()` has been removed.
- ConfigStore schemas are no longer matched automatically by config name. Use
  explicit schema extension in the Defaults List.

### Hydra 1.2 migration behavior

`version_base="1.2"` is no longer accepted, and the following migration paths
have been removed:

- `hydra.types.TargetConf` has been removed. Use a Structured Config with a
  `_target_` field.
- The `hydra.experimental` compose and initialization APIs have been removed.
  Import them from `hydra`.
- `hydra.job.chdir=null` is no longer accepted. Set it to `True` or `False`.
- Direct callers of the internal `run_job()` API must pass `hydra_context`.
- Third-party Sweepers must use the `HydraContext` supplied to `setup()` to
  access the config loader.
- Optuna Sweeper's deprecated `hydra.sweeper.search_space` configuration has
  been removed. Use `hydra.sweeper.params`.

### Instantiation

- Direct calls to `hydra.utils.instantiate()` now propagate target exceptions
  with their original type and chain instead of wrapping them in
  `InstantiationException`. Catch the target's exception type if your code
  handles these failures.
- `InstantiationException` now inherits directly from `HydraException`, not
  `CompactHydraException`. Code that catches `CompactHydraException` to handle
  Hydra-generated instantiation failures must catch `InstantiationException`
  explicitly.
- A `dict` or `DictConfig` call-site argument to `hydra.utils.instantiate()`
  replaces a plain mapping configured for that target parameter instead of
  merging into it. As an exception, a dictionary overriding a Structured Config
  node is merged and schema-validated. Configured target values also retain
  merge behavior, regardless of whether recursive instantiation is enabled. See
  [Instantiate resolution and call-site overrides](/docs/upgrades/1.3_to_1.4/instantiate_resolution).
- `hydra.utils.instantiate()` passes dataclass and attrs instances supplied as
  call-site arguments through unchanged instead of interpreting them as
  Structured Configs.
- `hydra.utils.instantiate()` rejects `???` and interpolation syntax in plain
  Python call-site overrides. Supply concrete runtime values or explicit
  OmegaConf containers instead.
- `hydra.utils.instantiate()` resolves interpolations during recursive
  traversal instead of resolving the entire configuration before
  instantiation. With `_recursive_=False`, `_convert_="none"`, and no call-site
  overrides, Config containers are passed through without a final copy. See
  [Instantiate resolution and call-site overrides](/docs/upgrades/1.3_to_1.4/instantiate_resolution).
- During instantiation without call-site overrides, Hydra temporarily makes the
  source configuration read-only and restores its previous state afterward.
  Constructors that intentionally mutate it must opt in with OmegaConf's
  `read_write()` context manager. See
  [Instantiate resolution and call-site overrides](/docs/upgrades/1.3_to_1.4/instantiate_resolution).
- Hydra `_partial_` factories cannot be pickled. Construct the object before
  serialization, if its type supports pickling, or recreate the factory in the
  receiving process.
- Launcher and sweeper plugin configurations are instantiated
  non-recursively.
- Some security-sensitive modules can no longer be instantiated by default.
  This restriction is not a security boundary; do not rely on it to make
  untrusted configurations safe.

### Experimental rerun

`PickleJobInfoCallback` has been removed. Remove it from `hydra.callbacks`.
`--experimental-rerun` now takes a job output directory containing
`.hydra/hydra.yaml` and `.hydra/overrides.yaml`, rather than a pickle file.
It recomposes from the current project's config sources and saved overrides;
saved `config.yaml` values are not loaded. See
[Re-run a job from its output directory](/docs/experimental/rerun).

### Bundled plugins and Configen

Upgrade bundled plugins alongside Hydra. Their current versions require
`hydra-core>=1.4.0.dev1,<1.5.0.dev0` and cannot be used with Hydra 1.3.
`hydra-configen` also requires Hydra 1.4 or newer.

| Plugin | Dependency changes |
| --- | --- |
| Ax Sweeper | Python 3.11–3.14; `ax-platform>=1.2.4,<1.3.0`; `torch>=2.2` |
| Joblib Launcher | `joblib>=1.5.3` |
| Nevergrad Sweeper | `nevergrad>=1.0.12` |
| Optuna Sweeper | `optuna>=4.9.0,<6.0.0` |
| RQ Launcher | `fakeredis>=2.36.2,<3`; `rq>=2.10.0,<3` |
| Submitit Launcher | `submitit>=1.5.0` |

Hydra 1.4 includes the final first-party Ax Sweeper release. The plugin will be
removed in Hydra 1.5; see [Ax Sweeper retirement](/docs/plugins/ax_sweeper).

The Optuna `motpe` sampler is no longer supported. Use
`hydra/sweeper/sampler=tpe`, which supports multi-objective optimization.
Nevergrad's `hydra.sweeper.parametrization` is deprecated and will be removed
in Hydra 1.5. Move search-space entries to `hydra.sweeper.params`; see
[Nevergrad Sweeper search-space configuration](/docs/upgrades/1.3_to_1.4/nevergrad_sweeper).

### Testing and error reporting

- `hydra.test_utils.test_utils.assert_regex_match()` has been removed. Use
  `assert_multiline_regex_search()`; add anchors if a full-string match is
  required.
- Hydra no longer suggests `HYDRA_FULL_ERROR=1` after a sanitized error.
  The variable still disables traceback sanitization; see the
  [developer guide](/docs/development/overview).

## OmegaConf 2.4

- Direct assignment and typed-container mutation warn when they implicitly
  convert a value to another type. Pass values of the declared type; for an
  assignment that needs conversion, use `OmegaConf.update()`. Assigning a
  structured-config object remains unchanged. Configuration loading, merges,
  and command-line overrides continue to support conversion.
  See [OmegaConf #459](https://github.com/hydra-ecosystem/omegaconf/issues/459).
- Python 3.6, 3.7, 3.8, and 3.9 are no longer supported. OmegaConf requires
  Python 3.10 or newer.
- Native tuples create immutable `TupleConfig` values instead of mutable
  `ListConfig` values, and conversion returns tuples instead of lists. See the
  [OmegaConf tuple migration guide](https://omegaconf.readthedocs.io/en/latest/tuple_migration.html).
- `DictConfig` and `ListConfig` are unhashable and cannot be dictionary keys or
  set elements. Use a separate immutable key instead.
- `OmegaConf.create(None)` returns `None` instead of a `DictConfig` wrapping
  `None`.
- `OmegaConf.get_type()` returns `NoneType` for nodes containing `None`, and
  `None` and `NoneType` annotations are validated.
- `OmegaConf.resolve()` raises `InterpolationToMissingValueError` when an
  interpolation dereferences a missing (`???`) value instead of replacing the
  node with `???`.
- `OmegaConf.to_container(..., resolve=True)` resolves a custom resolver at
  most once per resolved node during a conversion pass. Code relying on
  repeated side effects from the same resolver may behave differently.
- `OmegaConf.register_resolver()` is the canonical custom resolver API.
  `OmegaConf.register_new_resolver()` and
  `OmegaConf.legacy_register_resolver()` are deprecated. When migrating a
  legacy resolver, check argument parsing and caching behavior.
- Custom resolvers now warn when their arguments or return values do not match
  their annotations. Correct the annotations or values, or choose an explicit
  `annotation_validation` policy when registering the resolver.
- `OmegaConf.missing_keys()` no longer evaluates custom resolvers by default.
  Pass `resolve_custom_resolvers=True` when this evaluation is required.
- Typed container and union interpolations are validated and converted against
  their destination type on lazy access. Values that previously bypassed
  validation may now raise an error.
- Plain `???` returned by a resolver is treated as missing on access. Return
  `r"\???"` when the intended value is the literal string `???`.
- Integer-looking key paths can resolve integer dictionary keys. Configurations
  reject ambiguous pairs such as `1` and `"1"`; use one key representation.
- YAML loading limits alias expansion by default. Large configurations that
  exceed the limit must be simplified or use an explicit higher
  `OMEGACONF_MAX_YAML_EXPANDED_NODES` limit for trusted input.
- A backslash immediately before a key-path delimiter now escapes that
  delimiter. This changes the interpretation of key paths involving keys whose
  names end in a backslash.
