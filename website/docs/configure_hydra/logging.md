---
id: logging
title: Customizing logging
sidebar_label: Customizing logging
---

import {ExampleGithubLink} from "@site/src/components/GithubLink"

<ExampleGithubLink text="Example application" to="examples/configure_hydra/logging"/>

Hydra is configuring Python standard logging library with the dictConfig method. You can learn more about it [here](https://docs.python.org/3/howto/logging.html).
There are two logging configurations, one for Hydra itself and one for the executed jobs.

This example demonstrates how to customize the logging behavior of your Hydra app, by making the following changes
to the default logging behavior:

 * Outputs only to stdout (no log file)
 * Output a simpler log line pattern

```yaml title="config.yaml"
defaults:
  - override hydra/job_logging: custom
```

```yaml title="hydra/job_logging/custom.yaml"
version: 1
formatters:
  simple:
    format: '[%(levelname)s] - %(message)s'
handlers:
  console:
    class: logging.StreamHandler
    formatter: simple
    stream: ext://sys.stdout
root:
  handlers: [console]

disable_existing_loggers: false
```

<details>
<summary>Security considerations</summary>

Python logging configuration can import and call the values of handler
`class` keys and formatter, filter, and handler `()` keys. Configure a target
whitelist in trusted Python code whenever logging configuration may come from
an untrusted source:

```python
import hydra

@hydra.main(
    version_base=None,
    config_path="conf",
    config_name="config",
    target_whitelist=["my_app.logging.CustomHandler"],
)
def my_app(cfg):
    ...
```

Hydra automatically permits the exact targets used by its built-in logging
configurations. Add any application-defined handler, formatter, filter, queue,
or listener targets to the whitelist. The whitelist must come from trusted
Python code; do not derive it from composed configuration.

Hydra does not support replacing Python's global
`logging.config.dictConfigClass`. A custom configurator would bypass Hydra's
target authorization. Express custom logging components in the logging
configuration and authorize their targets instead.

See [Target whitelist](/docs/upgrades/1.3_to_1.4/instantiate_target_whitelist)
for the shared whitelist rules and migration guidance for both logging and
`instantiate()`.

Resolving additional logging targets without a target whitelist retains the
legacy blocklist behavior in Hydra 1.4, but is deprecated and will become an
error in Hydra 1.5. Use `UNSAFE_ALLOW_ALL_TARGETS` only when all composed
logging configuration is trusted and unrestricted target resolution is
intentional.

</details>

This is what the default logging looks like:
```
$ python my_app.py hydra/job_logging=default
[2020-08-24 13:43:26,761][__main__][INFO] - Info level message
```

And this is what the custom logging looks like:
```text
$ python my_app.py 
[INFO] - Info level message
```
