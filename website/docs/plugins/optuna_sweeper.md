---
id: optuna_sweeper
title: Optuna Sweeper plugin
sidebar_label: Optuna Sweeper plugin
---

import GithubLink,{ExampleGithubLink} from "@site/src/components/GithubLink"

[![PyPI](https://img.shields.io/pypi/v/hydra-optuna-sweeper)](https://pypi.org/project/hydra-optuna-sweeper/)
![PyPI - License](https://img.shields.io/pypi/l/hydra-optuna-sweeper)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/hydra-optuna-sweeper)
[![PyPI - Downloads](https://api.pepy.tech/badge/hydra-optuna-sweeper/month)](https://pepy.tech/project/hydra-optuna-sweeper)<ExampleGithubLink text="Example application" to="plugins/hydra_optuna_sweeper/example"/><ExampleGithubLink text="Plugin source" to="plugins/hydra_optuna_sweeper"/>


This plugin enables Hydra applications to utilize [Optuna](https://optuna.org) for the optimization of the parameters of experiments.

## Installation

This plugin requires Hydra Core 1.4 (`hydra-core>=1.4.0.dev1,<1.5.0.dev0`).
Please install it with the following command:

```commandline
pip install --upgrade --pre "hydra-core>=1.4.0.dev1,<1.5.0.dev0"
```

You can install the plugin via pip:

```commandline
pip install --upgrade --pre "hydra-optuna-sweeper>=1.4.0.dev1,<1.5.0.dev0"
```
There are several standard approaches for configuring plugins. Check [this page](../patterns/configuring_plugins.md) for more information.

## Usage

Please set `hydra/sweeper` to `optuna` in your config file.

```yaml
defaults:
  - override hydra/sweeper: optuna
```

Alternatively, add `hydra/sweeper=optuna` option to your command line.

The default configuration is <GithubLink to="plugins/hydra_optuna_sweeper/hydra_plugins/hydra_optuna_sweeper/config.py">here</GithubLink>.

## Example 1: Single-Objective Optimization

We include an example in <GithubLink to="plugins/hydra_optuna_sweeper/example">this directory</GithubLink>. `example/sphere.py` implements a simple benchmark function to be minimized.




You can discover the Optuna sweeper parameters with:

```yaml title="python example/sphere.py hydra/sweeper=optuna --cfg hydra -p hydra.sweeper"
# @package hydra.sweeper
sampler:
  _target_: optuna.samplers.TPESampler
  seed: 123
  n_startup_trials: 10
  n_ei_candidates: 24
  multivariate: false
_target_: hydra_plugins.hydra_optuna_sweeper.optuna_sweeper.OptunaSweeper
direction: minimize
storage: null
study_name: sphere
n_trials: 20
n_jobs: 1
max_failure_rate: 0.0
params:
  x: range(-5.5,5.5,step=0.5)
  y: choice(-5,0,5)
```

The function decorated with `@hydra.main()` returns a float which we want to minimize, the minimum is 0 and reached for:
```yaml
x: 0
y: 0
```

To run optimization, clone the code and run the following command in the `plugins/hydra_optuna_sweeper` directory:

```commandline
python example/sphere.py --multirun
```

You can also override the search space parametrization:

```commandline
python example/sphere.py --multirun 'x=interval(-5.0, 5.0)' 'y=interval(0, 10)'
```

You might find the `optimization_results.yaml` file (i.e. best params and best value) under `multirun` logs folder:

```yaml
name: optuna
best_params:
  x: 0.0
  'y': 0
best_value: 0.0
```


## Sampler configuration
This plugin supports Optuna's [samplers](https://optuna.readthedocs.io/en/stable/reference/samplers.html).
You can change the sampler by overriding `hydra/sweeper/sampler` or change sampler settings within `hydra.sweeper.sampler`.

## Search space configuration

This plugin supports Optuna's [distributions](https://optuna.readthedocs.io/en/stable/reference/distributions.html) to configure search spaces. They can be defined either through commandline override or config file.

### Configuring through commandline override

Hydra provides a override parser that support rich syntax. Please refer to [OverrideGrammer/Basic](../advanced/override_grammar/basic.md) and [OverrideGrammer/Extended](../advanced/override_grammar/extended.md) for details.

#### Interval override

By default, `interval` is converted to [`FloatDistribution`](https://optuna.readthedocs.io/en/stable/reference/generated/optuna.distributions.FloatDistribution.html). You can use [`IntDistribution`](https://optuna.readthedocs.io/en/stable/reference/generated/optuna.distributions.IntDistribution.html) by casting the interval to `int`.

<details>
  <summary>Example for interval override</summary>

  ```commandline
  python example/sphere.py --multirun 'x=int(interval(-5.0, 5.0))' 'y=tag(log, interval(1, 10))'
  ```

  The output is as follows:

  ```commandline
  [HYDRA] Study name: sphere
  [HYDRA] Storage: None
  [HYDRA] Sampler: TPESampler
  [HYDRA] Directions: ['minimize']
  [HYDRA] Launching 1 jobs locally
  [HYDRA] 	#0 : x=-3 y=1.6859762540733367
  [HYDRA] Launching 1 jobs locally
  [HYDRA] 	#1 : x=1 y=5.237816870668193
  ...
  [HYDRA] Best parameters: {'x': 0, 'y': 1.0929184723430116}
  [HYDRA] Best value: 1.1944707871885822
  ```

</details>

#### Range override

`range` is converted to [`IntDistribution`](https://optuna.readthedocs.io/en/stable/reference/generated/optuna.distributions.IntDistribution.html). If you apply `shuffle` to `range`, [`CategoricalDistribution`](https://optuna.readthedocs.io/en/stable/reference/generated/optuna.distributions.CategoricalDistribution.html) is used instead.
If any of `range`'s start, stop or step is of type float, it will be converted to [`FloatDistribution`](https://optuna.readthedocs.io/en/stable/reference/generated/optuna.distributions.FloatDistribution.html)

<details>
  <summary>Example for range override</summary>

  ```commandline
  python example/sphere.py --multirun 'x=range(-5.0, 5.0)' 'y=shuffle(range(-5, 5))'
  ```

  The output is as follows:

  ```commandline
  [HYDRA] Study name: sphere
  [HYDRA] Storage: None
  [HYDRA] Sampler: TPESampler
  [HYDRA] Directions: ['minimize']
  [HYDRA] Launching 1 jobs locally
  [HYDRA] 	#0 : x=-3 y=-4
  [HYDRA] Launching 1 jobs locally
  [HYDRA] 	#1 : x=1 y=-1
  ...
  [HYDRA] Best parameters: {'x': 0, 'y': -1}
  [HYDRA] Best value: 1.0
  ```

</details>

#### Choice override

`choice` is converted to [`CategoricalDistribution`](https://optuna.readthedocs.io/en/stable/reference/generated/optuna.distributions.CategoricalDistribution.html).

<details>
  <summary>Example for choice override</summary>

  ```commandline
  python example/sphere.py --multirun 'x=choice(-5.0, 0.0, 5.0)' 'y=choice(0, 1, 2, 3, 4, 5)'
  ```

  The output is as follows:

  ```commandline
  [HYDRA] Study name: sphere
  [HYDRA] Storage: None
  [HYDRA] Sampler: TPESampler
  [HYDRA] Directions: ['minimize']
  [HYDRA] Launching 1 jobs locally
  [HYDRA] 	#0 : x=5.0 y=5
  [HYDRA] Launching 1 jobs locally
  [HYDRA] 	#1 : x=5.0 y=2
  ...
  [HYDRA] Best parameters: {'x': 0.0, 'y': 0}
  [HYDRA] Best value: 0.0
  ```

</details>

### Configuring through config file

The syntax in config file is consistent with the above commandline override. For example, a commandline override
`x=range(1,4)` can be expressed in config file as `x: range(1,4)` under the `hydra.sweeper.params` node.

## Example 2:  Multi-Objective Optimization

In the same directory, `example/multi-objective.py` implements a simple benchmark function, which has two objective values. We want to minimize two objectives simultaneously.

You can discover the Optuna sweeper parameters with:

```commandline
python example/multi-objective.py hydra/sweeper=optuna --cfg hydra -p hydra.sweeper
```

<details>
  <summary>Configuration of the multi-objective optimization example</summary>

  ```yaml
  # @package hydra.sweeper
  sampler:
    _target_: optuna.samplers.NSGAIISampler
    seed: 123
    population_size: 50
    mutation_prob: null
    crossover_prob: 0.9
    swapping_prob: 0.5
    constraints_func: null
  _target_: hydra_plugins.hydra_optuna_sweeper.optuna_sweeper.OptunaSweeper
  direction:
  - minimize
  - minimize
  storage: null
  study_name: multi-objective
  n_trials: 20
  n_jobs: 1
  params:
    x: range(0, 5, step=0.5)
    y: range(0, 3, step=0.5)
  ```
</details>


To run the optimization, use the following command in the `plugins/hydra_optuna_sweeper` directory:

```commandline
python example/multi-objective.py --multirun
```

For problems with trade-offs between two different objectives, there may be no single solution that simultaneously minimizes both objectives. Instead, we obtained a set of solutions, namely [Pareto optimal solutions](https://en.wikipedia.org/wiki/Pareto_efficiency), that show the best trade-offs possible between the objectives. In the following figure, the blue dots show the Pareto optimal solutions in the optimization results.

![Pareto-optimal solutions](/plugins/optuna_sweeper/multi_objective_result.png)

## EXPERIMENTAL:  Custom-Search-Space Optimization

Hydra's Optuna Sweeper allows users to provide a hook for custom search space configuration.
This means you can work directly with the `optuna.trial.Trial` object to suggest parameters.
To use this feature, define a python function with signature `Callable[[DictConfig, optuna.trial.Trial], None]`
and set the `hydra.sweeper.custom_search_space` key in your config to target that function.

The callback path is selected by configuration. When using an execution
whitelist, authorize that path from trusted Python code:

```python
@hydra.main(
    config_path="custom-search-space",
    config_name="config",
    execution_whitelist="custom-search-space-objective.configure",
)
def multi_dimensional_sphere(cfg: DictConfig) -> float:
    ...
```

You can find a full example in the same directory as before, where `example/custom-search-space-objective.py` implements a benchmark function to be minimized.
The example shows the use of Optuna's [pythonic search spaces](https://optuna.readthedocs.io/en/stable/tutorial/10_key_features/002_configurations.html) in combination with Hydra.
Part of the search space configuration is defined in config files, and part of it is written in Python.

<details>
  <summary>Example: Custom search space configuration</summary>

  ```yaml
  defaults:
    - override hydra/sweeper: optuna

  hydra:
    sweeper:
      sampler:
        seed: 123
      direction: minimize
      study_name: custom-search-space
      storage: null
      n_trials: 20
      n_jobs: 1

      params:
        x: range(-5.5, 5.5, 0.5)
        y: choice(-5, 0, 5)
      # `custom_search_space` should be a dotpath pointing to a
      # callable that provides search-space configuration logic:
      custom_search_space: custom-search-space-objective.configure

  x: 1
  y: 1
  z: 100
  max_z_difference_from_x: 0.5
  ```
  ```python
  # example/custom-search-space-objective.py

  ...

  def configure(cfg: DictConfig, trial: Trial) -> None:
      x_value = trial.params["x"]
      trial.suggest_float(
          "z",
          x_value - cfg.max_z_difference_from_x,
          x_value + cfg.max_z_difference_from_x,
      )
      trial.suggest_float("+w", 0.0, 1.0)  # note +w here, not w as w is a new parameter

  ...
  ```

</details>

The method that `custom_search_space` points to must accepts both a DictConfig with already set options and a trial object which needs further configuration. In this example we limit `z` the difference between `x` and `z` to be no more than 0.5.
Note that this `custom_search_space` API should be considered experimental and is subject to change.

### Order of trial configuration
Configuring a trial object is done in the following sequence:
  - search space parameters are set from the `hydra.sweeper.params` key in the config
  - Command line overrides are set
  - `custom_search_space` parameters are set

It is not allowed to set search space parameters in the `custom_search_space` method for parameters which have a fixed value from command line overrides. [Trial.user_attrs](https://optuna.readthedocs.io/en/stable/reference/generated/optuna.trial.Trial.html#optuna.trial.Trial.user_attrs) can be inspected to find any of such fixed parameters.
