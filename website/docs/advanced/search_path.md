---
id: search_path
title: Config Search Path
---

import {ExampleGithubLink} from "@site/src/components/GithubLink"

The Config Search Path is an ordered list of sources Hydra searches for configs,
including the primary config and configs referenced by its Defaults List. It is
similar to the Python `PYTHONPATH`: the first source containing a requested config
wins.

Sources use prefixes such as `file://` and `pkg://`:

- `file://` points to a filesystem directory. A relative path is resolved from the
  current working directory; an absolute path is used as-is. Use `/` as the path
  separator on all operating systems.
- `pkg://` points to an importable Python package, using `.` between package
  names. Package directories need `__init__.py` files.

The application's initial config source normally precedes later additions such
as `--config-dir` and `hydra.searchpath`. These additions can supply missing
configs but cannot shadow a same-named config in an earlier source. A
`SearchPathPlugin` can explicitly change that order by prepending a source.

You can inspect the search path and the configurations loaded by Hydra via the `--info` flag:

```bash
$ python my_app.py --info searchpath
```

### Choosing initial config sources

The entry point determines the initial application sources:

| API | Path behavior |
| --- | --- |
| `@hydra.main(config_path=...)` | An absolute path is used as-is; a relative path is resolved from the location of the decorated function. |
| `initialize(config_path=...)` | An absolute path is used as-is; a relative path is resolved from the caller. |
| `initialize_config_dir(config_dir=...)` | Uses an absolute filesystem directory. |
| `initialize_config_module(config_module=...)` | Uses an importable Python package. |
| `initialize_config_search_path(config_search_path=...)` | Searches the supplied source URIs in order. |

See the [Compose API](compose_api.md#initialization-methods) for the four
initializers' signatures and examples. `initialize_config_search_path()` accepts
absolute `file://` directories, importable `pkg://` packages, and `caller://`
for the caller's directory (`caller://conf` for its `conf` subdirectory).
`caller://` is special syntax for that initializer, not a config-source scheme
for `hydra.searchpath` or plugins. Unlike those mechanisms, this initializer
requires `file://` paths to be absolute.

### Adding sources with `hydra.searchpath`

Set `hydra.searchpath` in the primary config to find configs in additional
directories or Python packages. See [Adding config sources with
`hydra.searchpath`](search_path/hydra_searchpath.md) for the rules and an example.

### Adding `--config-dir` from the command line

Like `hydra.searchpath`, `--config-dir` adds a source after the initial config
sources, so it cannot shadow a same-named config there. A relative
`--config-dir` is resolved from the current working directory, not from the
location of the decorated function. It is searched before entries added by
`hydra.searchpath`. See the [command-line flags](hydra-command-line-flags.md)
for more information.

### Creating a `SearchPathPlugin`

<ExampleGithubLink text="ExampleSearchPathPlugin" to="examples/plugins/example_searchpath_plugin/"/>

Framework authors may want to add their configs to the search path automatically once their package is installed,
eliminating the need for any actions from the users.
This can be achieved using a `SearchPathPlugin`. Check the example plugin linked above for more details.
To change precedence programmatically, a plugin can prepend a config source.
For an organization-wide override of Hydra's own defaults, see
[Environment-specific overrides](../patterns/environment_specific_overrides.md).
