---
id: submitit_launcher
title: Submitit Launcher plugin
sidebar_label: Submitit Launcher plugin
---

import GithubLink,{ExampleGithubLink} from "@site/src/components/GithubLink"

[![PyPI](https://img.shields.io/pypi/v/hydra-submitit-launcher)](https://pypi.org/project/hydra-submitit-launcher/)
![PyPI - License](https://img.shields.io/pypi/l/hydra-submitit-launcher)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/hydra-submitit-launcher)
[![PyPI - Downloads](https://api.pepy.tech/badge/hydra-submitit-launcher/month)](https://pepy.tech/project/hydra-submitit-launcher)<ExampleGithubLink text="Example application" to="plugins/hydra_submitit_launcher/examples"/><ExampleGithubLink text="Plugin source" to="plugins/hydra_submitit_launcher"/>

The Submitit Launcher plugin provides a [SLURM](https://slurm.schedmd.com/documentation.html) Launcher based on [Submitit](https://github.com/facebookincubator/submitit).

### Installation
```commandline
pip install hydra-submitit-launcher --upgrade
```


### Usage
Once installed, add `hydra/launcher=submitit_slurm` to your command line. Alternatively, override `hydra/launcher` in your config:

```yaml
defaults:
  - override hydra/launcher: submitit_slurm
```
There are several standard approaches for configuring plugins. Check [this page](../patterns/configuring_plugins.md) for more information.
Note that this plugin expects a valid environment in the target host. Usually this means a shared file system between
the launching host and the target host.

The Submitit Plugin implements 2 different launchers: `submitit_slurm` to run on a SLURM cluster, and `submitit_local` for basic local tests.

<details>
  <summary>Discover the SLURM Launcher parameters <b>(Expand)</b></summary>

  ```yaml title="$ python your_app.py hydra/launcher=submitit_slurm --cfg hydra -p hydra.launcher"
  # @package hydra.launcher
  submitit_folder: ${hydra.sweep.dir}/.submitit/%j
  timeout_min: 60
  cpus_per_task: null
  gpus_per_node: null
  tasks_per_node: 1
  mem_gb: null
  nodes: 1
  name: ${hydra.job.name}
  _target_: hydra_plugins.hydra_submitit_launcher.submitit_launcher.SlurmLauncher
  partition: null
  qos: null
  comment: null
  constraint: null
  exclude: null
  gres: null
  cpus_per_gpu: null
  gpus_per_task: null
  mem_per_gpu: null
  mem_per_cpu: null
  account: null
  signal_delay_s: 120
  max_num_timeout: 0
  python: null
  additional_parameters: {}
  array_parallelism: 256
  setup: null
  srun_args: null
  use_srun: true
  ```
</details>
<details>
  <summary>Discover the Local Launcher parameters <b>(Expand)</b></summary>

  ```yaml title="$ python example/my_app.py hydra/launcher=submitit_local --cfg hydra -p hydra.launcher"
  # @package hydra.launcher
  _target_: hydra_plugins.hydra_submitit_launcher.submitit_launcher.LocalLauncher
  submitit_folder: ${hydra.sweep.dir}/.submitit/%j
  timeout_min: 60
  cpus_per_task: 1
  gpus_per_node: 0
  tasks_per_node: 1
  mem_gb: 4
  nodes: 1
  name: ${hydra.job.name}
  ```
</details>

<br/>
You can set all these parameters in your configuration file and/or override them in the command-line:

```text
python foo.py --multirun hydra/launcher=submitit_slurm hydra.launcher.timeout_min=3
```
Set `hydra.launcher.tasks_per_node=null` to omit `--ntasks-per-node` from the
generated Slurm submission.

Set `hydra.launcher.use_srun=false` to run Python directly in the batch script
instead of through `srun`. The default is `true`. When disabled, Python runs
once on the batch node, and `srun_args` is ignored; Slurm does not automatically
launch the other requested tasks.

Set `hydra.launcher.python` to use a Python executable other than the one
running Hydra:

```text
python foo.py --multirun hydra/launcher=submitit_slurm hydra.launcher.python=/opt/venv/bin/python
```

For more details, including descriptions for each parameter, check out the <GithubLink to="plugins/hydra_submitit_launcher/hydra_plugins/hydra_submitit_launcher/config.py">config file</GithubLink>.
You can also check the [Submitit documentation](https://github.com/facebookincubator/submitit).


**Caution**: use of `--multirun` is required for the launcher to be picked up.

### Example

An <GithubLink to="plugins/hydra_submitit_launcher/example">example application</GithubLink> using this launcher is provided in the plugin repository.

Starting the app with `python my_app.py task=1,2,3 --multirun` (see [Multi-run](../tutorials/basic/running_your_app/2_multirun.md) for details) will launch 3 executions (you can override the launcher to run locally for testing by adding `hydra/launcher=submitit_local`):

```text
$ python my_app.py task=1,2,3 --multirun
[HYDRA] Sweep output dir : multirun/2020-05-28/15-05-22
[HYDRA]        #0 : task=1
[HYDRA]        #1 : task=2
[HYDRA]        #2 : task=3
```
You will be able to see the output of the app in the output dir:
```commandline
$ tree
.
├── 0
│   └── my_app.log
├── 1
│   └── my_app.log
├── 2
│   └── my_app.log
└── multirun.yaml

$ cat 0/my_app.log
[2020-05-28 15:05:23,511][__main__][INFO] - Process ID 15887 executing task 1 ...
[2020-05-28 15:05:24,514][submitit][INFO] - Job completed successfully
```
