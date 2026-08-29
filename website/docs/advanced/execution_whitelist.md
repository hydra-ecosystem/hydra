---
id: execution_whitelist
title: Execution whitelist
sidebar_label: Execution whitelist
---

Hydra configuration can select importable Python callables. This is useful for
`hydra.utils.instantiate()` and for Python logging configured by Hydra, but it
also means that an untrusted config can select code to execute.

The Hydra execution whitelist limits those choices to targets approved by
trusted Python code. The same whitelist applies to object instantiation and
logging setup.

:::warning

The execution whitelist is a trust decision and must come from trusted Python
code. Do not construct it from composed configuration: a configuration that can
choose both targets and their whitelist can authorize its own code and defeat
the security boundary.

:::

## Configure an application

Use `execution_whitelist` on `@hydra.main()` to authorize targets selected by
`hydra.utils.instantiate()` and its `call()` alias in the application context,
as well as targets selected during Hydra logging setup. Hydra carries this
policy into jobs started through its launcher interfaces. When only this call
site needs the policy, define it inline as an immutable tuple:

```python
import hydra


@hydra.main(
    version_base=None,
    config_path="conf",
    config_name="config",
    execution_whitelist=(
        "my_app.logging.CustomHandler",
        "my_app.models.*",
    ),
)
def my_app(cfg):
    ...
```

Entries can be exact targets or package prefixes ending in `.*`. The wildcard
`*` by itself is not allowed.

Be careful with namespace packages and plugin namespaces. An entry such as
`my_app.*` permits any importable target under that namespace, including
modules contributed by other installed distributions. Prefer exact names or
narrower prefixes for shared namespaces.

## Python logging configured by Hydra

When Hydra configures Python logging, its use of
`logging.config.dictConfig()` can import handler `class` values and call
formatter, filter, handler, queue, and listener `()` values. Add custom logging
components selected by Hydra's logging configuration to the application
execution whitelist:

```python
@hydra.main(
    version_base=None,
    config_path="conf",
    config_name="config",
    execution_whitelist=("my_app.logging.CustomHandler",),
)
def my_app(cfg):
    ...
```

Hydra automatically permits the exact targets used by its built-in logging
configurations during logging setup. It does not support replacing Python's
global `logging.config.dictConfigClass`; a custom configurator would bypass
Hydra's checks. Express custom components in logging configuration and
whitelist their targets instead.

This does not protect calls that application code makes directly to
`logging.config.dictConfig()` or other Python logging configuration APIs.

## Continue reading

- [Scopes and application integration](./execution_whitelist/scopes.md) covers
  direct calls, nested contexts, shared policies, frameworks, and threads.
- [Target authorization rules](./execution_whitelist/target_rules.md) covers
  configured identities, indirectly selected callables, and partial
  instantiation.
- [Restricted targets](./execution_whitelist/restricted_targets.md) explains
  operations that cannot be authorized and the explicit unsafe opt-out.
