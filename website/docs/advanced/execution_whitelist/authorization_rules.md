---
id: authorization_rules
title: Execution authorization rules
sidebar_label: Authorization rules
---

Hydra authorizes every callable that composed configuration can select.
Authorizing one callable does not automatically authorize another callable that
it selects or returns.

Here, selection means resolving a config-controlled target or discovery path,
or choosing a callable result based on declarative arguments. Live Python
objects embedded directly in a config by trusted Python code—including custom
string or callable subclasses—are trusted inputs and are not recursively
analyzed as a Python sandbox would analyze them.

## Configured names and resolved identities

Hydra checks a configured target name before importing it. After resolution,
Hydra also checks the callable's canonical identity. This prevents a permitted
module prefix from hiding a target imported from somewhere else. Rejections
identify both names, for example:

```text
Target 'os.system' (resolved from 'my_app.compat.system') cannot be authorized ...
```

An exact whitelist entry deliberately authorizes that configured name, including
a public re-export, unless the resolved callable is a restricted target. A
package wildcard still requires the resolved callable to belong to an authorized
package.

## Indirectly selected targets

Some targets select another callable from configuration. In those cases, both
the selector and the selected callable require authorization.

### Discovery helpers

`hydra.utils.get_class`, `get_method`, `get_static_method`, and `get_object` are
low-level lookup APIs. Direct calls do not enforce Hydra's execution policy;
their `path` must be trusted and must never come from untrusted configuration.
Use `instantiate()` for config-driven lookup.

When `hydra.utils.get_class`, `get_method`, `get_static_method`, or `get_object`
is an instantiate target, its `path` argument selects another object. Whitelist
both the helper and the selected path:

```python
method = instantiate(
    {
        "_target_": "hydra.utils.get_method",
        "path": "my_app.make_model",
    },
    _execution_whitelist_=(
        "hydra.utils.get_method",
        "my_app.make_model",
    ),
)
```

Hydra checks the selected callable by canonical identity as well as by path.

### Callable results

A factory can return a class or function for later use. Whitelisting the factory
does not authorize that callable result:

```python
model_type = instantiate(
    {
        "_target_": "my_app.get_model_class",
        "name": "resnet",
    },
    _execution_whitelist_=(
        "my_app.get_model_class",
        "my_app.models.ResNet",
    ),
)
```

Here `my_app.get_model_class` authorizes the factory call and
`my_app.models.ResNet` authorizes the returned class.

## Threat model and implementation state

Declarative instantiation configuration may be untrusted. Logging configuration,
installed Python code, and execution whitelists supplied by trusted Python code
are trusted; the execution policy is not a general Python sandbox.

Configuration cannot reference objects under `hydra._internal`, expose Hydra
module state through discovery, or modify existing Python functions and classes.
Hydra also validates and captures its immutable policy before resolving targets,
so rebinding a policy global cannot change an operation already in progress and
causes the next operation to fail closed. `UNSAFE_DISABLE_EXECUTION_CHECKS`
explicitly disables these protections for trusted configuration.

## Partial instantiation (deferred calls)

Use Hydra's native `_partial_: true` support when configuration should produce a
callable for later invocation:

```yaml
_target_: my_app.Optimizer
_partial_: true
lr: 0.01
```

Hydra authorizes the configured target when creating the partial. When the
partial is invoked, Hydra checks runtime-selected discovery paths, argument-
sensitive operations, and callable results before returning them.

Discovery helpers may also use `_partial_: true`. Hydra checks their effective
`path` when the deferred factory is invoked, including a path supplied or
replaced at runtime.

Use `_partial_: true` instead of configuring `functools.partial` as `_target_`.
Direct `functools.partial` targets are deprecated and will become an error in
Hydra 1.5.

See [Restricted targets](./restricted_targets.md) for operations that cannot be
authorized by an execution whitelist.
