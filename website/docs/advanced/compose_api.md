---
id: compose_api
title: Compose API
sidebar_label: Compose API
---

import GithubLink,{ExampleGithubLink} from "@site/src/components/GithubLink"

The Compose API lets you compose configs programmatically after Hydra has been
initialized, either by [`@hydra.main()`](hydra_main.md) or by one of the
initialization methods below.

### When to use the Compose API

Use the Compose API when `@hydra.main()` is not suitable as an entry point, or
when an application needs to compose additional configs after initialization:

- In application code without a standard Hydra command-line entry point (<GithubLink to="examples/advanced/ad_hoc_composition">example</GithubLink>).
- In a unit test ([example](unit_testing.md)).
- In a Jupyter notebook ([example](jupyter_notebooks.md)).
- To compose multiple configs within an `@hydra.main()` application (<GithubLink to="examples/advanced/ray_example/ray_compose_example.py">Ray example</GithubLink>).

<div class="alert alert--info" role="alert">
Prefer <b>@hydra.main()</b> for your application's entry point when possible.
Replacing it with the Compose API forfeits features such as tab completion,
multirun, working directory management, and logging management.
</div>

### Initialization methods

There are 4 initialization methods:

- `initialize()`: Initialize with an absolute filesystem path or one relative to the caller.
- `initialize_config_dir()`: Initialize with an absolute filesystem directory.
- `initialize_config_module()`: Initialize with an importable config package.
- `initialize_config_search_path()`: Initialize with multiple ordered config sources.

All 4 can be used as methods or contexts.
When used as methods, they are initializing Hydra globally and should only be called once.
When used as contexts, they are initializing Hydra within the context and can be used multiple times.
Like <b>@hydra.main()</b>, the original three still accept the deprecated `version_base`
parameter in Hydra 1.4. Remove it after upgrading; see the
[Hydra 1.4 preparation guide](../upgrades/1.3_to_1.4/prepare_for_1_4.md).
`initialize_config_search_path()` does not accept `version_base`.

Use `initialize_config_search_path()` when a Compose API session needs more than one config source.
Entries are searched in the order provided; the first matching config wins.
`file://` entries must name absolute directories, and `pkg://` entries name
importable config packages. `caller://` resolves to the caller's directory;
`caller://conf` resolves to its `conf` subdirectory, like a relative
`initialize(config_path="conf")`. `caller://` is supported by this initializer,
not by `hydra.searchpath` in a config file. It refers to the immediate call site;
if a wrapper calls the initializer, it resolves relative to the wrapper.

Pass the source directory or package to the initializer, then pass a config
name relative to those sources to `compose()`. For example, with
`file:///models` as a source, use `compose(config_name="model")` for
`/models/model.yaml`, not `compose(config_name="/models/model.yaml")`.
Unlike `initialize()`, this initializer defaults `job_name` to `"app"`;
specify it if you need to preserve a caller-derived job name.

For example, a caller-relative primary config can use defaults supplied by a
packaged config source:

```python
from hydra import compose, initialize_config_search_path

with initialize_config_search_path(
    ["caller://conf", "pkg://my_app.conf"]
):
    cfg = compose(config_name="config")
```

### Code example

```python
from hydra import compose, initialize
from omegaconf import OmegaConf

if __name__ == "__main__":
    # context initialization
    with initialize(config_path="conf", job_name="test_app"):
        cfg = compose(config_name="config", overrides=["db=mysql", "db.user=me"])
        print(OmegaConf.to_yaml(cfg))

    # global initialization
    initialize(config_path="conf", job_name="test_app")
    cfg = compose(config_name="config", overrides=["db=mysql", "db.user=me"])
    print(OmegaConf.to_yaml(cfg))
```
### API Documentation

```python title="Compose API"
def compose(
    config_name: str | None = None,
    overrides: list[str] = [],
    return_hydra_config: bool = False,
) -> DictConfig:
    """
    :param config_name: the name of the config
           (usually the file name without the .yaml extension)
    :param overrides: list of overrides for config file
    :param return_hydra_config: True to return the hydra config node in the result
    :return: the composed config
    """
```

```python title="Initialization with a filesystem path"
def initialize(
    config_path: str | None = None,
    job_name: str | None = None,
    caller_stack_depth: int = 1,
    version_base: str | None = ...,
) -> None:
    """
    Initializes Hydra and add the config_path to the config search path.
    A relative config_path is resolved relative to the parent of the caller.
    An absolute config_path is used as is.
    Hydra detects the caller type automatically at runtime.

    Supported callers:
    - Python scripts
    - Python modules
    - Unit tests
    - Jupyter notebooks.
    :param config_path: absolute path or path relative to the parent of the caller
    :param job_name: the value for hydra.job.name (By default it is automatically detected based on the caller)
    :param caller_stack_depth: stack depth of the caller, defaults to 1 (direct caller).
    """
```

```python title="Initializing with a config module"
def initialize_config_module(
    config_module: str,
    job_name: str = "app",
    version_base: str | None = ...,
) -> None:
    """
    Initializes Hydra and adds the config_module to the config search path.
    The config module must be an importable regular Python package.
    Its initializer may be Python source or a compiled extension.
    :param config_module: importable module name, for example "foo.bar.conf".
    :param job_name: the value for hydra.job.name (default is 'app')
    """
```
```python title="Initializing with a config directory"
def initialize_config_dir(
    config_dir: str,
    job_name: str = "app",
    version_base: str | None = ...,
) -> None:
    """
    Initializes Hydra and adds an absolute config directory to the config search path.
    The config_dir is always a filesystem path and must be absolute.
    Relative paths will result in an error.
    :param config_dir: absolute file system path
    :param job_name: the value for hydra.job.name (default is 'app')
    """
```

```python title="Initializing with multiple config sources"
def initialize_config_search_path(
    config_search_path: Sequence[str],
    job_name: str = "app",
) -> None:
    """Initialize with ordered config source URIs, including caller://."""
```
