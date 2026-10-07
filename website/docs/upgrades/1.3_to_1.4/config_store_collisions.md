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
cs.store(group="db", name="mysql", node={"host": "localhost"}, provider="defaults")
cs.store(
    group="db",
    name="mysql",
    node={"host": "database.example.com"},
    provider="application",
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

Plugin discovery can re-execute a plugin module that was already imported,
repeating its module-level registrations. Plugin authors should use
`replace=True` for these intentional registrations. This includes registering
the same config again; otherwise discovery emits a warning in Hydra 1.4 and
will raise an error in Hydra 1.5.

The warning identifies the config path and the original and replacement
providers when supplied. `ConfigStoreWithProvider.store()` supports `replace`
with the same behavior. The warning is a `Hydra15MigrationWarning`, which derives
from `UserWarning`.
