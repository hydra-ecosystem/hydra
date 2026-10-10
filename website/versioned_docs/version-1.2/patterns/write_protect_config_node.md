---
id: write_protect_config_node
title: Read-only config
---
import {ExampleGithubLink} from "@site/src/components/GithubLink"

<ExampleGithubLink text="Example application" to="examples/patterns/write_protect_config_node"/>

### Problem
Sometimes you want to prevent a config node from being changed accidentally.

### Solution
Structured Configs can enable it by passing [frozen=True](https://omegaconf.cli.dev/docs/guides/flags#read-only) in the dataclass definition.
Using Structured Configs, you can annotate a dataclass as frozen. This is recursive and applies to all child nodes.

This will prevent modifications via code, command line overrides and config composition.

<div className="row">
<div className="col col--6">

```python title="frozen.py" {1}
@dataclass(frozen=True)
class SerialPort:
    baud_rate: int = 19200
    data_bits: int = 8
    stop_bits: int = 1


cs = ConfigStore.instance()
cs.store(name="config", node=SerialPort)


@hydra.main(version_base=None, config_name="config")
def my_app(cfg: SerialPort) -> None:
    print(cfg)


if __name__ == "__main__":
    my_app()
```
</div><div className="col  col--6">

```shell script title="Output"
$ python frozen.py data_bits=10
Error merging override data_bits=10
Cannot change read-only config container
    full_key: data_bits
    object_type=SerialPort
```
</div></div>

<div class="alert alert--warning" role="alert">
<strong>NOTE</strong>:
A crafty user can find many ways around this. This is just making it harder to change things accidentally.
</div>

