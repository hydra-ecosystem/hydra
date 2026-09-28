---
id: hydra-command-line-flags
title: Hydra's command line flags
---

Hydra is using the command line for two things:
- Controlling Hydra
- Configuring your application (See [Override Grammar](override_grammar/basic.md))

Arguments prefixed by - or -- control Hydra; the rest are used to configure the application.

Information about Hydra:
- **--hydra-help**: Shows Hydra specific flags
- **--version**: Show Hydra's version and exit

Information provided by the Hydra app:
- **--help,-h**: Shows the application's help. This can be [customized](configure_hydra/app_help.md).

Debugging assistance:
- **--cfg,-c**: Show config instead of running. Takes as parameter one of `job`, `hydra` or `all`.
- **--resolve**: Used in conjunction with the `--cfg` flag; resolve interpolations in the config before printing it.
- **--package,-p**: Used in conjunction with --cfg to select a specific config package to show.
- **--info,-i**: Print Hydra information. This includes installed plugins, Config Search Path, Defaults List, generated config and more.


Running Hydra applications:
- **--run,-r**: Run is the default mode and is not normally needed.
- **--multirun,-m**: Run multiple jobs with the configured launcher and sweeper. See [Multi-run](/tutorials/basic/running_your_app/2_multirun.md).
  <br/><br/>
- **--config-path,-cp**: Overrides the `config_path` specified in `hydra.main()`. The `config_path` is absolute or relative to the Python file declaring `@hydra.main()`.
- **--config-name,-cn**: Overrides the `config_name` specified in `hydra.main()`.
- **--config-dir,-cd**: Adds an additional config directory to the [config search path](search_path.md).   
  A relative directory is resolved from the current working directory. This is
  useful for installed apps that want to allow their users to provide additional configs.

Misc:
- **--shell-completion,-sc**: Install or Uninstall [shell tab completion](/tutorials/basic/running_your_app/6_tab_completion.md).
