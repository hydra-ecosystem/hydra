---
id: restricted_targets
title: Restricted targets
sidebar_label: Restricted targets
---

Some callables are too generic or powerful for target-name authorization. Even
an exact execution-whitelist entry cannot authorize these targets because the
configured name does not bound the behavior that configuration can select.

Hydra's error identifies the exact rejected target and explains why it cannot be
authorized.

## Dynamic selection and dispatch

Attribute operations such as `builtins.getattr`, `hasattr`, `setattr`, and
`delattr` let configuration select an attribute or descriptor operation as data.
Generic `operator` helpers such as `call`, `attrgetter`, `methodcaller`,
`getitem`, `itemgetter`, `setitem`, `delitem`, and `contains` have the same
problem.

Name the intended callable directly as `_target_`, or perform the dynamic
selection in trusted Python code.

## Callback dispatch and callable wrappers

Dispatchers such as `builtins.map`, `functools.reduce`, `itertools.starmap`, and
executor or pool submission APIs invoke a config-supplied callback. Invocation
may continue outside Hydra's immediate callable-result checks.

Callable binding and wrapper helpers can similarly defer or obscure the
effective callable. Examples include `classmethod`, `staticmethod`,
`functools.lru_cache`, `partialmethod`, `singledispatch`, and `update_wrapper`.

Perform this dispatch or wrapping in trusted Python code. If configuration must
request a broader operation, expose a narrow application-owned wrapper whose
behavior is bounded by its target name.

## Uncontrolled execution

Targets that execute code, import modules, load native libraries, spawn
processes, or deserialize executable objects cannot be authorized. This
includes families such as `eval` and `exec`, subprocess and shell execution,
dynamic import loaders, `ctypes` library loading, and pickle-backed loaders.

These operations should remain in trusted Python code rather than composed
configuration.

## Reentrant instantiation

Do not configure `hydra.utils.instantiate`, `hydra.utils.call`, or Hydra's
internal instantiate function as `_target_`. Reentrant instantiation does not
safely preserve the effective policy. Call `instantiate()` from trusted Python
code and pass or establish the intended execution whitelist there.

## Explicitly disabling checks

:::warning

`UNSAFE_DISABLE_EXECUTION_CHECKS` disables both whitelist and blacklist checks.
It permits every target described on this page. Use it only with trusted code
in a trusted runtime environment, where every relevant configuration source is
also trusted and unrestricted Python execution is intentional.

:::

To disable checks explicitly for one direct `instantiate()` call:

```python
from hydra.utils import UNSAFE_DISABLE_EXECUTION_CHECKS, instantiate

obj = instantiate(
    cfg.component,
    _execution_whitelist_=UNSAFE_DISABLE_EXECUTION_CHECKS,
)
```
