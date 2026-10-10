---
id: simple_cli
title: Simple command line application
sidebar_label: Simple command line application
---

This is a simple Hydra application that prints your configuration.
The `my_app` function is a place holder 
for your code. We will slowly evolve this example to show-case more Hydra features.

The examples in this tutorial are available [here](https://github.com/facebookresearch/hydra/tree/0.11_branch/examples/tutorial).

Python file: `my_app.py`
```python
import hydra

@hydra.main()
def my_app(cfg):
    print(OmegaConf.to_yaml(cfg))

if __name__ == "__main__":
    my_app()
```
The `cfg` is an <a class="external" href="https://omegaconf.cli.dev/docs/concepts/configs-and-values" target="_blank" rel="noopener noreferrer">OmegaConf</a>
object that holds the configuration for your function.
You don't need a deep understanding of OmegaConf for this tutorial.

We can pass arbitrary command line arguments from which Hydra creates a hierarchical configuration object:
```yaml
$ python my_app.py db.driver=mysql db.user=omry db.pass=secret
db:
  driver: mysql
  pass: secret
  user: omry
```

