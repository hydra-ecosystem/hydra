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

Runtime-introspection APIs that expose live frames or tracebacks are also
permanently restricted. This includes traceback walkers and task stack access;
otherwise configuration could reach active function locals, globals, or
builtins and mutate existing Python code or authorization state.

## Dynamic selection and dispatch

Attribute operations such as `builtins.getattr`, `hasattr`, `setattr`, and
`delattr` let configuration select an attribute or descriptor operation as data.
Generic `operator` helpers such as `call`, `attrgetter`, `methodcaller`,
`getitem`, `itemgetter`, `setitem`, `delitem`, and `contains` have the same
problem.

Generic `__call__` indirection is authorized as the callable it actually
invokes; spelling an allowed target through `.__call__` does not bypass its
blacklist or whitelist status. Low-level descriptor `__get__` operations remain
blocked because configuration would select the descriptor and receiver as data.
`locals` and both forms of `vars` are also blocked because they expose caller or
object namespaces; rejecting the otherwise-safe `vars(obj)` form is intentional
collateral damage for a simple fail-closed rule.

The `inspect` module is also blocked because its reflection helpers expose live
Python objects and code metadata through ordinary containers.
Live-frame access through `sys._getframe`, `sys._current_frames`, and
`traceback.walk_stack` is likewise blocked. Current-exception access through
`sys.exception` and `sys.exc_info` is blocked because exception tracebacks lead
back to live frames. The `gc` module and runtime object enumerators such as
`sys._current_exceptions` are blocked because they expose live object graphs
without using normal attribute access.

Name the intended callable directly as `_target_`, or perform the dynamic
selection in trusted Python code.

## Process environment mutation

Targets that modify the process environment are permanently restricted. This
includes `os.putenv`, `os.unsetenv`, and mutating methods reached through
`os.environ` or `os.environb`, such as assignment, deletion, `update`, `clear`,
`pop`, `popitem`, and `setdefault`. Direct mutation of their backing mappings
and attributes is also rejected.

This restriction does not block environment reads, including OmegaConf's
`oc.env` resolver. Perform required environment mutation in trusted Python code
or expose a narrow application-owned wrapper whose behavior is bounded by its
target name.

## Callback dispatch and callable wrappers

Dispatchers such as `builtins.map`, `builtins.filter`, predicate-based
`itertools` helpers, `functools.reduce`, `itertools.starmap`, and executor or
pool submission APIs invoke a config-supplied callback. Invocation may continue
outside Hydra's immediate callable-result checks.

Callable binding and wrapper helpers can similarly defer or obscure the
effective callable. Examples include `classmethod`, `staticmethod`,
`property`, `functools.cached_property`, the equivalent `abc` wrappers,
`types.DynamicClassAttribute`, `enum.property`,
`contextlib.contextmanager`, `contextlib.asynccontextmanager`,
`functools.lru_cache`, `partialmethod`, `singledispatch`, `types.coroutine`, and
`update_wrapper`.

Perform this dispatch or wrapping in trusted Python code. If configuration must
request a broader operation, expose a narrow application-owned wrapper whose
behavior is bounded by its target name.

## Formatting traversal

Selecting `str.format`, `str.format_map`, or the traversal methods on
`string.Formatter`, `logging.Formatter`, or `logging.StrFormatStyle` as a
configured target is permanently restricted. Python format fields can traverse
attributes and mapping items, including live function globals and other
implementation metadata. The equivalent `collections.UserString.format` and
`format_map` methods are restricted as well. Hydra logging configuration also
rejects the `{` format style; use `%` or `$` style instead. A configured
formatter factory or class result that is not a `logging.Formatter` is ignored
with a warning, leaving the handler's default formatter in place. These
restrictions do not affect ordinary format strings used by trusted Python code
or OmegaConf.

## Uncontrolled execution

Targets that execute code, import modules, load native libraries, spawn
processes, or deserialize executable objects cannot be authorized. This
includes families such as `eval` and `exec`, subprocess and shell execution,
dynamic import loaders, `ctypes` library loading, and pickle-backed loaders.

The `yaml.*` namespace is restricted except for `yaml.safe_load`,
`yaml.safe_load_all`, `yaml.safe_dump`, and `yaml.safe_dump_all`. These exceptions
allow only the exact functions, not their attributes or other YAML targets.

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
