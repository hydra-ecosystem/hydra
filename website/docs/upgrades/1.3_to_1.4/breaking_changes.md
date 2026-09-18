---
id: breaking_changes
title: Current breaking changes
---

Hydra 1.4 and OmegaConf 2.4 are still under development. This page is a
working inventory of changes currently known to require application updates.
It is derived from their news fragments, may change, and may not yet be
complete. The final release notes will be the authoritative list.

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
- Launcher and sweeper plugin configurations are instantiated
  non-recursively.
- Entry points are the preferred plugin discovery mechanism. Legacy
  `hydra_plugins` namespace scanning remains available in 1.4 but is
  deprecated. See [Plugin discovery with entry points](/docs/upgrades/1.3_to_1.4/plugin_discovery).
- Some security-sensitive modules can no longer be instantiated by default.
  This restriction is not a security boundary; do not rely on it to make
  untrusted configurations safe.

## OmegaConf 2.4

- Python 3.6, 3.7, 3.8, and 3.9 are no longer supported. OmegaConf requires
  Python 3.10 or newer.
- Native tuples create immutable `TupleConfig` values instead of mutable
  `ListConfig` values, and conversion returns tuples instead of lists. See the
  [OmegaConf tuple migration guide](https://omegaconf.readthedocs.io/en/latest/tuple_migration.html).
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
- A backslash immediately before a key-path delimiter now escapes that
  delimiter. This changes the interpretation of key paths involving keys whose
  names end in a backslash.
