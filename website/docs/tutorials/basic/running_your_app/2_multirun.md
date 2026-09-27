---
id: multi-run
title: Multi-run
sidebar_label: Multi-run
---

Sometimes you want to run the same application with multiple different configurations.  
E.g. running a performance test on each of the databases with each of the schemas.

You can multirun a Hydra application via either commandline or configuration:

### Configure `hydra.mode` (new in Hydra 1.2)
You can configure `hydra.mode` in any supported way. The legal values are `RUN` and `MULTIRUN`.
The following shows how to override from the command-line and sweep over all combinations of the dbs and schemas.
Setting `hydra.mode=MULTIRUN` in your input config would make your application multi-run by default.

```text title="$ python my_app.py hydra.mode=MULTIRUN db=mysql,postgresql schema=warehouse,support,school"
[2021-01-20 17:25:03,317][HYDRA] Launching 6 jobs locally
[2021-01-20 17:25:03,318][HYDRA]        #0 : db=mysql schema=warehouse
[2021-01-20 17:25:03,458][HYDRA]        #1 : db=mysql schema=support
[2021-01-20 17:25:03,602][HYDRA]        #2 : db=mysql schema=school
[2021-01-20 17:25:03,755][HYDRA]        #3 : db=postgresql schema=warehouse
[2021-01-20 17:25:03,895][HYDRA]        #4 : db=postgresql schema=support
[2021-01-20 17:25:04,040][HYDRA]        #5 : db=postgresql schema=school
```
The printed configurations have been omitted for brevity.

### `--multirun (-m)` from the command-line
You can achieve the above from command-line as well:
```commandline
python my_app.py --multirun db=mysql,postgresql schema=warehouse,support,school
```
or 
```commandline
python my_app.py -m db=mysql,postgresql schema=warehouse,support,school
```

You can access `hydra.mode` at runtime to determine whether the application is in RUN or MULTIRUN mode. Check [here](/configure_hydra/Intro.md)
on how to access Hydra config at run time.

If conflicts arise (e.g., `hydra.mode=RUN` and the application was run with `--multirun`), Hydra will determine the value of `hydra.mode`
at run time. The following table shows what runtime `hydra.mode` value you'd get with different input configs and commandline combinations.

[//]: # (Conversion matrix)

|                    	   | No multirun commandline flag      	 | --multirun ( -m)                    |
|--------------------	   |-------------------------------------|-------------------------------------|
|hydra.mode=RUN            | RunMode.RUN          	              | RunMode.MULTIRUN (with UserWarning) |
|hydra.mode=MULTIRUN       | RunMode.MULTIRUN          	         | RunMode.MULTIRUN                    |
|hydra.mode=None (default) | RunMode.RUN          	              | RunMode.MULTIRUN                    |


:::important
Hydra composes configs lazily at job launching time. If you change code or configs after launching a job/sweep, the final 
composed configs might be impacted.
:::

### Sweeping via `hydra.sweeper.params`

import {ExampleGithubLink} from "@site/src/components/GithubLink"

<ExampleGithubLink to="examples/tutorials/basic/running_your_hydra_app/5_basic_sweep"/>

You can also define sweeping in the input configs by overriding
`hydra.sweeper.params`. Using the above example, the same multirun could be achieved via the following config.

```yaml
hydra:
  sweeper:
    params:
      db: mysql,postgresql
      schema: warehouse,support,school
```

The syntax are consistent for both input configs and commandline overrides.
If a sweep is specified in both an input config and at the command line,
then the commandline sweep will take precedence over the sweep defined 
in the input config. If we run the same application with the above input config and a new commandline override:

```text title="$ python my_app.py -m db=mysql"
[2021-01-20 17:25:03,317][HYDRA] Launching 3 jobs locally
[2021-01-20 17:25:03,318][HYDRA]        #0 : db=mysql schema=warehouse
[2021-01-20 17:25:03,458][HYDRA]        #1 : db=mysql schema=support
[2021-01-20 17:25:03,602][HYDRA]        #2 : db=mysql schema=school
```
:::info
The above configuration methods only apply to Hydra's default `BasicSweeper` for now. For other sweepers, please check out the 
corresponding documentations.
:::

### Stop on the first failed job

By default, the basic sweeper runs the jobs in a batch before reporting a job failure.
To stop as soon as one job fails, set `hydra.sweeper.fail_fast=true`:

```commandline
python my_app.py -m db=mysql,postgresql schema=warehouse,support hydra.sweeper.fail_fast=true
```

Fail-fast is supported with Hydra's basic launcher, which runs jobs sequentially.
It is not supported with parallel or remote launchers.
The basic launcher receives batches as usual but stops executing jobs after the first failure.

### Additional sweep types
Hydra supports other kinds of sweeps, e.g.:
```python
x=range(1,10)                  # 1-9
schema=glob(*)                 # warehouse,support,school
schema=glob(*,exclude=w*)      # support,school
```
See the [Extended Override syntax](/advanced/override_grammar/extended.md) for details.

### Sweeper
The default sweeping logic is built into Hydra. Additional sweepers are available as plugins.
For example, the [Ax Sweeper](/plugins/ax_sweeper.md) can automatically find the best parameter combination!

### Launcher
By default, Hydra runs your multi-run jobs locally and serially. 
Other launchers are available as plugins for launching in parallel and on different clusters. For example, the [JobLib Launcher](/plugins/joblib_launcher.md)
can execute the different parameter combinations in parallel on your local machine using multi-processing.
