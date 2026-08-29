---
id: scopes
title: Scopes and application integration
sidebar_label: Scopes and integration
---

Use `hydra.utils.execution_whitelist()` when trusted code calls `instantiate()`
indirectly, when several `instantiate()` calls share a whitelist, or when
Python logging configured by Hydra needs the same policy.

## Direct calls

For one direct `instantiate()` call, pass the expected targets from trusted
Python code:

```python
from hydra.utils import instantiate

model = instantiate(
    cfg.model,
    _execution_whitelist_="my_app.models.*",
)
```

Use `execution_whitelist()` as a context manager when trusted code calls
`instantiate()` indirectly, so there is no direct call site at which to pass
`_execution_whitelist_`. A context is also useful when a block performs several
`instantiate()` calls or configures logging through Hydra:

```python
from hydra.utils import execution_whitelist

with execution_whitelist("my_app.*"):
    build_components(cfg)
```

## Nested contexts

Nested contexts are additive by default. The inner context permits the union of
the outer and inner entries. Exiting the inner block restores the exact outer
policy, including when the block exits because of an exception:

```python
with execution_whitelist("my_app.models.*"):
    with execution_whitelist("my_app.optimizers.*"):
        build_training_components(cfg)  # Both entries are active.

    instantiate(cfg.model)  # Only my_app.models.* remains active.
```

Use `reset=True` when the inner operation must use exactly its supplied policy
instead of adding to the outer context:

```python
with execution_whitelist("my_app.*"):
    with execution_whitelist("my_app.models.*", reset=True):
        instantiate(cfg.model)
```

A whitelist passed directly to `instantiate()` also adds to the active context.
Pass a resetting policy to make the call-site policy authoritative:

```python
model = instantiate(
    cfg.model,
    _execution_whitelist_=execution_whitelist(
        "my_app.models.*",
        reset=True,
    ),
)
```

:::warning

An additive inner context does not reinstate checks if an outer context uses
`UNSAFE_DISABLE_EXECUTION_CHECKS`. Use `reset=True` with an explicit whitelist
to restore enforcement for the inner operation.

:::

## Share a whitelist between call sites

If several trusted call sites must use the same whitelist, define one immutable
value in a small leaf module that imports no application modules:

```python
# my_app/execution_policy.py
from typing import Final

EXECUTION_WHITELIST: Final[tuple[str, ...]] = (
    "my_app.logging.CustomHandler",
    "my_app.models.*",
)
```

String target names avoid import cycles and import-time side effects. The tuple
cannot be changed in place, and `Final` lets static type checkers reject
rebinding. Import this value wherever the same policy is required:

```python
# my_app/main.py
import hydra

from my_app.execution_policy import EXECUTION_WHITELIST


@hydra.main(
    version_base=None,
    config_path="conf",
    config_name="config",
    execution_whitelist=EXECUTION_WHITELIST,
)
def my_app(cfg):
    ...
```

:::note

These precautions prevent accidental changes; malicious code that is already
running can still monkeypatch the policy module. The execution whitelist does
not provide a security boundary against code that is already executing in the
process.

:::

## Frameworks and plugins

### Application code

An application integrating a third-party framework remains responsible only
for its application-owned targets. It supplies that policy around the framework
call and does not maintain the framework's internal whitelist:

```python
# my_app/main.py — application-owned code
from hydra.utils import execution_whitelist
from training_framework.training import train


with execution_whitelist("my_app.*"):
    train(cfg)
```

### Framework and plugin code

Framework authors should authorize only framework-owned targets around their
internal Hydra calls. For example, a training framework can authorize its
built-in models and datasets while still accepting application-owned
implementations through the outer policy:

```python
# training_framework/training.py — code shipped by the framework
from hydra.utils import execution_whitelist, instantiate


def train(cfg):
    with execution_whitelist(
        (
            "training_framework.models.*",
            "training_framework.datasets.*",
        )
    ):
        model = instantiate(cfg.model)
        dataset = instantiate(cfg.dataset)
        train_model(model, dataset)
```

While the framework instantiates the model and dataset, both its inner policy
and the application's outer policy are active. The configuration can therefore
select either framework-provided or application-provided implementations.

The same ownership rule applies to Hydra plugins. Hydra instantiates launcher
and sweeper plugin configs non-recursively. If a plugin config contains nested
`_target_` values, the plugin author should call `instantiate()` with a
plugin-owned whitelist. Application authors remain responsible for targets
owned by their applications.

## Async tasks and application-created threads

The whitelist context is isolated between overlapping async tasks. It is not
guaranteed to propagate into threads created by application code. Re-establish
it at the worker boundary from a trusted Python constant:

```python
from concurrent.futures import ThreadPoolExecutor

from hydra.utils import execution_whitelist, instantiate

from my_app.execution_policy import EXECUTION_WHITELIST


def build_model(model_cfg):
    with execution_whitelist(EXECUTION_WHITELIST, reset=True):
        return instantiate(model_cfg)


with ThreadPoolExecutor() as executor:
    model = executor.submit(build_model, cfg.model).result()
```

For a single `instantiate()` call in a worker, pass the same resetting policy at
the call site:

```python
model = instantiate(
    cfg.model,
    _execution_whitelist_=execution_whitelist(
        EXECUTION_WHITELIST,
        reset=True,
    ),
)
```

`reset=True` makes the trusted worker policy authoritative instead of adding it
to any execution whitelist that happens to be active in that thread.
