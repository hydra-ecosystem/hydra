---
id: strict_mode_flag_deprecated
title: strict flag mode deprecation
---
## Overview
The strict mode is a flag added to `@hydra.main()` to enable two features:
- Command line error detection (overriding a field not in the config)
- Runtime config access error detection (accessing/setting a field not in the config)

This flag is now deprecated and the ability to turn it off will be removed in Hydra 1.1.

## Alternatives to `strict=False`
Below are a few common reasons for people disabling strict mode along with recommended alternatives.

### Adding config fields through the command line
With strict mode disabled; you can add fields not specified in config file through the command line.
Hydra 1.0 introduces the + prefix to command line overrides, enabling the addition of fields not in the config file.

```yaml title="config.yaml"
db:
  driver: mysql
```

```yaml {1,6}
$ python my_app.py +db.host=localhost
db:
  driver: mysql
  host: localhost
```

### Adding fields at runtime
When strict mode is disabled, you can add fields to your config at runtime.
Strict mode is implemented by setting the OmegaConf `struct` flag to True on the root of the config.
- You can disable the struct flag a specific context using `open_dict`.
- You can disable the struct flag permanently for your config using `OmegaConf.set_struct(cfg, False)`.

Learn more about OmegaConf struct flag <a class="external" href="https://omegaconf.cli.dev/docs/guides/flags#struct" target="_blank" rel="noopener noreferrer">here</a>.


### Field existence check
With strict mode disabled, you can check if a field is in the config by comparing it to None:
```python
if cfg.host is None:
    # host is not in the config
```
This will no longer work because an exception will be thrown when the `host` field is accessed.  
Use `in` or `hasattr` instead:
```python
if "host" not in cfg:
    # host is not in the config

if not hasattr(cfg, "host"):
    # host is not in the config
```