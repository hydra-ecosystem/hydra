---
id: execution_whitelist
title: Execution whitelist
---

Hydra 1.4 deprecates resolving config-selected Python targets without an
execution whitelist supplied by trusted Python code. This applies to both
`hydra.utils.instantiate()` and Python logging configured by Hydra.

For the permanent security model and API guidance, see
[Execution whitelist](/docs/advanced/execution_whitelist).

## Migrate an application

Add the expected application and logging targets to `@hydra.main()`:

```python
import hydra

@hydra.main(
    version_base=None,
    config_path="conf",
    config_name="config",
    execution_whitelist=("my_app.*",),
)
def my_app(cfg):
    ...
```

Hydra automatically permits targets used by its built-in logging
configurations. Add application-defined handlers, formatters, filters, queues,
and listeners explicitly.

## Migrate direct calls

Pass expected targets to direct `instantiate()` calls:

```python
from hydra.utils import instantiate

model = instantiate(
    cfg.model,
    _execution_whitelist_="my_app.models.*",
)
```

If a framework or helper calls `instantiate()` internally, wrap the call in a
trusted scope:

```python
from hydra.utils import execution_whitelist

with execution_whitelist("my_app.*"):
    framework_function(cfg)
```

## Temporary legacy behavior

Hydra 1.4 warns when it resolves config-selected targets without an execution
whitelist; this becomes an error in Hydra 1.5. The no-whitelist path retains
Hydra's target blacklist as defense-in-depth.

If unrestricted resolution is intentional and all relevant configuration is
trusted, pass `UNSAFE_DISABLE_EXECUTION_CHECKS` explicitly. This disables both
whitelist and blacklist checks and should not be used as a routine migration.
See [Restricted targets](/docs/advanced/execution_whitelist/restricted_targets)
for the implications of disabling these checks.
