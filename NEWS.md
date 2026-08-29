1.3.6 (2026-08-29)
==================

### Bug Fixes

- Harden instantiate authorization against unsafe aliases and callable results.
  ([#3410](https://github.com/facebookresearch/hydra/issues/3410))
- Apply Hydra's target blocklist to Python logging configuration.
  ([#3418](https://github.com/facebookresearch/hydra/issues/3418))


1.3.5 (2026-08-06)
==================

### API Change (Renames, deprecations and removals)

- Warn Hydra 1.3 applications that rely on Hydra 1.1 compatibility before
  upgrading to Hydra 1.4. ([#3334](https://github.com/facebookresearch/hydra/issues/3334))
1.3.4 (2026-07-05)
==================

### Bug Fixes

- Add an instantiate target blocklist for security-sensitive callables. ([#3259](https://github.com/facebookresearch/hydra/issues/3259))
1.3.3 (2026-06-11)
==================

### Bug Fixes

- Remove the setup.py dependency on pkg_resources for source builds. ([#3207](https://github.com/facebookresearch/hydra/issues/3207))


1.3.2 (2023-02-22)
==================

### Features

- Add a `hydra.utils.get_object` function that gives users access to Hydra's dotpath-lookup machinery. ([#2139](https://github.com/facebookresearch/hydra/issues/2139))
- Allow config_path to specify a non-relative module path, by starting with `pkg://` ([#2564](https://github.com/facebookresearch/hydra/issues/2564))

### Maintenance Changes

- Drop support for python3.6 ([#2304](https://github.com/facebookresearch/hydra/issues/2304))


1.3.1 (2022-12-20)
==================

### Bug Fixes

- Relax OmegaConf pin allowing OmegaConf 2.3 to be installed ([#2510](https://github.com/facebookresearch/hydra/issues/2510))


1.3.0 (2022-12-08)
==================

### Features

- Implement `_convert_="object"` option for `instantiate`, enabling conversion of non-`_target_` structured configs to instances of the backing dataclass / attr class. ([#1719](https://github.com/facebookresearch/hydra/issues/1719))
- Enable layering of the `@hydra.main` decorator on top of other decorators produced using `functools.wraps`. ([#2303](https://github.com/facebookresearch/hydra/issues/2303))
- Allow for non-leading dashes in override keys ([#2363](https://github.com/facebookresearch/hydra/issues/2363))
- support specifying an absolute path with `--config-path` ([#2368](https://github.com/facebookresearch/hydra/issues/2368))
- Support python3.11 ([#2443](https://github.com/facebookresearch/hydra/issues/2443))

### Bug Fixes

- Fix an issue where Hydra's exception-handling logic could raise an `AssertionError` ([#2342](https://github.com/facebookresearch/hydra/issues/2342))


1.2.0 (2022-05-17)
==================

### Bug fixes

- `hydra.runtime.choices` is now updated correctly during multi-run ([#1882](https://github.com/facebookresearch/hydra/issues/1882))
- `hydra.verbose=True` now works with multirun. ([#1897](https://github.com/facebookresearch/hydra/issues/1897))
- Fix a resolution error occurring when a nested class is passed as a `_target_` keyword argument to `instantiate` ([#1914](https://github.com/facebookresearch/hydra/issues/1914))
- It is now possible to pass other callable objects (besides functions) to `hydra.main`. ([#2042](https://github.com/facebookresearch/hydra/issues/2042))

### New features

- Add support to Hydra's instantiation API for creation of `functools.partial` instances via a `_partial_` keyword. ([#1283](https://github.com/facebookresearch/hydra/issues/1283))
- Support defining basic sweeping in input config. ([#1376](https://github.com/facebookresearch/hydra/issues/1376))
- Improve error message with more context when an omegaconf exception occurs during the config merge step. ([#1697](https://github.com/facebookresearch/hydra/issues/1697))
- Add `--experimental-rerun` command-line option to reproduce pickled single runs ([#1805](https://github.com/facebookresearch/hydra/issues/1805))
- Add experimental Callback for pickling job info. ([#2092](https://github.com/facebookresearch/hydra/issues/2092))
- Implement tab completions for appending to the defaults list (+group=option) and deleting from the defaults list (~group). ([#1841](https://github.com/facebookresearch/hydra/issues/1841))
- Enable the use of the pipe symbol `|` in unquoted strings when parsing command-line overrides. ([#1850](https://github.com/facebookresearch/hydra/issues/1850))
- Support for Python 3.10 ([#1856](https://github.com/facebookresearch/hydra/issues/1856))
- Improve clarity of error messages when `hydra.utils.instantiate` encounters a `_target_` that cannot be located ([#1863](https://github.com/facebookresearch/hydra/issues/1863))
- The `instantiate` API now accepts `ListConfig`/`list`-type config as top-level input. ([#1950](https://github.com/facebookresearch/hydra/issues/1950))
- Improve error messages raised in case of instantiation failure. ([#2099](https://github.com/facebookresearch/hydra/issues/2099))
- Add callback for logging JobReturn. ([#2100](https://github.com/facebookresearch/hydra/issues/2100))
- Support disable changing working directory at runtime. ([#910](https://github.com/facebookresearch/hydra/issues/910))
- Support setting hydra.mode through config. ([#394](https://github.com/facebookresearch/hydra/issues/394))

### Behavior changes

- The antlr version requirement is updated from 4.8 to 4.9, to align better with current antlr versions
- If user code raises an exception when called by `instantiate`, raise an `InstantiateError` exception instead of an instance of the same exception class that was raised by the user code. ([#1911](https://github.com/facebookresearch/hydra/issues/1911))
- Remove support for deprecated arg `config_loader` to Plugin.setup, and update signature of `run_job` to require `hydra_context`. ([#1953](https://github.com/facebookresearch/hydra/issues/1953))

The remaining changes are protected by the new [version_base](https://hydra.cc/docs/upgrades/version_base/) support,
which allows one to either configure Hydra to support older setups / config, or configure Hydra to use the following more modern defaults:

- Remove deprecated "old optional" defaults list syntax ([#1952](https://github.com/facebookresearch/hydra/issues/1952))
- Remove support for the legacy hydra override syntax (see [deprecation notice](https://hydra.cc/docs/upgrades/1.0_to_1.1/defaults_list_override/)). ([#2056](https://github.com/facebookresearch/hydra/issues/2056))
- Remove support for old hydra.experimental.{compose,initialize} interface
- Remove support for `_name_` and `_group_` from package header (see [deprecation notice](https://hydra.cc/docs/upgrades/1.0_to_1.1/changes_to_package_header))
- Remove support for legacy default list interpolation format (see [deprecation notice](http://hydra.cc/docs/upgrades/1.0_to_1.1/defaults_list_interpolation))
- Remove support for TargetConf class
- Remove support for strict flag from compose API (see [deprecation notice](https://hydra.cc/docs/upgrades/0.11_to_1.0/strict_mode_flag_deprecated))
- Remove support for "*.yml" extensions, requiring "*.yaml" instead.
- Default to not changing the working directory at runtime. Use `hydra.job.chdir=True` to reinstate old behavior.
- Default to not adding any directory to the config path. (see [`config_path` options](https://hydra.cc/docs/upgrades/1.0_to_1.1/changes_to_hydra_main_config_path))


1.1.1 (2021-08-19)
==================

### Features

- Allow range() in override grammar to have only one argument (the stop value), e.g. range(3) ([#1664](https://github.com/facebookresearch/hydra/issues/1664))
- Add support for a HYDRA_DEPRECATION_WARNINGS_AS_ERRORS envorinment variable. When it is set, using deprecated features causes an exception instead of a warning. ([#1689](https://github.com/facebookresearch/hydra/issues/1689))
- To make migration from Hydra 1.0 to 1.1 easier, Hydra will now issue a warning if the primary config defines config values and Defaults List if the Defaults List does not specify `_self_` ([#1755](https://github.com/facebookresearch/hydra/issues/1755))

### API Change (Renames, deprecations and removals)

- Re-introduced a deprecated strict flag in the Compose API ([#1694](https://github.com/facebookresearch/hydra/issues/1694))
- Relax handling of legacy hydra overrides in the defaults list to make migration from Hydra 1.0 to 1.1 easier ([#1748](https://github.com/facebookresearch/hydra/issues/1748))

### Bug Fixes

- Allow Defaults List interpolation in nested configs and document that the interpolation keys must be absolute ([#1668](https://github.com/facebookresearch/hydra/issues/1668))
- instantiate API now supports `target` as a parameter name ([#1669](https://github.com/facebookresearch/hydra/issues/1669))
- Fix `--cfg=job --resolve` and `--help --resolve` so that the ${hydra:...} resolver now prints properly ([#1681](https://github.com/facebookresearch/hydra/issues/1681))
- Fix unexpected changes to defaults list in some cases when appending an experiment (+experiment=test) ([#1706](https://github.com/facebookresearch/hydra/issues/1706))
- Fixed composition where top level of a config composed from a config group is a list ([#1724](https://github.com/facebookresearch/hydra/issues/1724))
- Fix bug where overriding hydra config groups more than once without using the override keyword resulted in an error instead of deprecation warnings ([#1730](https://github.com/facebookresearch/hydra/issues/1730))
- Fix failure when sanitizing stack traces resulting from job exceptions ([#1739](https://github.com/facebookresearch/hydra/issues/1739))


1.1.0 (2021-06-09)
==================
This is the biggest Hydra release yet.  
#### Highlights
- OmegaConf 2.1 supports relative interpolations, nested interpolations, more powerful resolvers and better compatibility with plain Python dict and list.
- Recursive defaults list: Every config can now have a Defaults List.  
- Recursive instantiation: When instantiating objects using the `instantiate` API, nested defined objects are instantiated automatically.

There have also been many bug fixes and performance improvements, as well of as some breaking changes - both in Hydra and in OmegaConf.
Please check the API changes and deprecation sections in these release notes and in the OmegaConf release notes.

### Features
#### General enhancements
- Upgrade to OmegaConf 2.1. Please check the [release notes](https://github.com/omry/omegaconf/releases/tag/v2.1.0.rc1) for it ([#1426](https://github.com/facebookresearch/hydra/issues/1426))
- Support for Python 3.9. ([#1062](https://github.com/facebookresearch/hydra/issues/1062))
- Improve performance of config composition in a benchmark by 64% ([#1328](https://github.com/facebookresearch/hydra/issues/1328))
- Allow `@`, `$` and `?` symbols in unquoted values in overrides ([#1074](https://github.com/facebookresearch/hydra/issues/1074), [#1437](https://github.com/facebookresearch/hydra/issues/1437), [#1597](https://github.com/facebookresearch/hydra/issues/1597))
- Add a --resolve flag that can be used with the --cfg and --help flags to resolve interpolations before the config is printed. ([#1585](https://github.com/facebookresearch/hydra/issues/1585),[#1482](https://github.com/facebookresearch/hydra/issues/1482))
- It is now possible to disable Hydra's logging configuration ([#1130](https://github.com/facebookresearch/hydra/issues/1130))
- Support for Zsh tab completion ([#347](https://github.com/facebookresearch/hydra/issues/347))
- Support for force-add of config values via `++key=value` (force-add overrides if the value exists and adds it otherwise) ([#1049](https://github.com/facebookresearch/hydra/issues/1049))
- New experimental Callback API ([#1402](https://github.com/facebookresearch/hydra/issues/1402))

#### Config composition enhancements
- Support for Defaults List in any config (Recursive relative defaults) ([#1170](https://github.com/facebookresearch/hydra/issues/1170))
- Composition order of a config with a Defaults List can be specified with the `_self_` keyword. ([#326](https://github.com/facebookresearch/hydra/issues/326))
- Support for configuring the config search path from the primary config ([#274](https://github.com/facebookresearch/hydra/issues/274))
- Add support for selecting multiple configs from the same Config Group ([#499](https://github.com/facebookresearch/hydra/issues/499))  
- Final choices of defaults list are retained in the dictionary hydra.runtime.choices ([#956](https://github.com/facebookresearch/hydra/issues/956))

#### Object Instantiation enhancements
- Support for recursive instantiation with `hydra.utils.instantiate()` ([#566](https://github.com/facebookresearch/hydra/issues/566))
- Instantiate now fully supports positional arguments ([#1432](https://github.com/facebookresearch/hydra/issues/1432))
- Support for converting parameters to primitive containers during instantiation ([#1015](https://github.com/facebookresearch/hydra/issues/1015))
- It is now possible to override the `_target_` of instantiation with a Python type or a string ([#1017](https://github.com/facebookresearch/hydra/issues/1017))

### API Change (Renames, deprecations and removals)
#### General changes
- Default composition order change, see [this](https://hydra.cc/docs/upgrades/1.0_to_1.1/default_composition_order) for details ([#1217](https://github.com/facebookresearch/hydra/issues/1217))
- Remove deprecated strict flag from `@hydra.main` and the `Compose API` ([#1010](https://github.com/facebookresearch/hydra/issues/1010))
- Passing a config name as config_path to `@hydra.main` is now an error ([#1010](https://github.com/facebookresearch/hydra/issues/1010))
- Promote `hydra.experimental.{compose,initialize,initialize_config_dir,initialize_config_module}` out from the `hydra.experimental` module to the hydra module. ([#1030](https://github.com/facebookresearch/hydra/issues/1030))
- The override grammar now requires that, in quoted strings, any sequence of \ preceding a quote (either an escaped quote, or the closing quote) must be escaped ([#1600](https://github.com/facebookresearch/hydra/issues/1600))
- Support partial failures in MULTIRUN mode ([#1377](https://github.com/facebookresearch/hydra/issues/1377))
- Add `HydraContext` to `run_job` and Launcher/Sweeper's `setup` ([#1498](https://github.com/facebookresearch/hydra/issues/1498))
#### Instantiate changes
- Instantiate is now recursive by default, use `_recursive_=False` to disable recursive instantiation. ([#566](https://github.com/facebookresearch/hydra/issues/566))
- Deprecated TargetConf, you should no longer be extending or annotating with it ([#1010](https://github.com/facebookresearch/hydra/issues/1010))
- Remove ObjectConf and deprecated params support that was deprecated in Hydra 1.0 ([#1010](https://github.com/facebookresearch/hydra/issues/1010))
#### Plugins API changes
- HydraContext required in run_job, Launcher and Sweeper's setup methods, see issue for details ([#1498](https://github.com/facebookresearch/hydra/issues/1498))
- ConfigSourcePlugins needs to be modified to support recursive defaults, see link for details ([#1080](https://github.com/facebookresearch/hydra/issues/1080))

### Bug Fixes

- Hydra no longer erroneously changes the USER environment variable in pytest unit tests once installed ([#1059](https://github.com/facebookresearch/hydra/issues/1059))
- Fix a bug where Structured Config has a field like `list : Optional[List[int]] = None` ([#1117](https://github.com/facebookresearch/hydra/issues/1117))
- No longer modifies exception stack trace when running under a debugger ([#1237](https://github.com/facebookresearch/hydra/issues/1237))
- `hydra.job.{id,num}` are now properly passed to jobs in multirun ([#1270](https://github.com/facebookresearch/hydra/issues/1270))
- Add support for `%f` directive (microseconds) to the `${now:PATTERN}` resolver ([#1287](https://github.com/facebookresearch/hydra/issues/1287))
- Fixed a bug where tab completion did not work if the Defaults List had a missing (???) item. ([#1381](https://github.com/facebookresearch/hydra/issues/1381))
- Fix `+` overrides to properly insert new values into Structured Configs. ([#1515](https://github.com/facebookresearch/hydra/issues/1515))
- Fix edge cases where using the command line to set a key to a value containing a string ending with a backslash could crash ([#1600](https://github.com/facebookresearch/hydra/issues/1600))
- `--cfg=hydra` now works for read-only config ([#1461](https://github.com/facebookresearch/hydra/issues/1461))
- Change hydra.job_logging and hydra.hydra_logging to be non-optional ([#1656](https://github.com/facebookresearch/hydra/issues/1656))
- Configs with unicode characters are now working on Windows ([#1659](https://github.com/facebookresearch/hydra/issues/1659))

### Plugins

- Add [Optuna](https://optuna.org/) Sweeper plugin

### Improved Documentation

- New Defaults List [page](https://hydra.cc/docs/advanced/defaults_list) ([#1170](https://github.com/facebookresearch/hydra/issues/1170))
- New [Extending Configs](https://hydra.cc/docs/patterns/extending_configs/) pattern ([#1170](https://github.com/facebookresearch/hydra/issues/1170))
- Major updates to the [Packages](https://hydra.cc/docs/advanced/overriding_packages) page ([#1170](https://github.com/facebookresearch/hydra/issues/1170))
- New [Configuring Experiments](https://hydra.cc/docs/patterns/configuring_experiments/) pattern ([#1170](https://github.com/facebookresearch/hydra/issues/1170))
- Documentation updates for configuring search path ([#1449](https://github.com/facebookresearch/hydra/issues/1449))
- Documentation for `hydra.callbacks` ([#1526](https://github.com/facebookresearch/hydra/issues/1526))
- Document how to configure Hydra plugins ([#1582](https://github.com/facebookresearch/hydra/issues/1582))


1.0.7 (2021-07-14)
==================
This release contains a few small changes to make Hydra 1.0 a bit more compatible with OmegaConf 2.1 and Hydra 1.1 to enable easier migration.
There is no risk in using it if you are using 1.0.6 now as it just makes the migration a bit smoother in some scenarios:
1. If you are upgrading OmegaConf to 2.1 before upgrading Hydra to 1.1.
2. It enables some configs to be compatible with both versions in some rare cases related to the change in the default composition order in Hydra 1.1.

### Maintenance Changes

- Enables Hydra 1.0 to work with OmegaConf 2.1 (Manual installation of OmegaConf 2.1 is required) ([#1634](https://github.com/facebookresearch/hydra/issues/1634))
- Hydra 1.0 ignores `_self_` in Defaults List for partial future compatibility with Hydra 1.1 ([#1712](https://github.com/facebookresearch/hydra/issues/1712))


1.0.6 (2021-01-29)
==================

### Bug Fixes

- Fix interpolation in Hydra config node ([#1335](https://github.com/facebookresearch/hydra/issues/1335))

### Maintenance Changes

- Remove `Plugins` from `Singleton.get_state()` ([#1330](https://github.com/facebookresearch/hydra/issues/1330))


1.0.5 (2021-01-07)
==================

### Features

- Support Python 3.9 . ([#1062](https://github.com/facebookresearch/hydra/issues/1062))

### API Change (Renames, deprecations and removals)

- Deprecate support for renaming packages via the command line. ([#1140](https://github.com/facebookresearch/hydra/issues/1140))

### Bug Fixes

- Fixed hydra.job.id and hydra.job.num not getting passed to jobs in multirun ([#1270](https://github.com/facebookresearch/hydra/issues/1270))

### Plugins

- Support `additional_parameters` as an optional param in the Submitit launcher plugin.
- Add [Optuna](https://optuna.org/) Sweeper plugin

### Maintenance Changes

- Limit OmegaConf dependency to 2.0 versions ([#1253](https://github.com/facebookresearch/hydra/issues/1253))



1.0.4 (2020-11-17)
==================

### Bug Fixes

- Hydra no longer errorenously changes the USER environment variable in pytest unit tests once installed ([#1059](https://github.com/facebookresearch/hydra/issues/1059))
- Allow @ symbol in unquoted values in overrides ([#1074](https://github.com/facebookresearch/hydra/issues/1074))
- Fix a bug where Structured Config has a field like 'list : Optional[List[int]] = None` ([#1117](https://github.com/facebookresearch/hydra/issues/1117))
### Plugins
- Switch Ax Sweeper plugin to use new Hydra command line syntax
- Switch Nevergrad Sweeper plugin to use new Hydra command line syntax
- Revert the use of "_" to separate the path element in keys for the Ax sweeper plugin.


1.0.3 (2020-09-22)
==================

### Bug Fixes

- Fixed interaction between interpolation and instantiate ([#1001](https://github.com/facebookresearch/hydra/issues/1001))
- Fix float parsing for values where the exponent starts with 0 (e.g 1e-05) ([#999](https://github.com/facebookresearch/hydra/issues/999))


1.0.2 (2020-09-20)
==================
This is a small update improving support for config dataclasses generated by configen

### Features

- Overridden parameters annotated as Any in the config are not type checked by instantiate() ([#982](https://github.com/facebookresearch/hydra/issues/982))


1.0.1 (2020-09-15)
==================

### Features

- Add ability to escape special characters in unquoted command line values ([#954](https://github.com/facebookresearch/hydra/issues/954))

### Bug Fixes

- Add support for merging dicts and lists specified in the commend line ([#939](https://github.com/facebookresearch/hydra/issues/939))
- Fix appending dict values with new fields to config with + ([#946](https://github.com/facebookresearch/hydra/issues/946))
- Fix for Override Grammar integer parsing: Integers are now compatible with Python integers ('+' prefix, correct handling of '_') ([#954](https://github.com/facebookresearch/hydra/issues/954))

### Maintenance Changes

- Upgrade to OmegaConf 2.0.2 ([#755](https://github.com/facebookresearch/hydra/issues/755))


1.0.0 (2020-09-03)
==================
Hydra 1.0 is out!
See [blog post](https://hydra.cc/blog/2020/09/03/Hydra_1.0) for high level details.

Major new features in Hydra 1.0
* Config type safety via Structured Configs
* More powerful command line
* New plugins enabling remote launching and hyper parameter optimization
* Improved error reporting
* Reduce nesting levels with config packages

These release notes are covering the changes since 1.0.0rc4.

To see the complete release notes for 1.0 take a look at the release notes of:
- [1.0.0rc1](https://github.com/facebookresearch/hydra/releases/tag/v1.0.0rc1)
- [1.0.0rc2](https://github.com/facebookresearch/hydra/releases/tag/v1.0.0rc2)
- [1.0.0rc3](https://github.com/facebookresearch/hydra/releases/tag/v1.0.0rc3)
- [1.0.0rc4](https://github.com/facebookresearch/hydra/releases/tag/v1.0.0rc4)
- 1.0.0 (just below this line)

### Features

- Add support for casting interval to ints and floats ([#915](https://github.com/facebookresearch/hydra/issues/915))

### Bug Fixes

- Fix to flush logging instead of shutting it down at job end ([#833](https://github.com/facebookresearch/hydra/issues/833))
- compose() no longer initialized logging subsystem ([#833](https://github.com/facebookresearch/hydra/issues/833))
- Fix overriding of hydra.job.env_set from the command line ([#854](https://github.com/facebookresearch/hydra/issues/854))
- Fix tab completion to not output errors in some cases when using --multirun ([#856](https://github.com/facebookresearch/hydra/issues/856))
- Fix OmegaConf custom resolvers not being propagated to Sweepers properly ([#861](https://github.com/facebookresearch/hydra/issues/861))
- Interpolation accepts any char between ${ and } ([#891](https://github.com/facebookresearch/hydra/issues/891))
- Update the signature of hydra.utils.instantiate() allow input configs of Any type ([#896](https://github.com/facebookresearch/hydra/issues/896))
- Fix instantiate to work correctly when parameters are interpolations into a parent node ([#904](https://github.com/facebookresearch/hydra/issues/904))
- Apps will now raise underlying exception if env HYDRA_FULL_ERROR=1 ([#926](https://github.com/facebookresearch/hydra/issues/926))

### Plugins

- Fix integer/float choice from spec in the Nevergrad plugin

### Improved Documentation

- New page in Structured Configs tutorial: Static schema with many configs ([#918](https://github.com/facebookresearch/hydra/issues/918))
- New page in Structured Configs tutorial: Dynamic schema with many configs ([#918](https://github.com/facebookresearch/hydra/issues/918))


1.0.0rc4 (2020-08-18)
=====================
Be aware that `cfg.pretty()` is now deprecated and you should use `OmegaConf.to_yaml(cfg)` instead.

### Features

- Upgrade to OmegaConf 2.0.1rc12 ([#889](https://github.com/facebookresearch/hydra/issues/889))

### Bug Fixes

- Fix bug with bash autocompletion for the users who has `.` in their PATH environment variable ([#868](https://github.com/facebookresearch/hydra/issues/868))
- Fix instantiate to return None when None config is passed ([#887](https://github.com/facebookresearch/hydra/issues/887))


1.0.0rc3 (2020-08-17)
=====================

### Features

- Extended Override grammar supports range(),glob(),type casts,shuffle, sort and more. ([#752](https://github.com/facebookresearch/hydra/issues/752))
- Add support for specifying an additional config dir in the command line ([#874](https://github.com/facebookresearch/hydra/issues/874))
- Allow overriding of the `defaults` and `hydra` nodes in primary Structured Configs that does not mentioned `defaults` and `hydra`. ([#877](https://github.com/facebookresearch/hydra/issues/877))

### API Change (Renames, deprecations and removals)

- ObjectConf is deprecated for TargetConf. See [upgrade page](https://hydra.cc/docs/upgrades/0.11_to_1.0/object_instantiation_changes). ([#882](https://github.com/facebookresearch/hydra/issues/882))
- All plugins updated to use TargetConf. Be sure to update all your Hydra plugins ([#882](https://github.com/facebookresearch/hydra/issues/882))
- Instantiated objects no longer have a params node in the conf. keys like hydra.launcher.params.foo are changed to hydra.launcher.foo. Update your configs and overrides if you were overriding such parameters. ([#882](https://github.com/facebookresearch/hydra/issues/882))

### Bug Fixes

- Fixed parsing of two nested lists with whitespace between them: [[a], [b]] ([#836](https://github.com/facebookresearch/hydra/issues/836))

### Improved Documentation

- New Extended command line syntax page ([#752](https://github.com/facebookresearch/hydra/issues/752))


1.0.0rc2 (2020-07-18)
=====================

### Features

- Introducing a DSL for the command line override syntax ([#797](https://github.com/facebookresearch/hydra/issues/797))
- Sanitize exception messages by default, showing only interesting stack frames ([#646](https://github.com/facebookresearch/hydra/issues/646))
- Add a new --info flag to show Hydra debug information without running the user function. ([#662](https://github.com/facebookresearch/hydra/issues/662))
- Add --package flag, can be used with --cfg to print a specific config package ([#674](https://github.com/facebookresearch/hydra/issues/674))
- Improve the Compose API initialization methods ([#702](https://github.com/facebookresearch/hydra/issues/702))
- Switch internal package resource loader from pkg_resources to importlb_resources ([#719](https://github.com/facebookresearch/hydra/issues/719))
- Allow interpolation in the Hydra config node to access the application config ([#771](https://github.com/facebookresearch/hydra/issues/771))
- Hydra provides pytest fixtures (hydra_sweep_runner, hydra_task_runner, hydra_restore_singletons) ([#687](https://github.com/facebookresearch/hydra/issues/687))
- Added contexts to help initialize Hydra in a localized context (Mostly for Unit Tests and Jupyter Notebooks) ([#687](https://github.com/facebookresearch/hydra/issues/687))
- Prints error when command line override looks like a sweep but --multirun is not specified ([#712](https://github.com/facebookresearch/hydra/issues/712))
- Frozen Structured Configs are respected during composition command line overrides ([#724](https://github.com/facebookresearch/hydra/issues/724))

## API Change (Renames, deprecations and removals)

- Hydra argparse flags are now consistently using dash-style. ([#661](https://github.com/facebookresearch/hydra/issues/661))
- Restructure the configuration of the Submitit launcher ([#682](https://github.com/facebookresearch/hydra/issues/682))
- Deprecated cls in favor of target in hydra.utils.{instantiate()/call{}} ([#721](https://github.com/facebookresearch/hydra/issues/721))

### Bug Fixes

- Add hydra/py.typed to pip package to enable type checking in downstream projects ([#657](https://github.com/facebookresearch/hydra/issues/657))
- Fix initialization of Hydra in a module imported from a Jupyter Notebook ([#695](https://github.com/facebookresearch/hydra/issues/695))
- Fix handling of main module override via HYDRA_MAIN_MODULE ([#717](https://github.com/facebookresearch/hydra/issues/717))
- Fix interpolations in overrides to evaluate lazily ([#725](https://github.com/facebookresearch/hydra/issues/725))
- Fixed handling of multirun when target config node is introduced by composition ([#726](https://github.com/facebookresearch/hydra/issues/726))
- Sweepers are now validating config composition before launching ([#775](https://github.com/facebookresearch/hydra/issues/775))
- Save `.hydra/*.yaml` before task execution ([#678](https://github.com/facebookresearch/hydra/issues/678))

### Plugins

- Add [Redis Queue](https://python-rq.org/) Launcher plugin ([Jan-Matthis](https://github.com/jan-matthis))
- Upgrade ax-platform used by Ax sweeper plugin to 0.1.13 or newer

### Improved Documentation

- Add a unit testing example in the [Hydra example application](https://github.com/facebookresearch/hydra/blob/master/examples/advanced/hydra_app_example/tests/test_example.py) ([#687](https://github.com/facebookresearch/hydra/issues/687))
- New [Terminology](https://hydra.cc/docs/terminology) page ([#795](https://github.com/facebookresearch/hydra/issues/795))
- New [Advanced/Hydra in Jupyter Notebooks](https://hydra.cc/docs/advanced/jupyter_notebooks) page ([#795](https://github.com/facebookresearch/hydra/issues/795))
- New [Advanced/Hydra in Unit Tests](https://hydra.cc/docs/advanced/unit_testing) page ([#795](https://github.com/facebookresearch/hydra/issues/795))
- New [Advanced/Override Grammar/Basic](https://hydra.cc/docs/advanced/override_grammar/basic) page ([#795](https://github.com/facebookresearch/hydra/issues/795))

### Maintenance Changes

- Integrate [yamllint](https://yamllint.readthedocs.io/) ([#693](https://github.com/facebookresearch/hydra/issues/693))
- Upgrade to OmegaConf 2.0.1rc11 which solves multiple bugs ([#755](https://github.com/facebookresearch/hydra/issues/755))


1.0.0-rc1 (2020-05-31)
======================
Hydra 1.0 is a major release introducing many new features and breaking some compatibility.

### Features
- Upgrade to OmegaConf 2.0 ([Release notes](https://github.com/omry/omegaconf/releases/tag/2.0.0)) (#630)
- Optional config type safety via Structured Configs (#629)
- Improve command line and config composition error reporting (#349)
- Hydra config can now be accessed through interpolation using ${hydra:key}, for example ${hydra:job.name} ([#325](https://github.com/facebookresearch/hydra/issues/325))
- Support for setting environment variable of running job ([#7](https://github.com/facebookresearch/hydra/issues/7))
- Changes command line processing (requiring + and ~ prefixes for appending and removing items) ([#598](https://github.com/facebookresearch/hydra/issues/598))
- Introducing `@package` header for config files ([#586](https://github.com/facebookresearch/hydra/issues/586))
- Add command line override flags for `config_path` and `config_name` ([#386](https://github.com/facebookresearch/hydra/issues/386))
- hydra.main() now take an optional cfg object to passthrough to the function ([#575](https://github.com/facebookresearch/hydra/issues/575))
- Add hydra.experimental.{initialize_with_file, initialize_with_module} ([#574](https://github.com/facebookresearch/hydra/issues/574))
- Support for disabling the creation of the `.hydra` subdirectory by overriding "hydra.output_subdir" to "null" ([#324](https://github.com/facebookresearch/hydra/issues/324))
- Add `hydra.utils.call()` to call methods and functions as well as instantiate objects.  Search module paths more generically. ([#498](https://github.com/facebookresearch/hydra/issues/498))
- Add support for overriding package from command line and defaults list ([#235](https://github.com/facebookresearch/hydra/issues/235))
- Config source is now abstracted, allowing additional config sources to be used ([#257](https://github.com/facebookresearch/hydra/issues/257))
- New ConfigSource plugin API allowing configs to be provided by external plugins ([#367](https://github.com/facebookresearch/hydra/issues/367))
- Add isort to ensure imports are always sorted ([#340](https://github.com/facebookresearch/hydra/issues/340))
- Codebase is now passing mypy --strict type checking ([#342](https://github.com/facebookresearch/hydra/issues/342))
- Improve performance of plugin discovery and instantiation ([#489](https://github.com/facebookresearch/hydra/issues/489))
- Modules whose name starts with "\_" are skipped during plugin discovery ([#494](https://github.com/facebookresearch/hydra/issues/494))

### Plugins
- Add [Ax](https://ax.dev) Sweeper plugin ([Shagun Sodhani](https://shagunsodhani.com/))
- Add [Nevergrad](https://github.com/facebookresearch/nevergrad) Sweeper plugin ([Jérémy Rapin](https://github.com/jrapin))
- Add [Joblib](https://joblib.readthedocs.io/en/latest/) Launcher plugin ([Jan-Matthis](https://github.com/jan-matthis))
- Add [Submitit](https://github.com/facebookincubator/submitit) Launcher plugin to launch jobs to SLURM clusters
- Add [Fish](https://fishshell.com/) shell Tab Completion plugin ([Binsheng Liu](https://binshengliu.github.io/)) ([#549](https://github.com/facebookresearch/hydra/issues/549))

### API Change (Renames, deprecations and removals)
- Drop support Python 2.7 and 3.5 ([#313](https://github.com/facebookresearch/hydra/issues/313))
- hydra.main() now takes an additional optional config_name and composite-style config_path is deprecated ([#395](https://github.com/facebookresearch/hydra/issues/395))
- Launcher API launch method now takes an additional initial_job_idx indicating the id of the first job in the batch ([#284](https://github.com/facebookresearch/hydra/issues/284))
- Singleton metaclass is now exposed at hydra.core.Singleton ([#371](https://github.com/facebookresearch/hydra/issues/371))
- Moved HydraConfig from hydra.plugins.common.utils to hydra.core ([#371](https://github.com/facebookresearch/hydra/issues/371))
- Move several formerly internal APIs to hydra/core to ensure plugins does not need to use internal APIs ([#371](https://github.com/facebookresearch/hydra/issues/371))
- Plugin import now requires explicit name (from hydra.plugins.launcher import Launcher) ([#371](https://github.com/facebookresearch/hydra/issues/371))
- Object Config "class" field is deprecated in favor of "cls" and will be removed in a future version. ([#389](https://github.com/facebookresearch/hydra/issues/389))
- Experimental compose API config_file changed to config_name ([#395](https://github.com/facebookresearch/hydra/issues/395))
- User plugins should be modified to not import twice during plugin discovery. see issue for details. ([#482](https://github.com/facebookresearch/hydra/issues/482))
- Change hydra.core.plugins.Plugins class to a Singleton. access should be changed to the pattern Plugins.instance().foo() ([#489](https://github.com/facebookresearch/hydra/issues/489))
- Plugins should now include test fixtures (sweep_runner, task_runner) via a standardized conftest.py ([#521](https://github.com/facebookresearch/hydra/issues/521))
- Switch Python 3 native namespace packages for plugins (See task for details) ([#534](https://github.com/facebookresearch/hydra/issues/534))
- Packaged configuration directories now requires an `__init__.py` at their top level ([#536](https://github.com/facebookresearch/hydra/issues/536))
- Appending config groups to the defaults list via the command line now requires a + prefix ([#598](https://github.com/facebookresearch/hydra/issues/598))
- Removing an item from the defaults list by assigning null (db=null) is deprecated, use ~db instead ([#598](https://github.com/facebookresearch/hydra/issues/598))
- Installed Hydra applications no longer need have an additional `entry()` function on the stack ([#92](https://github.com/facebookresearch/hydra/issues/92))

### Bug Fixes

- Fix a bug causing sys.exit() error code to not be propagated ([#351](https://github.com/facebookresearch/hydra/issues/351))
- Shutdown logging subsystem aftter job finishes to ensure log files are flushed and closed ([#378](https://github.com/facebookresearch/hydra/issues/378))
- Fix a bug with utils.instantiate() failing if params contains interpolated values. ([#388](https://github.com/facebookresearch/hydra/issues/388))
- Allow hydra.utils.instantiate() to accept non primitive objects for passthrough by name ([#400](https://github.com/facebookresearch/hydra/issues/400))
- Fix to work when an Hydra app is executed in Jupyter notebook using the %run command ([#481](https://github.com/facebookresearch/hydra/issues/481))
- Plugins are no longer imported twice during plugin discovery ([#482](https://github.com/facebookresearch/hydra/issues/482))
- to_absolute_dir(path) now converts relative path to be relative to os.cwd() when used outside of Hydra ([#496](https://github.com/facebookresearch/hydra/issues/496))

### Improved Documentation

- Working examples are provided for all Hydra plugins in [plugins/examples](https://github.com/facebookresearch/hydra/tree/master/plugins/examples) ([#253](https://github.com/facebookresearch/hydra/issues/253))
- The basic tutorial was rewritten to reflect many changes ([#602](https://github.com/facebookresearch/hydra/issues/602))
- Add a new tutorial covering Structured Configs ([#628](https://github.com/facebookresearch/hydra/issues/628))


0.11.3 (2019-12-29)
===================

### Bug Fixes

- Pin Hydra 0.11 to OmegaConf 1.4 to avoid breaking compatibility when OmegaConf 2.0 is released ([#334](https://github.com/facebookresearch/hydra/issues/334))

### Improved Documentation

- Document a simple Ray example ([#317](https://github.com/facebookresearch/hydra/issues/317))


0.11.2 (2019-12-04)
===================

### Features

- Change website from cli.dev to hydra.cc (#314)

### Bug Fixes

- Fixes --cfg command line flag not working (#305)


0.11.0 (2019-11-19)
===================

### Features

- Add hydra.experimental API for composing configuration on demand (hydra.experimental.compose) (#219)
- Add hydra.utils.get_original_cwd() to access original working directory and hydra.utils.to_absolute_path() to convert a path to absolute path (#251)
- Change hydra logging format pattern, example: "[2019-10-22 16:13:10,769][HYDRA] Installed Hydra Plugins" (#254)
- Change --cfg to require config type (one of 'job', 'hydra' or 'all') (#270)
- Upgrade to OmegaConf 1.4.0, see full change log [here](https://github.com/omry/omegaconf/releases/tag/1.4.0) (#280)
- Experimental support for Jupyter notebooks via compose API (#281)
- Allow configuring override_dirname via hydra.job.config.override_dirname to exclude specific keys or change separator characters (#95)

### Bug Fixes

- Fix a bug that caused out of order composition when mixing config-groups with non-config-group in the defaults block (#261)
- Allow '=' to be used in the value of an override, eg. foo=bar=10 (key foo, value bar=10). (#266)
- Allow composing config files with dot in their name (foo.bar.yaml) (#271)

### Plugins

- hydra-colorlog plugin adds colored log output.

### Improved Documentation

- Document utils.get_original_cwd() and utils.to_absolute_path("foo") (#251)


0.10.0 (2019-10-19)
===================

### Configuration structure changes

- Change the default sweep subdir from ${hydra.job.num}_${hydra.job.id} to ${hydra.job.num} (#150)

### Features

- App help now contains config groups and generated config
  App help can now be customized
  Hydra help is now available via --hydra-help (#1)
- Simplify install and uninstall commands for tab completion (#200)
- hydra.runtime.cwd now contains the original working directory the app was launched from (#244)

### Bug Fixes

- Fix an error with tab completion that occurred when a TAB was pressed after two spaces (#203)
- Fix a bug when sweeping over groups that are used in an interpolation in defaults (#206)
- Fix tab completion for cases where app name looks like foo.par (#213)

### Improved Documentation

- Describe news fragment types in more details in development/contributing (#150)
- Examples dir now mirrors the structure of the website docs (#209)


0.9.0 (2019-10-01)
==================

### Deprecations and Removals

- Old demos directory was removed and a new tutorial directory as added (#167)

### Features

- Make strict mode the default when a config file is specified directly (#150)
- Replace --verbose with a standard override (hydra.verbose) (#161)
- Add IntegrationTestSuite to test_utils for testing Launcher plugins (#168)
- Add support for specifying which config to print in -c, options are job (default), hydra or all. (#176)
- Hydra is now hosted on https://cli.dev! (#75)
- Move all Hydra configuration files to a subfolder (.hydra by default) under the output folder (#77)

### Bug Fixes

- Fix a bug in tab completion of missing mandatory values. (#145)
- Fix a bug with multirun overriding free config groups (not in defaults) when strict mode is enabled (#181)
- Fix a bug that prevented sweeping over an unspecified ('???') default group (#187)

### Improved Documentation

- Updated the primary tutorial on the web site and added a brand new tutorial directory (#58)
- Documented debugging methods in website (#6)


0.1.5 (2019-09-22)
==================

### Deprecations and Removals

- Move FAIRTask, Submititit and FAIR-cluster-defaults plugins to fairinternal/hydra-fair-plugins repository (#138)
- Remove Fairtask and Submitit example configs from demos as they are no longer needed (#146)

### Features

- Created hydra-core pip package, Hydra can now installed with 'pip install hydra-core' (#143)
- Finalized submitit support (#18)

### Plugins

- Add default launcher config for Fairtask and Submitit launcher plugins


0.1.4 (2019-09-18)
==================

### Features

- hydra.utils.instantiate() can now take an additional optional kwargs dictionary to pass to constructor of the instantiated object (#142)
- Initial support for bash completion, see documentation for details (#8)

### Bug Fixes

- Fixed Town Crier to generate correct links to issues in generated news file. (#122)
- Fixed bug with overriding hydra defaults from user config file. (#123)
- Fixed Singletons not getting serialized to remote jobs. (#128)
- Fixed a bug that prevented using submitit in strict mode (#129)
- Fixed example submitit config to set the job name (#133)


0.1.3 (2019-09-02)
==================

### Configuration structure changes

- Changed Hydra core defaults to be more appropriate for open source use. To get the FAIR cluster defaults install the fair_cluster plugin (#103)
- Changed output directories default to group by day (output/DAY/TIME instead of output/DAY_TIME) (#121)

### Features

- Added the ability to prevent a default from being merged it by assigning null to it (hydra/launcher=null) (#106)
- Implemented Plugin discovery mechanism, this can be used to find all installed plugins that implement a specific interface (#119)
- Implemented an API to for manipulating the config search path (#120)

### Bug Fixes

- Fixed config loading to properly support the use case in demos/8_specializing_config (#104)
- Fixed error message when the user config contains defaults that is a mapping and not a list (#107)
- Fixed config loading order to allow properly overriding Hydra config groups from user config (#115)

### Plugins

- New plugin: fair_cluster
  Change Hydra defaults to be appropriate for the FAIR cluster

### Improved Documentation

- Initial search path and plugins documentation (#103)


0.1.2 (2019-08-26)
==================

### Deprecations and Removals

- Hydra config groups were moved to the hydra/namespace (#101)
- Removed support for .hydra directory, Hydra can be configured directly from the job config. (#91)

### Bug Fixes

- Config loading rewrite fixed #88 (#88)


0.1.1 (2019-08-22)
==================

### Deprecations and Removals

- Move non-public APIs into hydra._internal:
    - Moved non-API code into hydra._interanl to flag it as private.
    - Moved plugin interfaces into hydra.plugins.
    - Moved code meant to be used by plugins to hydra.plugins.common. (#78)

### Features

- Integrated towncrier to bring you this news! (#45)
- Hydra is now compatible with Windows (#63)
- Hydra apps can now be packaged and installed along with their configuration files. (#87)

### Bug Fixes

- It is now possible to use ${override_dirname} in the output directory of a local job (#31)
- Override_dirname separator changed from : to =, for example: foo/a:10,b:10 => foo/a=10,b=10 (#63)
- Fixed automatic detection of missing copyright headers (#72)
- fixed a bug that caused an empty config to be returned if specified config file did not have a .yaml extension. (#80)
- Multi change diff:
    - Logging config search path in verbose logging to assist debugging of config load issues
    - Saving hydra.yaml into the job dir to assist debugging hydra issues
    - Fixed a bug caused by fairtask logging change
    - Improved integration-tests debuggability by switching hydra to debug logging in them
    - Added selective plugin testing to nox using env, for example PLUGINS=fairtask would only test fairtask. (#87)

### Improved Documentation

- Improved the contributing docs (#45)
- Documented Hydra app packaging under Deployment/Application packaging (#87)
