---
id: config_store_collisions
title: ConfigStore collision handling
---

Previously, `ConfigStore.store()` silently replaced any config registered with
the same name and group. Hydra 1.4 adds the `replace` argument to make the intended
behavior explicit:

| `replace` | First registration | Collision in Hydra 1.4 |
| --- | --- | --- |
| Omitted or `None` | Register | Warn and replace |
| `True` | Register | Replace silently |
| `False` | Register | Raise `ValueError`; keep the original config |

In Hydra 1.5, a collision with `replace` omitted will raise an error. This warning
period allows applications that register configs during imports to migrate
without unexpectedly preventing startup. Applications that treat warnings as
errors must address the warning in Hydra 1.4.

## Choose the intended behavior

If replacement is intentional, opt in explicitly:

```python
from hydra.core.config_store import ConfigStore

cs = ConfigStore.instance()
cs.store(group="db", name="mysql", node={"host": "localhost"})
cs.store(
    group="db",
    name="mysql",
    node={"host": "database.example.com"},
    replace=True,
)
```

If duplicate registration indicates an error, use `replace=False`. A collision
then raises `ValueError` without replacing the original config:

```python
cs.store(group="db", name="mysql", node={"host": "localhost"}, replace=False)
```

For unintended duplicates, give the configs different names or groups, or remove
the redundant registration. Changing the package or provider does not avoid a
collision. `mysql` and `mysql.yaml` refer to the same registration; `group=None`
and `group=""` both mean the root group. Re-registering an identical node still
counts as a collision.

Plugin discovery uses normal Python imports. Scanning an already-imported
module does not repeat its registrations.

The warning identifies the config path and the original and replacement
providers when supplied. `ConfigStoreWithProvider.store()` supports `replace`
with the same behavior. The warning is a `Hydra15MigrationWarning`, which derives
from `UserWarning`.

## Registering configs in the main script

Registering configs at the top level of your main script is a common pattern.
It can produce a collision warning when the same script is also imported as a
module. For example, running `python my_app.py` and then instantiating
`_target_: my_app.MySQLConnection` loads the same file under two names:

1. Python runs the script as `__main__`, executing its registrations.
2. `instantiate()` imports `my_app` to resolve `MySQLConnection`. Python caches
   modules by name, so it does not reuse the module cached as `__main__`.
3. The file's top-level code runs again and repeats the registrations, causing
   `Hydra15MigrationWarning` even when the configs have not changed.

This is Python's [documented treatment of `__main__`](https://docs.python.org/3/reference/import.html#special-considerations-for-main),
and can also happen with `python -m my_app`. Registering in the main script
does not cause a warning unless a registration is repeated.

Keep the schema classes and Hydra task defined at module level, but move the
registration calls into the script's entry point, before calling the task:

```python
@hydra.main(config_name="config")
def my_app(cfg: Config) -> None:
    # cfg.db targets my_app.MySQLConnection, a class defined in this same file.
    instantiate(cfg.db)


if __name__ == "__main__":
    # instantiate() imports this file as my_app; register only when run as a script.
    cs = ConfigStore.instance()
    cs.store(name="config", node=Config)
    cs.store(group="db", name="mysql", node=MySQLConfig)
    my_app()
```

Importing `my_app` can then resolve its target classes without registering the
configs again. This removes the duplicate registration without needing
`replace=True`.

The two module instances still define distinct class objects. To avoid that
as well, put reusable classes in a separate module and reference that module
in `_target_`, keeping the main script as a small entry point.

Alternatively, for a config tied to running this script, target the class in
the existing main module:

```yaml
_target_: __main__.MySQLConnection
```

This reuses the original class without importing the script again, avoiding
both duplicate registrations and distinct class objects. It depends on this
script being the entry point: when another program or a test runner imports
your application, its `__main__` may not contain the target class.
