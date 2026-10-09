---
id: debugging
title: Debugging
sidebar_label: Debugging
---
Hydra provides a few options to improve debuggability.

### Printing the configuration
Print the config for your app without running your function by adding `--cfg` or `-c` to the command line.

The `--cfg` option takes one argument indicating which part of the config to print:
* `job`: Your config
* `hydra`: Hydra's config
* `all`: The full config, which is a union of `job` and `hydra`.

```yaml
# A normal run:
$ python my_app.py
MySQL connecting to localhost with user=root and password=1234

# just show the config without running your function:
$ python my_app.py --cfg job
db:
  host: localhost
  user: root
  password: 1234
```
The printed config includes any modifications done via the command line:
```yaml {3}
$ python my_app.py db.host=10.0.0.1 --cfg job
db:
  host: 10.0.0.1
  user: root
  password: 1234
```

You can use --package or -p to display a subset of the configuration:
```yaml
python my_app.py --cfg hydra --package hydra.job
# @package hydra.job
name: my_app
config_name: config
...
```

By default, config interpolations are not resolved. To print resolved config use the `--resolve` flag in addition to the `--cfg` flag
### Info
The `--info` flag can provide information about various aspects of Hydra and your application:
 - `--info all`: Default behavior, prints everything
 - `--info aliases`: Lists override aliases and shows how supplied overrides expand,
   including unchanged inputs. This does not require full composition.
 - `--info config`: Prints information useful to understanding the config composition:  
   Config Search Path, Defaults Tree, Defaults List and the final config.
 - `--info defaults`: Prints the Final Defaults List
 - `--info defaults-tree`: Prints the Defaults Tree
 - `--info plugins`: Prints information about installed plugins

For example, if `bs` aliases `trainer.batch_size`,
`python my_app.py --info aliases bs=32` shows
`bs=32 -> trainer.batch_size=32`. See [Override aliases](/advanced/override_aliases.md)
for definitions and examples. Expansion is also shown under Hydra debug logging.
