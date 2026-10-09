---
id: override_aliases
title: Override aliases
---

Override aliases provide shortcuts for config keys, package-qualified config
groups, and complete override expressions. Define them in your **primary config**:

```yaml title="config.yaml"
defaults:
  - config@_global_: null
  - _self_

trainer:
  batch_size: 8
verbose: false
action: train

hydra:
  aliases:
    config: config@_global_
    batch_size,bs: trainer.batch_size
    verbose,v: verbose=true
    check: action=check
```

Aliases expand before normal [override parsing](override_grammar/basic.md) and
classification. They work both on the command line and in the
[Compose API](compose_api.md).

| Input | Expanded override |
| --- | --- |
| `config=userconfig` | `config@_global_=userconfig` |
| `batch_size=32` or `bs=32` | `trainer.batch_size=32` |
| `bs=16,32` | `trainer.batch_size=16,32` |
| `verbose` or `v` | `verbose=true` |
| `check` | `action=check` |
| `verbose=false` | `verbose=false` |
| `check=other` | `check=other` |

### Key aliases and complete expressions

A key alias replaces the key and preserves the supplied value. A bare key alias,
such as `bs`, reports that a value is required.

A complete-expression alias supplies its own value and applies only to bare
tokens. Explicit assignments such as `verbose=false` and `check=other` remain
normal overrides; `check=other` does not become `action=other`.

Operator prefixes are preserved:

| Input | Expanded override |
| --- | --- |
| `+bs=32` | `+trainer.batch_size=32` |
| `++bs=32` | `++trainer.batch_size=32` |
| `~bs` | `~trainer.batch_size` |
| `~bs=8` | `~trainer.batch_size=8` |
| `+verbose` | `+verbose=true` |
| `~verbose` | `~verbose=true` |

The expanded override follows normal Hydra rules. For example, `+verbose` fails
if `verbose` already exists, and `~verbose` deletes it only if its value is `true`.

### Definition rules

- Define `hydra.aliases` directly in the primary config. Defaults List includes
  cannot define them, and overrides cannot change their definitions.
- Names are exact override keys. An alias named `bs` does not match `bs.child`.
- Comma-separated names declare independent aliases for the same target.
  Whitespace around names is ignored; empty or duplicate names are errors.
- Targets must be literal strings: either keys or complete override expressions.
  Interpolation in definitions is not supported.
- A declared key alias takes precedence over a real config key of the same name.
- Expansion preserves override order, values, and sweep expressions. Each alias
  expands to one override, once; there is no chaining, pattern matching, or
  expansion into multiple overrides.

For example, `a: b` and `b: c` make `a=1` expand to `b=1`, not `c=1`.

### Inspecting expansion

Application `--help` lists available aliases, and shell completion suggests them.
Use `--info aliases` to inspect definitions and the expansion of supplied inputs:

```console
$ python app.py --info aliases bs=32 verbose verbose=false
== Override aliases ==
...
Input -> Expanded override
bs=32 -> trainer.batch_size=32
verbose -> verbose=true
verbose=false -> verbose=false
```

This does not run the application or require full config composition. The same
information is included in `--info all` and Hydra debug logging. Errors involving
expanded overrides include the original alias input.

### Recorded overrides

`hydra.overrides.task` and `hydra.overrides.hydra` record the expanded strings in
input order, classified by their expanded targets. For example, `bs=32` is saved
as `trainer.batch_size=32`. Sweep jobs and experimental reruns reuse those
expanded overrides without expanding them again.

The `hydra_override_dirname` resolver also uses these expanded strings. Its
`exclude_keys` option therefore matches expanded keys, such as
`trainer.batch_size`, rather than alias names.
