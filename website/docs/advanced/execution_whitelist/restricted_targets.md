---
id: restricted_targets
title: Restricted targets
sidebar_label: Restricted targets
---

Some targets expose or modify existing Python code, live namespaces, or
authorization state. An exact execution-whitelist entry cannot authorize those
operations. Other execution-capable targets can be explicitly authorized by
trusted Python code.

Hydra's error identifies the exact rejected target and explains why it cannot be
authorized.

These restrictions supplement the [threat model](../execution_whitelist.md#threat-model).
The whitelist authorizes selected callables; it does not sandbox their internal
operations. Protected-target and protected-object checks still apply to targets,
receivers, discovery paths, and immediate results checked by Hydra, even when a
target is explicitly whitelisted. They do not control what authorized code does
internally or recursively inspect arbitrary containers.

Runtime-introspection APIs that expose live frames or tracebacks are also
permanently restricted. This includes traceback walkers and task stack access;
otherwise configuration could reach active function locals, globals, or
builtins and mutate existing Python code or authorization state.

## Dynamic selection and dispatch

Attribute operations such as `builtins.getattr`, `hasattr`, `setattr`, and
`delattr` let configuration select an attribute or descriptor operation as data.
`operator` traversal helpers such as `attrgetter`, `methodcaller`, `getitem`,
and `itemgetter` have the same problem. Dispatch and mutation helpers such as
`call`, `contains`, `setitem`, and `delitem` can be explicitly authorized; direct
mutation of existing code or authorization state remains blocked.

Generic `__call__` indirection is authorized as the callable it actually
invokes; spelling an allowed target through `.__call__` does not bypass its
blacklist or whitelist status. Selected descriptor-binding targets, including
`builtins.property.__get__` and `types.FunctionType.__get__`, remain permanently
restricted. Other descriptor methods, such as
`functools.cached_property.__get__`, can be explicitly authorized.
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

Targets that modify the process environment require explicit authorization.
This includes `os.putenv`, `os.unsetenv`, and mutating methods reached through
`os.environ` or `os.environb`. Their arguments can select keys, values, or whole
mapping updates. Authorizing them accepts that process-wide effect.

The legacy path retains its existing environment-mutation restrictions.
Environment reads, including OmegaConf's `oc.env` resolver, remain available.
Built-in logging permissions do not authorize environment mutation; custom
logging targets still require authorization from trusted Python code.

## Callback dispatch and callable wrappers

Dispatchers such as `builtins.map`, `builtins.filter`, `functools.reduce`, and
executor submission APIs can invoke a callback selected by configuration. An
explicit whitelist can authorize this dispatch, including execution that occurs
after `instantiate()` returns. Hydra does not inspect the callback's behavior.

Ordinary callable-wrapper constructors can also be explicitly authorized.
The descriptor-binding targets described above and helpers that modify
existing functions, such as `functools.update_wrapper`, remain restricted.
Argument checks on dynamic class construction, the two-argument `iter()` form,
and non-callable mock configuration still apply.

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

## Explicit execution authorization

Trusted Python code can explicitly authorize evaluation, process launchers,
imports, native-library loading, and executable deserialization. For example:

```python
from hydra.utils import instantiate

result = instantiate(
    {"_target_": "builtins.eval", "_args_": ["40 + 2"]},
    _execution_whitelist_="builtins.eval",
)
assert result == 42
```

This accepts evaluation of the configured expression. Authorizing a loader or
process launcher similarly accepts the payload, program, and arguments selected
by configuration. An authorized callable can change process state through its
own implementation; Hydra does not sandbox it.

The legacy blacklist remains unchanged. On that path, `yaml.*` is restricted
except for the exact `yaml.safe_load`, `yaml.safe_load_all`, `yaml.safe_dump`,
and `yaml.safe_dump_all` functions. Explicit authorization can allow other YAML
loaders, including Python-object deserialization. Prefer the safe functions
unless that broader behavior is intentional.

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
