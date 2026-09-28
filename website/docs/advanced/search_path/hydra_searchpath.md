---
id: hydra_searchpath
title: Adding Config Sources with hydra.searchpath
---

import {ExampleGithubLink} from "@site/src/components/GithubLink"

Use `hydra.searchpath` when the primary config refers to configs in another
directory or Python package. For example, a test config under `tests/configs`
may refer to an application config under `app/configs`.

Add sources to the `hydra.searchpath` list in the **primary config**. Hydra
searches them after the initial config sources, in list order. An entry can use
`file://` for a filesystem directory or `pkg://` for an importable Python
package. See [Config Search Path](../search_path.md) for source syntax and
precedence.

Among config files, only the primary config can set `hydra.searchpath`.
Setting it in a config selected by the Defaults List results in an error.
You can also set it on the command line; that value **replaces**, rather than
appends to, the list in the primary config.

### With `initialize_config_search_path()`

The sources passed to `initialize_config_search_path()` form the initial search
path. Hydra finds the primary config in that path before reading its
`hydra.searchpath`. The config's entries are then searched **after all** the
initializer's sources; they do not replace them. For example, if the
initializer receives `["caller://conf", "pkg://shared"]` and the selected
`config.yaml` sets `hydra.searchpath: ["pkg://extras"]`, config lookup uses
`conf`, then `shared`, then `extras` (unless a plugin changes the order).

A command-line `hydra.searchpath` override replaces only the list from
`config.yaml`, not the initializer's sources. Hydra applies that list separately
for each `compose()` call; it does not accumulate across calls. Every source
passed to the initializer must be available, or composition fails before
processing the config's `hydra.searchpath`. An unavailable source in
`hydra.searchpath` instead produces a warning, though looking up a config from
that source can still fail.

### Example

<ExampleGithubLink text="Example application" to="examples/advanced/config_search_path"/>

Suppose the application has two config directories:

```text
├── conf
│   ├── config.yaml
│   └── dataset
│       └── cifar10.yaml
├── additional_conf
│   ├── __init__.py
│   └── dataset
│       └── imagenet.yaml
└── my_app.py
```

`my_app.py` uses `conf/config.yaml` as its primary config:

```python title="my_app.py"
import hydra
from omegaconf import DictConfig, OmegaConf


@hydra.main(config_path="conf", config_name="config")
def my_app(cfg: DictConfig) -> None:
    print(OmegaConf.to_yaml(cfg))


if __name__ == "__main__":
    my_app()
```

Add the importable `additional_conf` package to the search path so that
Hydra can find `dataset/imagenet`:

```yaml title="conf/config.yaml"
defaults:
  - dataset: cifar10
  - _self_

hydra:
  searchpath:
    - pkg://additional_conf
```

Now `python my_app.py dataset=imagenet` selects the config from
`additional_conf`:

```yaml title="Output"
dataset:
  name: imagenet
  path: /datasets/imagenet
```

You can also override the list from the command line:

```bash
python my_app.py 'hydra.searchpath=[pkg://additional_conf]' dataset=imagenet
```

For a filesystem directory, use `file://` instead, for example
`file:///etc/my_app` or `file://${oc.env:HOME}/.my_app`.

### Giving an external source precedence

An added search path entry cannot shadow a same-named config in the initial
source. To give an external directory precedence, make it the primary source:

```bash
python -m foo --config-path=/my/path/to/configs --config-name=config
```

This selects `/my/path/to/configs/config.yaml` as the primary config. To use
configs from the installed package as fallbacks, list its importable config
package there:

```yaml title="/my/path/to/configs/config.yaml"
hydra:
  searchpath:
    - pkg://foo.conf
```

Define any defaults needed by the application in the new primary config; the
installed primary config is not merged automatically.
