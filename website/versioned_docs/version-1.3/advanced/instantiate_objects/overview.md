---
id: overview
title: Instantiating objects with Hydra
sidebar_label: Overview
---

import {ExampleGithubLink} from "@site/src/components/GithubLink"

<ExampleGithubLink text="Example applications" to="examples/instantiate"/>

One of the best ways to drive different behavior in an application is to instantiate different implementations of an interface.
The code using the instantiated object only knows the interface which remains constant, but the behavior
is determined by the actual object instance.

Hydra provides `hydra.utils.instantiate()` (and its alias `hydra.utils.call()`) for instantiating objects and calling functions. Prefer `instantiate` for creating objects and `call` for invoking functions.

Call/instantiate supports:
- Constructing an object by calling the `__init__` method
- Calling functions, static functions, class methods and other callable global objects

:::warning
`hydra.utils.instantiate()` and `hydra.utils.call()` can execute arbitrary code
from a config-controlled `_target_` and its arguments. Use them only with trusted
configs.

Hydra 1.3.4 blocks some dangerous targets by default, but this blocklist is
defense-in-depth and is not a complete security boundary. See
[GHSA-2cp2-2r3c-7p7r](https://github.com/facebookresearch/hydra/security/advisories/GHSA-2cp2-2r3c-7p7r)
for details.
:::

<details>
  <summary>Instantiate API (Expand for details)</summary>

  ```python
  def instantiate(config: Any, *args: Any, **kwargs: Any) -> Any:
      """
      :param config: An config object describing what to call and what params to use.
                     In addition to the parameters, the config must contain:
                     _target_ : target class or callable name (str)
                     And may contain:
                     _args_: List-like of positional arguments to pass to the target
                     _recursive_: Construct nested objects as well (bool).
                                  True by default.
                                  may be overridden via a _recursive_ key in
                                  the kwargs
                     _convert_: Conversion strategy
                          none    : Passed objects are DictConfig and ListConfig, default
                          partial : Passed objects are converted to dict and list, with
                                    the exception of Structured Configs (and their fields).
                          object  : Passed objects are converted to dict and list.
                                    Structured Configs are converted to instances of the
                                    backing dataclass / attr class.
                          all     : Passed objects are dicts, lists and primitives without
                                    a trace of OmegaConf containers. Structured configs
                                    are converted to dicts / lists too.
                     _partial_: If True, return functools.partial wrapped method or object
                                False by default. Configure per target.
      :param args: Optional positional parameters pass-through
      :param kwargs: Optional named parameters to override
                     parameters in the config object. Parameters not present
                     in the config objects are being passed as is to the target.
                     IMPORTANT: dataclasses instances in kwargs are interpreted as config
                                and cannot be used as passthrough
      :return: if _target_ is a class name: the instantiated object
               if _target_ is a callable: the return value of the call
      """

  # Alias for instantiate
  call = instantiate
  ```

</details><br/>

The config passed to these functions must have a key called `_target_`, with the value of a fully qualified class name, class method, static method or callable.
For convenience, `None` config results in a `None` object.

**Named arguments** : Config fields (except reserved fields like `_target_`) are passed as named arguments to the target.
Named arguments in the config can be overridden by passing named argument with the same name in the `instantiate()` call-site.

**Positional arguments** : The config may contain a `_args_` field representing positional arguments to pass to the target.
The positional arguments can be overridden together by passing positional arguments in the `instantiate()` call-site.



### Simple usage
Your application might have an Optimizer class:
```python title="Example class"
class Optimizer:
    algo: str
    lr: float

    def __init__(self, algo: str, lr: float) -> None:
        self.algo = algo
        self.lr = lr
```

<div className="row">

<div className="col col--6">

```yaml title="Config"
optimizer:
  _target_: my_app.Optimizer
  algo: SGD
  lr: 0.01




```


</div>

<div className="col col--6">

```python title="Instantiation"
opt = instantiate(cfg.optimizer)
print(opt)
# Optimizer(algo=SGD,lr=0.01)

# override parameters on the call-site
opt = instantiate(cfg.optimizer, lr=0.2)
print(opt)
# Optimizer(algo=SGD,lr=0.2)
```

</div>
</div>


### Recursive instantiation
Let's add a Dataset and a Trainer class. The trainer holds a Dataset and an Optimizer instances.
```python title="Additional classes"
class Dataset:
    name: str
    path: str

    def __init__(self, name: str, path: str) -> None:
        self.name = name
        self.path = path


class Trainer:
    def __init__(self, optimizer: Optimizer, dataset: Dataset) -> None:
        self.optimizer = optimizer
        self.dataset = dataset
```

With the following config, you can instantiate the whole thing with a single call:
```yaml title="Example config"
trainer:
  _target_: my_app.Trainer
  optimizer:
    _target_: my_app.Optimizer
    algo: SGD
    lr: 0.01
  dataset:
    _target_: my_app.Dataset
    name: Imagenet
    path: /datasets/imagenet
```

Hydra will instantiate nested objects recursively by default.
```python
trainer = instantiate(cfg.trainer)
print(trainer)
# Trainer(
#  optimizer=Optimizer(algo=SGD,lr=0.01),
#  dataset=Dataset(name=Imagenet, path=/datasets/imagenet)
# )
```
You can override parameters for nested objects:
```python
trainer = instantiate(
    cfg.trainer,
    optimizer={"lr": 0.3},
    dataset={"name": "cifar10", "path": "/datasets/cifar10"},
)
print(trainer)
# Trainer(
#   optimizer=Optimizer(algo=SGD,lr=0.3),
#   dataset=Dataset(name=cifar10, path=/datasets/cifar10)
# )
```

Similarly, positional arguments of nested objects can be overridden:
```python
obj = instantiate(
    cfg.object,
    # pass 1 and 2 as positional arguments to the target object
    1, 2,
    # pass 3 and 4 as positional arguments to a nested child object
    child={"_args_": [3, 4]},
)
```

### Disable recursive instantiation
You can disable recursive instantiation by setting `_recursive_` to `False` in the config node or in the call-site
In that case the Trainer object will receive an OmegaConf DictConfig for nested dataset and optimizer instead of the instantiated objects.
```python
optimizer = instantiate(cfg.trainer, _recursive_=False)
print(optimizer)
```

Output:
```python
Trainer(
  optimizer={
    '_target_': 'my_app.Optimizer', 'algo': 'SGD', 'lr': 0.01
  },
  dataset={
    '_target_': 'my_app.Dataset', 'name': 'Imagenet', 'path': '/datasets/imagenet'
  }
)
```

### Parameter conversion strategies
By default, the parameters passed to the target are either primitives (int,
float, bool etc) or OmegaConf containers (`DictConfig`, `ListConfig`).
OmegaConf containers have many advantages over primitive dicts and lists,
including convenient attribute access for keys,
[duck-typing as instances of dataclasses or attrs classes](https://omegaconf.cli.dev/docs/concepts/structured-configs), and
support for [variable interpolation](https://omegaconf.cli.dev/docs/concepts/interpolation)
and [custom resolvers](https://omegaconf.cli.dev/docs/guides/custom-resolvers).
If the callable targeted by `instantiate` leverages OmegaConf's features, it
will make sense to pass `DictConfig` and `ListConfig` instances directly to
that callable.

That being said, in many cases it's desired to pass normal Python dicts and
lists, rather than `DictConfig` or `ListConfig` instances, as arguments to your
callable. You can change instantiate's argument conversion strategy using the
`_convert_` parameter. Supported values are:

- `"none"` : Default behavior, Use OmegaConf containers
- `"partial"` : Convert OmegaConf containers to dict and list, except
  Structured Configs, which remain as DictConfig instances.
- `"object"` : Convert OmegaConf containers to dict and list, except Structured
  Configs, which are converted to instances of the backing dataclass / attr
  class using `OmegaConf.to_object`.
- `"all"` : Convert everything to primitive containers

The conversion strategy applies recursively to all subconfigs of the instantiation target.
Here is an example demonstrating the various conversion strategies:

```python
from dataclasses import dataclass
from omegaconf import DictConfig, OmegaConf
from hydra.utils import instantiate

@dataclass
class Foo:
    a: int = 123

class MyTarget:
    def __init__(self, foo, bar):
        self.foo = foo
        self.bar = bar

cfg = OmegaConf.create(
    {
        "_target_": "__main__.MyTarget",
        "foo": Foo(),
        "bar": {"b": 456},
    }
)

obj_none = instantiate(cfg, _convert_="none")
assert isinstance(obj_none, MyTarget)
assert isinstance(obj_none.foo, DictConfig)
assert isinstance(obj_none.bar, DictConfig)

obj_partial = instantiate(cfg, _convert_="partial")
assert isinstance(obj_partial, MyTarget)
assert isinstance(obj_partial.foo, DictConfig)
assert isinstance(obj_partial.bar, dict)

obj_object = instantiate(cfg, _convert_="object")
assert isinstance(obj_object, MyTarget)
assert isinstance(obj_object.foo, Foo)
assert isinstance(obj_object.bar, dict)

obj_all = instantiate(cfg, _convert_="all")
assert isinstance(obj_none, MyTarget)
assert isinstance(obj_all.foo, dict)
assert isinstance(obj_all.bar, dict)
```

Passing the `_convert_` keyword argument to `instantiate` has the same effect as defining
a `_convert_` attribute on your config object. Here is an example creating
instances of `MyTarget` that are equivalent to the above:

```python
cfg_none = OmegaConf.create({..., "_convert_": "none"})
obj_none = instantiate(cfg_none)

cfg_partial = OmegaConf.create({..., "_convert_": "partial"})
obj_partial = instantiate(cfg_partial)

cfg_object = OmegaConf.create({..., "_convert_": "object"})
obj_object = instantiate(cfg_object)

cfg_all = OmegaConf.create({..., "_convert_": "all"})
obj_all = instantiate(cfg_all)
```

### Partial Instantiation
Sometimes you may not set all parameters needed to instantiate an object from the configuration, in this case you can set
`_partial_` to be `True` to get a `functools.partial` wrapped object or method, then complete initializing the object in
the application code. Here is an example:

```python title="Example classes"
class Optimizer:
    algo: str
    lr: float

    def __init__(self, algo: str, lr: float) -> None:
        self.algo = algo
        self.lr = lr

    def __repr__(self) -> str:
        return f"Optimizer(algo={self.algo},lr={self.lr})"


class Model:
    def __init__(self, optim_partial: Any, lr: float):
        super().__init__()
        self.optim = optim_partial(lr=lr)
        self.lr = lr

    def __repr__(self) -> str:
        return f"Model(Optimizer={self.optim},lr={self.lr})"
```

<div className="row">

<div className="col col--5">

```yaml title="Config"
model:
  _target_: my_app.Model
  optim_partial:
    _partial_: true
    _target_: my_app.Optimizer
    algo: SGD
  lr: 0.01
```


</div>

<div className="col col--7">

```python title="Instantiation"
model = instantiate(cfg.model)
print(model)
# "Model(Optimizer=Optimizer(algo=SGD,lr=0.01),lr=0.01)
```

</div>
</div>

If you are repeatedly instantiating the same config,
using `_partial_=True` may provide a significant speedup as compared with regular (non-partial) instantiation.
```python
factory = instantiate(config, _partial_=True)
obj = factory()
```
In the above example, repeatedly calling `factory` would be faster than repeatedly calling `instantiate(config)`.
A caveat of this approach is that the same keyword arguments would be re-used in each call to `factory`.
```python
class Foo:
    ...

class Bar:
    def __init__(self, foo):
        self.foo = foo

bar_conf = {
    "_target_": "__main__.Bar",
    "foo": {"_target_": "__main__.Foo"},
}

bar_factory = instantiate(bar_conf, _partial_=True)
bar1 = bar_factory()
bar2 = bar_factory()

assert bar1 is not bar2
assert bar1.foo is bar2.foo  # the `Foo` instance is re-used here
```
This does not apply if `_partial_=False`,
in which case a new `Foo` instance would be created with each call to `instantiate`.


### Instantiation of builtins

The value of `_target_` passed to `instantiate` should be a "dotpath" pointing
to some callable that can be looked up via a combination of `import` and `getattr`.
If you want to target one of Python's [built-in functions](https://docs.python.org/3/library/functions.html) (such as `len` or `print` or `divmod`),
you will need to provide a dotpath looking up that function in Python's [`builtins`](https://docs.python.org/3/library/builtins.html) module.
```python
from hydra.utils import instantiate
# instantiate({"_target_": "len"}, [1,2,3])  # this gives an InstantiationException
instantiate({"_target_": "builtins.len"}, [1,2,3])  # this works, returns the number 3
```

### Dotpath lookup machinery

Hydra looks up a given `_target_` by attempting to find a module that
corresponds to a prefix of the given dotpath and then looking for an object in
that module corresponding to the dotpath's tail. For example, to look up a `_target_`
given by the dotpath `"my_module.my_nested_module.my_object"`, hydra first locates
the module `my_module.my_nested_module`, then find `my_object` inside that nested module.

Hydra exposes an API allowing direct use of this dotpath lookup machinery.
The following two functions, which can be imported from the <GithubLink to="hydra/utils.py">hydra.utils</GithubLink> module,
accept a string-typed dotpath as an argument and return the located class/callable/object:
```python
def get_class(path: str) -> type:
    """
    Look up a class based on a dotpath.
    Fails if the path does not point to a class.

    >>> import my_module
    >>> from hydra.utils import get_class
    >>> assert get_class("my_module.MyClass") is my_module.MyClass
    """
    ...

def get_method(path: str) -> Callable[..., Any]:
    """
    Look up a callable based on a dotpath.
    Fails if the path does not point to a callable object.

    >>> import my_module
    >>> from hydra.utils import get_method
    >>> assert get_method("my_module.my_function") is my_module.my_function
    """
    ...

# Alias for get_method
get_static_method = get_method
```
