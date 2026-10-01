---
id: config_store
title: Config Store API
---

import {ExampleGithubLink} from "@site/src/components/GithubLink"

<ExampleGithubLink to="examples/tutorials/structured_configs/1_minimal"/>

Throughout the rest of tutorials, we will be using `ConfigStore` to register dataclasses as input configs in Hydra. 
`ConfigStore` is a singleton storing configs in memory. 
The primary API for interacting with the `ConfigStore` is the store method described below.

### API
```python
class ConfigStore(metaclass=Singleton):
    def store(
        self,
        name: str,
        node: Any,
        group: Optional[str] = None,
        package: Optional[str] = None,
        provider: Optional[str] = None,
        replace: Optional[bool] = None,
    ) -> None:
        """
        Stores a config node into the repository
        :param name: config name
        :param node: config node, can be DictConfig, ListConfig,
            Structured configs and even dict and list
        :param group: config group, subgroup separator is '/',
            for example hydra/launcher
        :param package: Config node parent hierarchy.
            Child separator is '.', for example foo.bar.baz
        :param provider: the name of the module/app providing this config.
            Helps debugging.
        :param replace: what to do when a *different* config is already stored
            under the same group and name. True replaces it, False raises a
            ValueError. The default, None, replaces it and issues a UserWarning.
            Storing a config that equals the stored one is never a clobber:
            Hydra re-executes plugin modules on every plugin discovery pass, so
            their module level store() calls repeat by design.
        """
    ...
```

### Overwriting a stored config

Storing a config under a group and name that is already taken by a *different*
config replaces it. Because that is easy to do by accident in an application
that stores many configs, it also issues a `UserWarning`:

```python
cs.store(name="config", group="db", node=MySQLConfig)
cs.store(name="config", group="db", node=PostgresSQLConfig)  # UserWarning
```

Pass `replace` to say which you meant:

```python
# Replace the stored config, no warning
cs.store(name="config", group="db", node=PostgresSQLConfig, replace=True)
# Refuse to replace it, raises ValueError
cs.store(name="config", group="db", node=PostgresSQLConfig, replace=False)
```

### ConfigStore and YAML input configs

`ConfigStore` has feature parity with YAML input configs. On top of that, it also provides typing validation. 
`ConfigStore` can be used alone or together with YAML. We will see more examples later in this series of tutorials. 
For now, let's see how the `ConfigStore` API translates into the YAML input configs, which we've become more familiar 
with after the basic tutorials.

Say we have a simple application and a `db` config group with a `mysql` option:

<div className="row">

<div className="col col--5">

```python title="my_app.py"
@hydra.main(config_path="conf")
def my_app(cfg: DictConfig) -> None:
    print(OmegaConf.to_yaml(cfg))


if __name__ == "__main__":
    my_app()
```
</div>
<div className="col  col--4">

```text title="Directory layout"
├─ conf
│  └─ db
│      └─ mysql.yaml
└── my_app.py



```
</div>
<div className="col col--3">

```yaml title="db/mysql.yaml"
driver: mysql
user: omry
password: secret




```
</div>
</div>

What if we want to add an `postgresql` option now? Yes, we can easily add a `db/postgresql.yaml` config group option. But
that is not the only way! We can also use `ConfigStore` to make another config group option for `db` available to Hydra.

To achieve this, we add a few lines (highlighted) in the above `my_app.py` file:


```python title="my_app.py" {1-9}
@dataclass
class PostgresSQLConfig:
    driver: str = "postgresql"
    user: str = "jieru"
    password: str = "secret"

cs = ConfigStore.instance()
# Registering the Config class with the name `postgresql` with the config group `db`
cs.store(name="postgresql", group="db", node=PostgresSQLConfig)

@hydra.main(config_path="conf")
def my_app(cfg: DictConfig) -> None:
    print(OmegaConf.to_yaml(cfg))


if __name__ == "__main__":
    my_app()
```


Now that our application has access to both `db` config group options, let's run the application to verify:

<div className="row">

<div className="col col--6">

```commandline title="python my_app.py +db=mysql"
db:
  driver: mysql
  user: omry
  password: secret

```
</div>
<div className="col  col--6">

```commandline title="python my_app.py +db=postgresql"
db:
  driver: postgresql
  user: jieru
  password: secret

```
</div>
</div>


### Example node values
A few examples of supported node values parameters:
```python
from dataclasses import dataclass

from hydra.core.config_store import ConfigStore

@dataclass
class MySQLConfig:
    host: str = "localhost"
    port: int = 3306

cs = ConfigStore.instance()

# Using the type
cs.store(name="config1", node=MySQLConfig)
# Using an instance, overriding some default values
cs.store(name="config2", node=MySQLConfig(host="test.db", port=3307))
# Using a dictionary, forfeiting runtime type safety
cs.store(name="config3", node={"host": "localhost", "port": 3308})
```
