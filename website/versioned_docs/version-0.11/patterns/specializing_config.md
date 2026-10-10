---
id: specializing_config
title: Specializing configuration
sidebar_label: Specializing configuration
---
In some cases the desired configuration should depend on other configuration choices.
For example, You may want to use only 5 layers in your Alexnet model if the dataset of choice is cifar10, and the default 7 otherwise.

We can start with a config that looks like this:
### initial config.yaml
```yaml
defaults:
  - dataset: imagenet
  - model: alexnet
```

We want to specialize the config based on the choice of the selected dataset and model:
Furthermore, we only want to do it for cifar10 and alexnet and not for 3 other combinations.

OmegaConf supports value interpolation, we can construct a value that would - at runtime - be a function of other values.
The idea is that we can add another element to the defaults list that would load a file name that depends on those two values:
### modified config.yaml
```yaml
defaults:
  - dataset: imagenet
  - model: alexnet
  - dataset_model: ${defaults.0.dataset}_${defaults.1.model}
    optional: true
```

Let's break this down:
#### dataset_model
The key `dataset_model` is an arbitrary directory, it can be anything unique that makes sense, including nested directory like `dataset/model`.

#### $\{defaults.0.dataset}_$\{defaults.1.model}
the value `${defaults.0.dataset}_${defaults.1.model}` is using OmegaConf's [variable interpolation](https://omegaconf.cli.dev/docs/concepts/interpolation).
At runtime, that value would resolve to *imagenet_alexnet*, or *cifar_resnet* - depending on the values of defaults.dataset and defaults.model.
This a bit clunky because defaults contains a list (I hope to improve this in the future)

#### optional: true
By default, Hydra would fail with an error if a config specified in the defaults does not exist.
in this case we only want to specialize cifar10 + alexnet, not all 4 combinations.
indication optional: true here tells Hydra to just continue if it can't find this file.

When specializing config, you usually want to only specify what's different, and not the whole thing.
We want the model for alexnet, when trained on cifar - to have 5 layers.

### dataset_model/cifar10_alexnet.yaml
```yaml
model:
  num_layers: 5
```

Let's check. Running with the default uses imagenet, so we don't get the specialized version of:

```yaml
$ python example.py
dataset:
  name: imagenet
  path: /datasets/imagenet
model:
  num_layers: 7
  type: alexnet
```

Running with cifar10 dataset, we do get 5 for num_layers:
```yaml
$ python example.py dataset=cifar10
dataset:
  name: cifar10
  path: /datasets/cifar10
model:
  num_layers: 5
  type: alexnet
```
