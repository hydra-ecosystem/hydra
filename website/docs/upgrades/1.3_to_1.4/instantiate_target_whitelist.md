---
id: instantiate_target_whitelist
title: Instantiate target whitelist
---

Running `hydra.utils.instantiate()` on config nodes from untrusted sources can
result in arbitrary code execution. This is a security risk because configs are
sometimes bundled with packages, models, checkpoints, or other downloaded
artifacts.

To address this, Hydra 1.4 deprecates resolving `_target_` values unless
trusted Python code at the callsite also provides `_target_whitelist_`.

For the full API reference, see
[Instantiating objects with Hydra](/docs/advanced/instantiate_objects/overview).

## Update direct calls

If your code calls `instantiate()` directly, pass the targets that call is
expected to resolve:

```python
from hydra.utils import instantiate

model = instantiate(cfg.model, _target_whitelist_="my_app.models.*")
```

## Update wrapped calls

If another function calls `instantiate()` internally, put the whitelist around
that call. This is also useful when calling `instantiate()` multiple times with
the same whitelist.

```python
from hydra.utils import target_whitelist

with target_whitelist("my_app.*"):
    framework_function(cfg)
```

## Framework authors

Framework authors should whitelist framework-owned targets around the internal
`instantiate()` calls that resolve framework config. Trust decisions for
application-owned targets should stay with the application. If framework code
also instantiates application objects, the application can wrap the framework
call with its own whitelist.

For example, a framework can whitelist its own launcher target:

```python
from hydra.utils import instantiate, target_whitelist

def train(cfg):
    with target_whitelist("my_framework.*"):
        launcher = instantiate(cfg.launcher)

    model = instantiate(cfg.model)
    launcher.run(model)
```

Application code can then add its own targets around the framework call:

```python
with target_whitelist("my_app.*"):
    train(cfg)
```

The inner framework whitelist adds `my_framework.*`; the outer application
whitelist adds `my_app.*`. The framework does not need to know which
application model targets are trusted.

## Plugin authors

Hydra 1.4 instantiates launcher and sweeper plugin configs non-recursively.
Hydra core instantiates only the registered plugin class. If your plugin config
contains nested `_target_` values, accept the nested config in the plugin
constructor and call `instantiate()` from plugin code with a plugin-owned
whitelist.

## Choose target patterns

Whitelist entries may be exact targets or package prefixes ending in `.*`.
The wildcard `*` by itself is not allowed.

Be careful with namespace packages and plugin namespaces. A whitelist entry such
as `my_app.*` allows any importable target under that Python namespace, including
modules contributed by other installed distributions. For shared namespaces,
prefer exact target names or narrower prefixes.

## Migrate direct `functools.partial` targets

Do not use `functools.partial` as `_target_`. It accepts the effective callable
as config data. Hydra checks the completed partial's effective callable against
the active target policy, so a target whitelist must authorize both the direct
`functools.partial` spelling and the effective callable. Equivalent constructor
spellings such as `functools.partial.__new__` receive the same check.

Use Hydra's native partial support instead. Replace:

```yaml
_target_: functools.partial
_args_:
  - _target_: hydra.utils.get_class
    path: my_app.Optimizer
lr: 0.01
```

with:

```yaml
_target_: my_app.Optimizer
_partial_: true
lr: 0.01
```

Direct `functools.partial` targets remain deprecated and will become an error in
Hydra 1.5. They cannot use `_partial_: true` with a real target whitelist
because construction—and therefore validation of the effective callable—would
be deferred. The explicit `UNSAFE_ALLOW_ALL_TARGETS` escape hatch permits that
deferred behavior outside the target whitelist's security guarantee.
Equivalent constructor spellings cannot construct partial subclasses while
safety checks are active because subclass overrides can hide their invocation
behavior.

## Replace generic operator dispatch

Hydra blocklists `operator.call`, `operator.attrgetter`, and
`operator.methodcaller` on the legacy path and refuses to authorize them
through `_target_whitelist_`. These targets let config data select the effective
callable, attribute, or method instead of naming it as `_target_`, which can
extend a narrow whitelist entry into generic selection or dispatch authority.
Set `_target_` to the intended callable, or call it from trusted Python code,
instead.

## Authorize config-selected callable results

When `hydra.utils.get_class`, `get_method`, `get_static_method`, or
`get_object` is itself an instantiate target, its `path` value selects another
object. Authorize both the helper and the selected path from trusted code:

```python
obj = instantiate(
    {
        "_target_": "hydra.utils.get_method",
        "path": "my_app.make_model",
    },
    _target_whitelist_=[
        "hydra.utils.get_method",
        "my_app.make_model",
    ],
)
```

Hydra applies the active blocklist or whitelist to the selected path and
rechecks callable results by canonical identity. This prevents a trusted
whitelist entry for the helper from authorizing an unrelated callable selected
by config data.

Hydra applies the same result check when `builtins.getattr` returns a callable.
Ordinary non-callable attribute values remain unchanged. When the result is a
callable, authorize its canonical target in addition to `builtins.getattr`.

Discovery helpers and `builtins.getattr` cannot use `_partial_: true` with a
real target whitelist. The partial could receive its selected path or attribute
after instantiate's authorization has finished. Resolve the value immediately,
or expose a narrow trusted Python wrapper for the intended operation. The
explicit `UNSAFE_ALLOW_ALL_TARGETS` escape hatch keeps discovery fully deferred.
On the legacy no-whitelist path, immediately selected callables are still
checked against the blocklist.

Do not configure `hydra.utils.instantiate`, `hydra.utils.call`, or the internal
`instantiate` function as `_target_`. Hydra refuses to authorize these aliases
because a reentrant call cannot yet safely inherit the effective whitelist.
Call `instantiate()` from trusted Python code instead.

## Legacy behavior

To preserve legacy all-target behavior, use `UNSAFE_ALLOW_ALL_TARGETS`
explicitly:

```python
from hydra.utils import UNSAFE_ALLOW_ALL_TARGETS, instantiate

obj = instantiate(cfg.component, _target_whitelist_=UNSAFE_ALLOW_ALL_TARGETS)
```

Use this only when you intentionally want the old behavior.

Calling `instantiate()` without `_target_whitelist_` still works in Hydra 1.4,
but it emits a deprecation warning when resolving `_target_`.
Legacy mode continues to use Hydra's target blocklist as defense-in-depth.
