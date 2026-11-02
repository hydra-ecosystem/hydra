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

## Threat model

### Hydra 1.3

Configuration must be trusted. Hydra's blacklist blocks known dangerous targets,
but it is not guaranteed to prevent all attacks and must not be relied on as a
security boundary.

### Hydra 1.4 with an execution whitelist

Configuration can select targets approved by trusted Python code. It cannot add
its own permissions through Hydra's configuration interfaces. Installed Python
code and the application are trusted.

Whitelisting a function means trusting what it can do with the arguments
configuration gives it. If it can run code, launch processes, or change the
environment, configuration can request those actions. Hydra does not sandbox
the function's internal behavior. Use narrow application functions when
configuration should control only a limited operation.

Hydra still blocks protected targets and objects, even when whitelisted. These
checks limit direct access through Hydra to its policy state, live frames, and
existing Python code. They do not stop an authorized function from accessing or
modifying that state internally. Hydra checks immediate results, but does not
recursively inspect arbitrary containers.
See [Restricted targets](./execution_whitelist/restricted_targets.md).

### Hydra 1.4 legacy mode

Running without an execution whitelist is deprecated and requires trusted
configuration. Its blacklist is not guaranteed to prevent all attacks and must
not be relied on as a security boundary.

### Hydra 1.5

Hydra 1.5 will remove legacy mode and its blacklist fallback. Applications must
provide an execution whitelist or explicitly disable checks. Protected-target
restrictions will remain when using a whitelist.

### Explicit unsafe opt-out

In Hydra 1.4 and 1.5, trusted Python code can explicitly disable execution checks
with `UNSAFE_DISABLE_EXECUTION_CHECKS`. This disables both whitelist and
blacklist checks and requires trusted configuration.

## Configure an application

Use `execution_whitelist` on `@hydra.main()` to authorize targets selected by
`hydra.utils.instantiate()` and its `call()` alias in the application context,
as well as targets selected during Hydra logging setup. Hydra carries this
policy into jobs started through its launcher interfaces. When only this call
site needs the policy, define it inline as an immutable tuple:

```python
import hydra


@hydra.main(
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

Entries can be exact targets or application and third-party package prefixes
ending in `.*`. Python standard-library and Hydra targets require exact entries,
including targets in their submodules. For example, use `os.getcwd` or
`hydra.utils.get_class`; `os.*` and `hydra.utils.*` are rejected. The wildcard
`*` by itself is not allowed.

Be careful with namespace packages and plugin namespaces. An entry such as
`my_app.*` permits any importable target under that namespace, including
modules contributed by other installed distributions. Prefer exact names or
narrower prefixes for shared namespaces.

## Python logging configured by Hydra

The execution whitelist controls which Python components logging configuration
can select. Hydra automatically permits its built-in logging components,
including `logging.FileHandler`. This does not restrict file destinations or
sandbox an authorized component's behavior.

When Hydra configures Python logging, its use of
`logging.config.dictConfig()` can import handler `class` values and call
formatter, filter, handler, queue, and listener `()` values. Add custom logging
components selected by Hydra's logging configuration to the application
execution whitelist:

```python
@hydra.main(
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

Hydra authorizes a factory before calling it. A return-type check verifies that
the result is an appropriate logging component; it cannot undo side effects
from an explicitly authorized factory. The built-in allowance remains an exact
list and does not authorize arbitrary factories or a `logging.*` namespace.

This does not protect calls that application code makes directly to
`logging.config.dictConfig()` or other Python logging configuration APIs.

## Continue reading

- [Scopes and application integration](./execution_whitelist/scopes.md) covers
  direct calls, nested contexts, shared policies, frameworks, and threads.
- [Execution authorization rules](./execution_whitelist/authorization_rules.md) covers
  configured identities, indirectly selected callables, and partial
  instantiation.
- [Restricted targets](./execution_whitelist/restricted_targets.md) explains
  operations that cannot be authorized and the explicit unsafe opt-out.
