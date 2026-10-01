---
id: defaults
title: Defaults List
---

import {ExampleGithubLink} from "@site/src/components/GithubLink"

<ExampleGithubLink to="examples/tutorials/structured_configs/4_defaults/my_app.py"/>

You can define a defaults list in your primary Structured Config just like you can in your primary `config.yaml` file.
The example below extends the previous example by adding a defaults list that will load `db=mysql` by default.

<div class="alert alert--info" role="alert">
NOTE: You can still place your defaults list in your primary (YAML) config file (Example in next page).
</div><br/>

```python {15-18,22-23}
from dataclasses import dataclass

import hydra
from hydra.core.config_store import ConfigStore
from omegaconf import MISSING, OmegaConf

@dataclass
class MySQLConfig:
    ...

@dataclass
class PostGreSQLConfig:
    ...

defaults = [
    # Load the config "mysql" from the config group "db"
    {"db": "mysql"}
]

@dataclass
class Config:
    # this is unfortunately verbose due to @dataclass limitations
    defaults: list[Any] = field(default_factory=lambda: defaults)

    # Hydra will populate this field based on the defaults list
    db: Any = MISSING

cs = ConfigStore.instance()
cs.store(group="db", name="mysql", node=MySQLConfig)
cs.store(group="db", name="postgresql", node=PostGreSQLConfig)
cs.store(name="config", node=Config)


@hydra.main(config_name="config")
def my_app(cfg: Config) -> None:
    print(OmegaConf.to_yaml(cfg))


if __name__ == "__main__":
    my_app()
```
Running `my_app.py` loads the mysql config option by default:
```yaml
$ python my_app.py
db:
  driver: mysql
  ...
```

You can override the default option via the command line:
```yaml
$ python my_app.py db=postgresql
db:
  driver: postgresql
  ...
```

### A Note about composition order
The default composition order in Hydra is that values defined in a config are merged into values introduced from configs in the Defaults List - or in other words - overriding them.
This behavior can be unintuitive when your primary config is a Structured Config, like in the example above.
For example, if the primary config is:
```python {6}
@dataclass
class Config:
    defaults: list[Any] = field(default_factory=lambda: [
        "debug/activate",
        # If you do not specify _self_, it will be appended to the end of the defaults list by default.
        "_self_"
    ])

    debug: bool = False
```
And `debug/activate.yaml` is overriding the `debug` flag to `True`, the composition order would be such that debug ends up being `False`.  
To get `debug/activate.yaml` to override this config, explicitly specify `_self_` before `debug/activate.yaml`:
```python {4}
@dataclass
class Config:
    defaults: list[Any] = field(default_factory=lambda: [
        "_self_",
        "debug/activate",
    ])

    debug: bool = False
```
 
See [Composition Order](advanced/defaults_list.md#composition-order) for more information.

### Requiring users to specify a default list value

Set `db` as `MISSING` to require the user to specify a value on the command line.

<div className="row">
<div className="col col--6">

```python title="Defaults list with a missing db"
defaults = [
    {"db": MISSING}
]


```

</div>

<div className="col  col--6">

```text title="Output"
$ python my_app.py
In 'config': You must specify 'db', e.g, db=<OPTION>
Available options:
        mysql
        postgresql
```


</div>
</div>
