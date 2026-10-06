---
id: rerun
title: Re-run a job from its output directory
sidebar_label: Re-run
---

import {ExampleGithubLink} from "@site/src/components/GithubLink"

<ExampleGithubLink text="Example application" to="examples/experimental/rerun"/>

:::caution
This is an experimental feature. Run from a compatible project version,
preferably the same commit and dependencies as the original job.
:::

Run your application normally:

```commandline
$ python my_app.py foo=bar hydra.run.dir=outputs/training
```

Hydra saves configuration metadata and overrides in the job's `.hydra`
directory. No callback is required. To rerun, pass the **job output directory**:

```commandline
$ python my_app.py --experimental-rerun outputs/training
```

Hydra recomposes the configuration from the current project's config sources,
using the original config name and the stored overrides. Additional overrides
are appended and take precedence through normal composition:

```commandline
$ python my_app.py --experimental-rerun outputs/training foo=baz
```

Because rerun uses the saved config name, `--config-name` cannot be supplied
with `--experimental-rerun`.

Both config-group overrides and config-value overrides work normally. Structured
config schemas are recovered from the current project. Saved `config.yaml`
values are not loaded or merged; changes to the project's defaults therefore
take effect unless a stored or new override replaces them. Interpolations are
resolved normally and may produce different values on a later run.

By default, rerun reuses the original job output directory. This allows an
application to resume training from a checkpoint it finds there. Checkpoint
loading remains the application's responsibility. To use a different directory:

```commandline
$ python my_app.py --experimental-rerun outputs/training hydra.run.dir=outputs/new-run
```

Rerun uses normal job execution, including logging, callbacks, and
`hydra.job.chdir`. Logs are updated and the configuration metadata is rewritten
in the selected output directory, just as for an ordinary run.

Only one job can be rerun at a time. An individual job from a previous sweep can
be rerun, but `--multirun`, `hydra.mode=MULTIRUN`, and sweep overrides are not
supported. The job directory must contain `.hydra/hydra.yaml` and
`.hydra/overrides.yaml`; jobs that disabled or relocated this metadata directory
cannot be rerun using this option.

`PickleJobInfoCallback` has been removed in Hydra 1.4. Remove it from
`hydra.callbacks`. The `config.pickle` and `job_return.pickle` artifacts are no
longer produced or accepted by experimental rerun.
