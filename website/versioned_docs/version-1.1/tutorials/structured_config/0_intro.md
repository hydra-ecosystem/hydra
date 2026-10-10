---
id: intro
title: Introduction to Structured Configs
sidebar_label: Introduction to Structured Configs
---

import GithubLink from "@site/src/components/GithubLink"

This is an advanced tutorial that assumes that you are comfortable with the concepts introduced in the [Basic Tutorial](/tutorials/basic/your_first_app/1_simple_cli.md).
The examples in this tutorial are available <GithubLink to="examples/tutorials/structured_configs">here</GithubLink>.

Structured Configs use Python [dataclasses](https://docs.python.org/3.7/library/dataclasses.html) to 
describe your configuration structure and types. They enable:

* **Runtime type checking** as you compose or mutate your config 
* **Static type checking** when using static type checkers (mypy, PyCharm, etc.)

#### Structured Configs supports:
- Primitive types (`int`, `bool`, `float`, `str`, `Enums`) 
- Nesting of Structured Configs
- Containers (List and Dict) containing primitives or Structured Configs
- Optional fields

#### Structured Configs Limitations:
- `Union` types are not supported (except `Optional`)
- User methods are not supported

#### There are two primary patterns for using Structured configs

- As a [config](/tutorials/structured_config/1_minimal_example.md), in place of configuration files (often a starting place)
- As a [config schema](/tutorials/structured_config/5_schema.md) validating configuration files (better for complex use cases)

With both patterns, you still get everything Hydra has to offer (config composition, Command line overrides etc).
This tutorial covers both. \***Read it in order**\*.

Hydra supports OmegaConf's Structured Configs via the `ConfigStore` API.
This tutorial does not assume any knowledge of them.
It is recommended that you visit the <a class="external" href="https://omegaconf.cli.dev/docs/concepts/structured-configs" target="_blank" rel="noopener noreferrer">OmegaConf Structured Configs page</a> to learn more later.
