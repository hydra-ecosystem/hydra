---
id: hydra_main
title: '@hydra.main()'
sidebar_label: '@hydra.main()'
---

`@hydra.main()` is the usual entry point for a Hydra application. It composes a
config, applies command-line overrides, and calls your function with the resulting
`DictConfig`. Hydra also manages features such as [multirun](../tutorials/basic/running_your_app/2_multirun.md),
[logging](../tutorials/basic/running_your_app/4_logging.md), and the
[working directory](../tutorials/basic/running_your_app/3_working_directory.md).

### Code example

```python
import hydra
from omegaconf import DictConfig


@hydra.main(config_path="conf", config_name="config")
def my_app(cfg: DictConfig) -> DictConfig:
    print(cfg)
    return cfg


if __name__ == "__main__":
    my_app()
```

Calling `my_app()` runs Hydra's command-line entry point. For example,
`python my_app.py db=mysql` composes `conf/config.yaml`, applies the `db=mysql`
override, and passes the resulting config to the function. See the
[tutorial](../tutorials/basic/your_first_app/1_simple_cli.md) for a first application.

### API Documentation

```python title="@hydra.main()"
def main(
    config_path: Optional[str] = None,
    config_name: Optional[str] = None,
    version_base: Optional[str] = ...,
    execution_whitelist: ExecutionWhitelist = None,
) -> Callable[[TaskFunction], Any]:
    ...
```

- `config_path` adds a directory or package to the [Config Search Path](search_path.md).
  A relative directory is resolved from the Python file declaring `@hydra.main()`;
  an absolute directory is used as-is. A `pkg://` path names an importable Python
  package. When omitted, no application directory is added.
- `config_name` names the primary config to compose, usually without its `.yaml`
  extension. It is resolved within the Config Search Path. When omitted, Hydra
  starts with an empty application config, which can still receive overrides.
- `version_base` is deprecated in Hydra 1.4. Omit it in new code; see the
  [1.4 preparation guide](../upgrades/1.3_to_1.4/prepare_for_1_4.md)
  when upgrading an existing application.
- `execution_whitelist` specifies trusted targets allowed for instantiation and
  Python logging configured by Hydra. See [Execution whitelist](execution_whitelist.md)
  for its syntax and security model.

The command-line flags `--config-path` and `--config-name` can override the
corresponding decorator parameters. See [Hydra command-line flags](hydra-command-line-flags.md).

### Return value and config passthrough

For a normal `my_app()` call, the decorated function returns `None`, even if the
task function returns a value. A multirun may call the task function multiple
times, so there is no single task value to return. The task's result is available
to Hydra's job execution machinery, not as the return value of `my_app()`.

You can instead pass a `DictConfig` directly to the decorated function:

```python
from omegaconf import OmegaConf

cfg = OmegaConf.create({"db": "mysql"})
result = my_app(cfg)
# result is cfg
```

In this form, Hydra passes `cfg` directly to the task function and returns its
value. It does not parse command-line arguments, compose a config, or run Hydra's
job machinery. This is useful when a caller has already prepared a config, such
as in a test; it is not equivalent to a normal Hydra application run.

For composing configs programmatically without using the decorator as an entry
point, see the [Compose API](compose_api.md). For wrapping a Hydra entry point
with other decorators, see [Decorating the main function](decorating_main.md).
