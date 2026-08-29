---
id: instantiate_resolution
title: Instantiate resolution and call-site overrides
---

Hydra 1.4 changes when `hydra.utils.instantiate()` resolves configuration
values and how call-site arguments interact with the input configuration.

The examples on this page pass `_execution_whitelist_` because trusted call-site
code is responsible for authorizing configured targets in Hydra 1.4. See the
[execution whitelist migration guide](/docs/upgrades/1.3_to_1.4/execution_whitelist)
for the associated security and migration context.

## Benefits

`instantiate()` no longer eagerly resolves the full input configuration before
it starts instantiating targets. Instead, it traverses the configuration and
resolves each value when that value is needed. Calls on OmegaConf inputs without
call-site overrides also avoid the former additional full-tree copy. When
overrides are present, Hydra uses a private copy so configured interpolations
resolve against the call-site values without modifying the input configuration.

This has several benefits:

- Unrelated parts of the configuration tree are not resolved.
- A call-site argument can replace an unresolvable configured value without
  forcing Hydra to resolve the replaced value first.
- An earlier target can establish runtime state, such as registering a custom
  resolver, before a later argument is resolved.
- With `_recursive_=False`, the default `_convert_="none"`, and no call-site
  overrides, Hydra no longer makes a final copy of OmegaConf containers before
  the target call. Containers passed through from the input tree retain their
  identity, lazy interpolations, ancestor context, resolver cache, and inherited
  flags.

## Compatibility impact

Call-site arguments determine the arguments passed to the target, but they do
not modify the input configuration itself. Hydra applies them to a private copy
used for resolution, so interpolations in other configured arguments resolve
against the effective values.

Call-site arguments are not generally coerced or validated against the
corresponding field in an input Structured Config. Dictionary overrides of
Structured Config nodes are the exception, as described below. Primitive
values, native `list`, `tuple`, and `dict` containers, and OmegaConf containers
remain supported configuration inputs. They retain Hydra's normal
instantiation and conversion where applicable.

Plain Python call-site overrides must be concrete runtime values. Hydra rejects
`???` and strings containing OmegaConf interpolation syntax (`${...}`),
including inside native containers. Explicit OmegaConf containers retain
normal OmegaConf semantics and may contain missing values or interpolations.

When a `dict` or `DictConfig` call-site argument overrides a parameter of the
target being instantiated, it is handled according to the configured parameter
value:

- If the configured value is a Structured Config node, Hydra validates the
  merged dictionary against the schema. Fields that the dictionary does not
  name retain their configured values, and interpolations within the node can
  resolve against the merged values.
- Otherwise, if the configured mapping contains `_target_`, Hydra merges the
  dictionary into that target config, preserving its target, instantiation
  settings, and arguments that the dictionary does not name. `_recursive_`
  controls whether the result is instantiated or passed through; it does not
  change this merge behavior.
- Any other configured mapping is replaced entirely.

Hydra uses the configured parameter's effective value after interpolation to
select among these cases. If the interpolation cannot be resolved, the
call-site dictionary replaces it.

The Structured Config behavior is an exception to replacement. Hydra 1.3
instead merged dictionaries into configured plain mappings, so the target
received configured keys that the call-site argument did not name:

```python
from hydra.utils import instantiate

cfg = {
    "_target_": "builtins.dict",
    "tags": {"env": "prod", "team": "ml"},
}

result = instantiate(cfg, tags={"env": "dev"}, _execution_whitelist_="builtins.dict")
assert result["tags"] == {"env": "dev"}
```

Hydra 1.3 returned `{"env": "dev", "team": "ml"}` for `tags`.

For example, a configured target retains its merge behavior:

```python
cfg = {
    "_target_": "builtins.dict",
    "optimizer": {"_target_": "builtins.dict", "lr": 0.1, "momentum": 0.5},
}

result = instantiate(
    cfg,
    optimizer={"lr": 0.3},
    _execution_whitelist_="builtins.dict",
)
assert result["optimizer"] == {"lr": 0.3, "momentum": 0.5}
```

To pass a merged value, merge it explicitly at the call-site, for example with
`OmegaConf.merge(cfg["tags"], {"env": "dev"})`.

Hydra 1.4 intentionally changes the treatment of already-constructed dataclass
and attrs instances passed as call-site arguments. They are now regular runtime
objects and remain unchanged, even if they define `_target_`. Hydra no longer
implicitly converts them to Structured Configs, merges them with the input
configuration, or recursively instantiates them.

To use a dataclass or attrs instance as configuration, explicitly convert it
with `OmegaConf.structured(instance)`:

```python
from dataclasses import dataclass

from omegaconf import OmegaConf

from hydra.utils import instantiate


@dataclass
class ChildConfig:
    _target_: str = "builtins.dict"
    value: int = 10


child = ChildConfig()
cfg = {"_target_": "builtins.dict"}

runtime_result = instantiate(
    cfg,
    child=child,
    _execution_whitelist_="builtins.dict",
)
assert runtime_result["child"] is child

config_result = instantiate(
    cfg,
    child=OmegaConf.structured(child),
    _execution_whitelist_="builtins.dict",
)
assert config_result["child"] == {"value": 10}
```

For example:

```python
from omegaconf import OmegaConf

from hydra.utils import instantiate

cfg = OmegaConf.create(
    {
        "_target_": "builtins.dict",
        "b": 200,
        "c": "${b}",
    }
)

result = instantiate(cfg, b=99, _execution_whitelist_="builtins.dict")
assert result == {"b": 99, "c": 99}
```

Hydra 1.4 leaves `cfg` unchanged while resolving `${b}` against the effective
call-site value. This preserves the result produced by Hydra 1.3 without
eagerly resolving the full configuration.

With `_recursive_=False`, `_convert_="none"`, and no call-site overrides,
OmegaConf containers are no longer copied and detached before the target call.
The target receives the same `DictConfig`, `ListConfig`, or `TupleConfig`
object from the input tree. Mutations made by the target are therefore visible
through the original configuration, and an attached subtree retains its
ancestor configuration when stored or serialized. When call-site overrides
are present, configured containers come from Hydra's private resolution copy.
Containers supplied directly as call-site values still retain their identity.
Other conversion modes retain their documented conversion behavior.

To pass an independent Config object instead, create one explicitly:

```python
cfg = OmegaConf.create(
    {
        "_target_": "builtins.dict",
        "_recursive_": False,
        "payload": {"value": 10, "alias": "${.value}"},
    }
)
independent = OmegaConf.create(cfg.payload)
result = instantiate(
    cfg,
    payload=independent,
    _execution_whitelist_="builtins.dict",
)
assert result["payload"] is independent
```

`OmegaConf.create()` preserves lazy interpolations within the copied container.
If an interpolation depends on an ancestor outside that container, resolve it
while copying:

```python
independent = OmegaConf.create(
    OmegaConf.to_container(cfg.payload, resolve=True)
)
```
