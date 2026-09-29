---
id: terminology
title: Terminology
---
This page describes some common concepts in Hydra, most of which are covered in greater details throughout the documentation.
Examples of many of the following concepts are in the [Examples section](#example-of-core-concepts).

## Input Configs
Input configs are building blocks used to construct the [Output Config](#output-config) consumed by the application.
They can be grouped by placing them in [Config Groups](#config-group).

### Config files
Config files are form of input configs in [YAML](https://yaml.org/) format. They can exist in the file system or
in a Python module.
```yaml title="Example config file"
user:
  name: James Bond
  age: 7
```

### Structured Config
This term has two common meanings:
1. A class decorated with [@dataclass](https://docs.python.org/3/library/dataclasses.html) or [@attr.s](https://www.attrs.org/en/stable/), or an instance of such a class which is intended to be used as config.
2. A Config object initialized from a class or object as defined in 1. Structured Configs provide additional type information that enables static and runtime type checking.

The two primary patterns for using Structured Configs are:
- As an [Input Config](#input-configs).
- As a schema validating Config Files and command line arguments.

```python title="Example Schema"
@dataclass
class User:
  name: str
  age: int
```

## Other configs
**Primary Config**: The input config named in [**@hydra.main()**](hydra_main.md) or in the [**Compose API**](compose_api.md).
**Output Config**: A config composed from the [Input Configs](#input-configs) and [Overrides](#overrides) by **@hydra.main()**, or the Compose API.

## Overrides
[Overrides](override_grammar/basic.md) are strings that can be used to manipulate the config composition process.
This includes updating, adding and deleting config values and [Defaults List](#defaults-list) options.

Overrides can be used in the command line and in the [Compose API](compose_api.md).
In the examples below, `key=value` is an override:
<div className="row">
<div className="col col--6">

```shell title="Override in the command line"
$ python my_app.py key=value

```

</div>
<div className="col col--6">

```python title="Override used in the Compose API"
cfg = compose(config_name,
              overrides=["key=value"])
```

</div>
</div>

## Defaults List
A list in an [Input Config](#input-configs) that instructs Hydra how compose the config.
```yaml title="Defaults List in a YAML config"
defaults:
  - db: mysql      # An overridable defaults list entry
  - schema/school  # A non-overridable defaults list entry
```

## Config Group
A Config Group is a directory in the [Config Search Path](#config-search-path) that contains [Input Configs](#input-configs).
Config Groups can be nested, and in that case the path elements are separated by a forward slash ('/') regardless of the operating system.

## Config Group Option
An Input Config in a Config Group. When used in a Defaults List, a Config Group Option can be a single Input Config, or a list of Input Configs from the same Config Group.

## Package
A Package is the path to node in a config. By default, the Package of a Config Group Option is derived from the Config Group.
*e.g:* Configs in **mi6/agent** will have the package **mi6.agent** by default.

### Package directive

The [Package Directive](overriding_packages.md#overriding-the-package-via-the-package-directive) specifies the root [Package](#package) of a [Config File](#input-configs). It can appear at the top of YAML config file.

## Example of Core Concepts

### Output config

<div className="row">
<div className="col col--4">

```yaml title="config.yaml"
defaults:
 - mi6/agent: james_bond

```

</div>

<div className="col col--4">

```yaml title="mi6/agent/james_bond.yaml" {1}
# @package bond.james
codename: '007'

```

</div>
<div className="col col--4">

```yaml title="Output config" {1,2}
bond:
  james:
    codename: '007'
```
</div>
</div>

- [Input Configs](#input-configs): **config.yaml**, **mi6/agent/james_bond.yaml**
- [Config Group](#config-group): mi6/agent
- [Config Group Option](#config-group-option): james_bond
- [Packages](#package): **\<empty>**, **mi6**, **mi6.agent**, **mi6.agent.codename**
- [Package directive](#package-directive): **# @package bond.james**, overriding the default Package for the containing Input Config

## Config Search Path
The [Config Search Path](search_path.md) is a list of paths that are searched in order to find configs. It is similar to
the Python [PYTHONPATH](https://docs.python.org/3/using/cmdline.html#envvar-PYTHONPATH).

## Plugins
[Plugins](plugins/intro.md) extend Hydra's capabilities. Hydra has several plugin types, for example Launcher and Sweeper.

## Special fields and directives

Hydra assigns special meaning to a few config fields and Defaults List entries. Most of these work in both YAML and Structured Configs; the `# @package` header is specific to YAML config files.

### Defaults List

- [`defaults`](defaults_list.md#introduction) lists the configs and config group options used to compose a config.
- [`_self_`](defaults_list.md#composition-order) sets where the containing config is composed relative to its Defaults List entries.
- [`override` and `optional`](defaults_list.md#introduction) modify a config group choice: `override` replaces an earlier choice, while `optional` allows a missing option.

### Packages

- [`@PACKAGE`](overriding_packages.md#overriding-packages-using-the-defaults-list) in a Defaults List entry selects where the included config is placed in the output config.
- [`_here_`, `_group_`, and `_global_`](overriding_packages.md#default-list-package-keywords) are special package values for the containing config's package, the included config group's default package, and the global package, respectively.
- [`# @package`](overriding_packages.md#overriding-the-package-via-the-package-directive) sets the package in a YAML config file header.

### Instantiation

- [`_target_`](instantiate_objects/overview.md) identifies the callable to instantiate; [`_args_`](instantiate_objects/overview.md) supplies positional arguments.
- [`_recursive_`](instantiate_objects/overview.md#disable-recursive-instantiation) controls whether nested configs are instantiated.
- [`_convert_`](instantiate_objects/overview.md#parameter-conversion-strategies) controls conversion of OmegaConf containers passed to the target.
- [`_partial_`](instantiate_objects/overview.md#partial-instantiation) creates a partial callable instead of invoking the target immediately.
