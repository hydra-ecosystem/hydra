---
id: callbacks
title: Callbacks
sidebar_label: Callbacks
---

import GithubLink from "@site/src/components/GithubLink"

:::warning Experimental API

Callbacks remain experimental in Hydra 1.4. Their API and lifecycle may change
in a future release.

:::

The <GithubLink to="hydra/experimental/callback.py">Callback interface</GithubLink>
lets an application run custom code at specific points in Hydra's run and
multirun lifecycle.

## Define a callback

Subclass `Callback` and override only the hooks you need:

```python title="my_app.py"
from typing import Any

import hydra
from hydra.core.utils import JobReturn
from hydra.experimental.callback import Callback
from omegaconf import DictConfig


class UploadCallback(Callback):
    def __init__(self, bucket: str, file_path: str) -> None:
        self.bucket = bucket
        self.file_path = file_path

    def on_job_end(
        self, config: DictConfig, job_return: JobReturn, **kwargs: Any
    ) -> None:
        print(f"Uploading {self.file_path} to {self.bucket}")


@hydra.main(config_path="conf", config_name="config")
def my_app(cfg: DictConfig) -> None:
    print(cfg)


if __name__ == "__main__":
    my_app()
```

## Configure a callback

`hydra.callbacks` is a mapping. Each value is an instantiation config for one
callback:

```yaml title="conf/hydra/callbacks/upload.yaml"
upload:
  _target_: my_app.UploadCallback
  bucket: my_s3_bucket
  file_path: ./result.pt
```

Select the callback from the primary config's Defaults List:

```yaml title="conf/config.yaml"
defaults:
  - /hydra/callbacks: upload

foo: bar
```

The mapping order determines callback order. Start hooks run in composed order;
end hooks run in reverse order. For callbacks `first` and `second`, Hydra calls
`first.on_job_start()`, then `second.on_job_start()`, followed later by
`second.on_job_end()` and `first.on_job_end()`.

## Lifecycle hooks

| Hook | Where it runs | Additional keyword arguments |
| --- | --- | --- |
| `on_run_start` | Controller, before a single-run job starts | `config_name` |
| `on_run_end` | Controller, after a single-run job ends | `config_name`, `job_return` |
| `on_multirun_start` | Controller, before the sweeper and launcher are initialized | `config_name` |
| `on_multirun_end` | Controller, after multirun finishes | `config_name` |
| `on_job_start` | In each job, immediately before application code | `task_function` |
| `on_job_end` | In each job, after application code | `job_return` |

In a single run, the order is:

```text
on_run_start -> on_job_start -> application -> on_job_end -> on_run_end
```

In a multirun, `on_multirun_start` and `on_multirun_end` surround sweeper and
launcher execution. Each launched job independently calls `on_job_start` and
`on_job_end`.

Once Hydra begins dispatching a start hook, it dispatches the matching end hook
exactly once while Python can unwind normally. This includes application,
sweeper, launcher, `KeyboardInterrupt`, and `SystemExit` failure paths. It
cannot cover termination that prevents Python cleanup, such as `SIGKILL`,
`os._exit()`, machine loss, or a remote worker disappearing.

`on_job_end` receives a failed `JobReturn` when application code fails. If a
single run fails before a job can produce a complete result, `on_run_end`
receives a minimal failed `JobReturn` containing that exception.
`on_job_end` receives the live, mutable `JobReturn`. Changes are visible to
later `on_job_end` callbacks and, when the same result reaches the controller
in a single run, to `on_run_end`; they can affect the outcome Hydra returns or
raises.

## Errors raised by callbacks

When a callback raises an ordinary `Exception`, Hydra attempts to report it as
a warning and continues dispatching the remaining callbacks.

Control-flow exceptions derived directly from `BaseException`, such as
`KeyboardInterrupt` and `SystemExit`, are not converted to warnings and
continue to propagate.

## Callbacks and launchers

Run and multirun hooks execute in the controller process. Job hooks execute
where the job runs. With a remote or process-based launcher, the configured
callback instances are serialized or copied to workers. Mutable state changed
by job hooks is therefore not automatically reflected in the controller-side
instance used by `on_multirun_end`.

Do not rely on sharing mutable callback state between controller and job hooks.
Use external storage or another explicit communication mechanism when results
must be aggregated across jobs.

## Hydra-provided callbacks

`LogJobReturnCallback` is a deprecated no-op in Hydra 1.4 and will be removed in
Hydra 1.5. Remove it from `hydra.callbacks`; Hydra logs task exceptions to
per-job logs without this callback. Logging successful return values is
deliberately no longer built in. If you need it, log in your application or
implement an `on_job_end` callback.
