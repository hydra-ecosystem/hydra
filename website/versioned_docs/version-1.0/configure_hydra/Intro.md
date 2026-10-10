---
id: intro
title: Overview
sidebar_label: Introduction
---

Many things in Hydra can be customized. This includes:
* Launcher configurations
* Sweeper configuration
* Logging configuration
* Run and Multirun output directory patterns
* Application help (--help and --hydra-help)

Hydra can be customized using the same methods you are already familiar with from the tutorial.
You can include some Hydra config snippet in your own config to override it directly, or compose in different
configurations provided by plugins or by your own code. You can also override everything in Hydra from the command 
line just like with your own configuration.

The Hydra configuration actually lives in the same config object as your configuration, but is removed prior to running
your function to reduce confusion.
You can view the configuration with `--cfg hydra|job|all`

The Hydra configuration itself is composed from multiple config files. here is a partial list:
```yaml
defaults:
  - hydra/job_logging : default     # Job's logging config
  - hydra/launcher: basic           # Launcher config
  - hydra/sweeper: basic            # Sweeper config
  - hydra/output: default           # Output directory
```
You can view the Hydra config structure [here](https://github.com/facebookresearch/hydra/tree/1.0_branch/hydra/conf).

This is a subset of the composed Hydra configuration node:

```yaml
hydra:
  run:
    # Output directory for normal runs
    dir: ./outputs/${now:%Y-%m-%d_%H-%M-%S}
  sweep:
    # Output directory for sweep runs
    dir: /checkpoint/${env:USER}/outputs/${now:%Y-%m-%d_%H-%M-%S}
    # Output sub directory for sweep runs.
    subdir: ${hydra.job.num}_${hydra.job.id}
```

## Runtime variables
The `hydra` package is deleted from your config when the function runs to reduce the amount of noise
in the config passed to the function.  
You can still access all config nodes in Hydra through the custom resolver `hydra`. 

For example:
```yaml
config_name: ${hydra:job.config_name}
```
Pay close attention to the syntax: The resolver name is `hydra`, and the `key` is passed after the colon.

The following variables are some of the variables populated at runtime.  
You can see the full Hydra config using `--cfg hydra`:

`hydra.job`:
- *hydra.job.name* : Job name, defaults to python file name without suffix. can be overridden.
- *hydra.job.override_dirname* : Pathname derived from the overrides for this job
- *hydra.job.num* : job serial number in sweep
- *hydra.job.id* : Job ID in the underlying jobs system (SLURM etc) 

`hydra.runtime`:
- *hydra.runtime.version*: Hydra's version
- *hydra.runtime.cwd*: Original working directory the app was executed from

### Hydra resolvers

Hydra supports [several OmegaConf resolvers](https://github.com/facebookresearch/hydra/blob/master/hydra/core/utils.py) by default.

#### `now`
Creates a string representing the current time using [strftime](https://docs.python.org/2/library/datetime.html#strftime-strptime-behavior).
For example, for formatting the time you can use something like`${now:%H-%M-%S}`.

#### `hydra`
Interpolates into the `hydra` config node.
For example, use `${hydra:job.name}` to get the Hydra job name.

#### `python_version`
Return a string representing the runtime python version by calling `sys.version_info`.
You can pass in a parameter to specify level of version returned. By default, the resolver returns the major and minor version.
```yaml
python_version: ${python_version:}                         # runtime python version, eg: 3.8
major_version: ${python_version:major}                     # runtime python major version, eg: 3
minor_version: ${python_version:minor}                     # runtime python version in the format major.minor, eg: 3.8
micro_version: ${python_version:micro}                     # runtime python version in the format major.minor.micro, eg: 3.8.2
```

You can learn more about OmegaConf <a class="external" href="https://omegaconf.cli.dev/docs/concepts/configs-and-values" target="_blank" rel="noopener noreferrer">here</a>.
