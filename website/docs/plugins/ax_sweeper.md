---
id: ax_sweeper
title: Ax Sweeper plugin
sidebar_label: Ax Sweeper plugin
---

import {ExampleGithubLink} from "@site/src/components/GithubLink"

[![PyPI](https://img.shields.io/pypi/v/hydra-ax-sweeper)](https://img.shields.io/pypi/v/hydra-ax-sweeper)
![PyPI - License](https://img.shields.io/pypi/l/hydra-ax-sweeper)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/hydra-ax-sweeper)
[![PyPI - Downloads](https://api.pepy.tech/badge/hydra-ax-sweeper/month)](https://pepy.tech/project/hydra-ax-sweeper)<ExampleGithubLink text="Example application" to="plugins/hydra_ax_sweeper/example"/><ExampleGithubLink text="Plugin source" to="plugins/hydra_ax_sweeper"/>


This plugin provides a mechanism for Hydra applications to use the [Adaptive Experimentation Platform, aka Ax](https://ax.dev/). Ax can optimize any experiment - machine learning experiments, A/B tests, and simulations.

:::warning Retirement after Hydra 1.4

Hydra 1.4 will include the final first-party release of the Ax Sweeper, based on
the existing implementation. Further modernization is no longer planned. The
plugin code will be removed in the Hydra 1.5 line, and no first-party Ax Sweeper
releases will be published for Hydra 1.5 or later. Existing PyPI releases will
remain available.

Community members interested in maintaining the plugin in a separate repository
are invited to comment on the [retirement issue](https://github.com/hydra-ecosystem/hydra/issues/3506).
Hydra's documentation can link to that repository. Transferring control of the
`hydra-ax-sweeper` PyPI package may be considered once new maintainers establish
a reliable track record and build trust.

:::

### Installation
```commandline
pip install hydra-ax-sweeper --upgrade
```

### Usage
Once installed, add `hydra/sweeper=ax` to your command line. Alternatively, override `hydra/sweeper` in your config:

```yaml
defaults:
  - override hydra/sweeper: ax
```

We include an example of how to use this plugin. The file <GithubLink to="plugins/hydra_ax_sweeper/example/banana.py">example/banana.py</GithubLink>
implements the [Rosenbrock function (aka Banana function)](https://en.wikipedia.org/wiki/Rosenbrock_function).
The return value of the function should be the value that we want to optimize.


To compute the best parameters for the Banana function, clone the code and run the following command in the `plugins/hydra_ax_sweeper` directory:

```
python example/banana.py -m 'banana.x=int(interval(-5, 5))' 'banana.y=interval(-5, 10.1)'
```

The output of a run looks like:

```
[HYDRA] AxSweeper is optimizing the following parameters:
banana.x: range=[-5, 5]
banana.y: range=[-5.0, 10.1]
ax.modelbridge.dispatch_utils: Using Bayesian Optimization generation strategy: GenerationStrategy(name='Sobol+GPEI', steps=[Sobol for 5 trials, GPEI for subsequent trials]). Iterations after 5 will take longer to generate due to model-fitting.
[HYDRA] AxSweeper is launching 5 jobs
[HYDRA] Launching 5 jobs locally
[HYDRA]        #0 : banana.x=2 banana.y=-0.988
[__main__][INFO] - Banana_Function(x=2, y=-0.988)=2488.883
[HYDRA]        #1 : banana.x=-1 banana.y=7.701
[__main__][INFO] - Banana_Function(x=-1, y=7.701)=4493.987
[HYDRA]        #2 : banana.x=-1 banana.y=-3.901
[__main__][INFO] - Banana_Function(x=-1, y=-3.901)=2406.259
[HYDRA]        #3 : banana.x=-1 banana.y=0.209
[__main__][INFO] - Banana_Function(x=-1, y=0.209)=66.639
[HYDRA]        #4 : banana.x=4 banana.y=-4.557
[__main__][INFO] - Banana_Function(x=4, y=-4.557)=42270.006
[HYDRA] New best value: 66.639, best parameters: {'banana.x': -1, 'banana.y': 0.209}
```

In this example, we set the range of `x` parameter as an integer in the interval `[-5, 5]` and the range of `y` parameter as a float in the interval `[-5, 10.1]`. Note that in the case of `x`, we used `int(interval(...))` and hence only integers are sampled. In the case of `y`, we used `interval(...)` which refers to a floating-point interval. Other supported formats are fixed parameters (e.g.` banana.x=5.0`), choice parameters (eg `banana.x=choice(1,2,3)`) and range (eg `banana.x=range(1, 10)`). Note that `interval`, `choice` etc. are functions provided by Hydra, and you can read more about them [here](/advanced/override_grammar/extended.md). An important thing to remember is, use [`interval`](/advanced/override_grammar/extended.md#interval-sweep) when we want Ax to sample values from an interval. [`RangeParameter`](https://ax.dev/api/ax.html#ax.RangeParameter) in Ax is equivalent to `interval` in Hydra. Remember to use `int(interval(...))` if you want to sample only integer points from the interval. [`range`](/advanced/override_grammar/extended.md#range-sweep) can be used as an alternate way of specifying choice parameters. For example `python example/banana.py -m banana.x=choice(1, 2, 3, 4)` is equivalent to `python example/banana.py -m banana.x=range(1, 5)`.

The values of the `x` and `y` parameters can also be set using the config file `plugins/hydra_ax_sweeper/example/conf/config.yaml`. For instance, the configuration corresponding to the commandline arguments is as follows:

```
banana.x:
 type: range
 bounds: [-5, 5]

banana.y:
 type: range
 bounds: [-5, 10.1]
```

To sample in log space, you can tag the commandline override with `log`. E.g. `python example/banana.py -m banana.x=tag(log, interval(1, 1000))`. You can set `log_scale: true` in the input config to achieve the same.
```
banana.z:
 type: range
 bounds: [1, 100]
 log_scale: true
```

In general, the plugin supports setting all the Ax supported [Parameters](https://ax.dev/api/core.html?highlight=range#module-ax.core.parameter) in the config. According to the [Ax documentation](https://ax.dev/api/service.html#ax.service.ax_client.AxClient.create_experiment), the required elements in the config are:

* `name` - Name of the parameter. It is of type string.
* `type` - Type of the parameter. It can take the following values: `range`, `fixed`, or `choice`.
* `bounds` - Required only for the `range` parameters. It should be a list of two values, with the lower bound first.
* `values` - Required only for the `choice` parameters. It should be a list of values.
* `value` - Required only for the `fixed` parameters. It should be a single value.

Note that if you want to sample integers in the range `-5` to `5`, you need to specify the range as `int(interval(-5, 5))` (in the command line) or `[-5, 5]` (in config). If you want to sample floats in range `-5` to `5`, you need to specify the range as `interval(-5, 5)` (in the command line) or `[-5.0, 5.0]` (in config).

The Ax Sweeper assumes the optimized function is a noisy function with unknown measurement uncertainty.
This can be changed by overriding the `is_noisy` parameter to False, which specifies that each measurement is exact, i.e., each measurement has a measurement uncertainty of zero.

If measurement uncertainty is known or can be estimated (e.g., via a heuristic or via the [standard error of the mean](https://en.wikipedia.org/wiki/Standard_error) of repeated measurements), the measurement function can return the tuple `(measurement_value, measurement_uncertainty)` instead of a scalar value.

The parameters for the optimization process can also be set in the config file. Specifying the Ax config is optional. You can discover the Ax Sweeper parameters with:

```yaml title="$ python your_app.py hydra/sweeper=ax --cfg hydra -p hydra.sweeper"
# @package hydra.sweeper
_target_: hydra_plugins.hydra_ax_sweeper.ax_sweeper.AxSweeper
max_batch_size: null
ax_config:
  max_trials: 10
  early_stop:
    minimize: true
    max_epochs_without_improvement: 10
    epsilon: 1.0e-05
  experiment:
    name: null
    objective_name: objective
    minimize: true
    parameter_constraints: null
    outcome_constraints: null
    status_quo: null
  client:
    verbose_logging: false
    random_seed: null
  is_noisy: true
  params: {}
```
There are several standard approaches for configuring plugins. Check [this page](../patterns/configuring_plugins.md) for more information.
