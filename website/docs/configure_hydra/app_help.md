---
id: app_help
title: Customizing Application's help
sidebar_label: Customizing Application's help
---

import {ExampleGithubLink} from "@site/src/components/GithubLink"

<ExampleGithubLink text="Example application" to="examples/configure_hydra/custom_help"/>

Hydra provides two different help options:
* `--help` : Application specific help
* `--hydra-help` Hydra specific help. 

If a Defaults List choice is mandatory (`group: ???`), `--help` still lists the
available options. `$CONFIG` shows the partial configuration until a choice is
provided.

Example output of `--help`:
```text
$ python my_app.py --help
== AwesomeApp ==

This is AwesomeApp!
You can choose a db driver by appending
== Configuration groups ==
Compose your configuration from those groups (db=mysql)

db: mysql, postgresql


== Config ==
This is the config generated for this run.
You can override everything, for example:
python my_app.py db.user=foo db.pass=bar
-------
db:
  driver: mysql
  user: omry
  pass: secret

-------

Powered by Hydra (https://hydra.cc)
Use --hydra-help to view Hydra specific help
```

This output is generated from the following config group option (selected in `config.yaml` to be used by default): 
```yaml title="hydra/help/my_app_help.yaml"
# App name, override to match the name your app is known by
app_name: AwesomeApp

# Help header, customize to describe your app to your users
header: == ${hydra.help.app_name} ==

footer: |-
  Powered by Hydra (https://hydra.cc)
  Use --hydra-help to view Hydra specific help

# Basic Hydra flags:
#   $FLAGS_HELP
#
# Config groups, choose one of:
#   $APP_CONFIG_GROUPS: All config groups that does not start with hydra/.
#   $HYDRA_CONFIG_GROUPS: All the Hydra config groups (starts with hydra/)
#
# Configuration generated with overrides:
#   $CONFIG : Generated config
#
template: |-
  ${hydra.help.header}

  This is ${hydra.help.app_name}!
  You can choose a db driver by appending
  == Configuration groups ==
  Compose your configuration from those groups (db=mysql)

  $APP_CONFIG_GROUPS

  == Config ==
  This is the config generated for this run.
  You can override everything, for example:
  python my_app.py db.user=foo db.pass=bar
  -------
  $CONFIG
  -------
  
  ${hydra.help.footer}
```
