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

Top-level list and tuple inputs are instantiated element by element. Partial
instantiation is not supported for these sequence inputs.

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
                            none    : Passed objects are DictConfig, ListConfig and
                                      TupleConfig, default
                            partial : Passed objects are converted to dict, list and
                                      tuple, with the exception of Structured Configs
                                      (and their fields).
                            object  : Passed objects are converted to dict, list and tuple.
                                      Structured Configs are converted to instances of the
                                      backing dataclass / attr class.
                            all     : Passed objects are dicts, lists, tuples and
                                      primitives without a trace of OmegaConf containers.
                                      Structured configs are converted to primitive
                                      containers too.
                       _partial_: If True, return functools.partial wrapped method or object
                                  False by default. Configure per target.
        :param _target_whitelist_: A target string, list of target strings,
                                   object returned by target_whitelist(), or
                                   UNSAFE_ALLOW_ALL_TARGETS. Passing None
                                   preserves legacy behavior unless a
                                   target_whitelist() context is active.
        :param args: Optional positional parameters pass-through
        :param kwargs: Optional named parameters to override
                       parameters in the config object. Parameters not present
                       in the config objects are being passed as is to the target.
                       Dataclass and attrs instances are passed through without
                       conversion or recursive instantiation.
        :return: if _target_ is a class name: the instantiated object
                 if _target_ is a callable: the return value of the call
        """

    # Alias for instantiate
    call = instantiate
    ```

</details><br/>

<details>
    <summary>Target whitelist API (Expand for details)</summary>

    ```python
    def target_whitelist(
        target_whitelist: str | Sequence[str] | UNSAFE_ALLOW_ALL_TARGETS | None,
        reset: bool = False,
    ):
        """
        Create a target whitelist object for hydra.utils.instantiate().

        The returned object can be used as a context manager to apply a whitelist
        to instantiate() calls in the current context, or passed to instantiate()
        as _target_whitelist_.

        :param target_whitelist: A target string, list of target strings, or
                                 UNSAFE_ALLOW_ALL_TARGETS. A trailing .*
                                 allows targets under a package prefix.
        :param reset: If True, ignore any outer target_whitelist() context.
                      If False, add these targets to the current context.
        """
    ```

</details><br/>

The config passed to these functions must have a key called `_target_`, with the value of a fully qualified class name, class method, static method or callable.
For convenience, `None` config results in a `None` object.

Create a whitelist object with `target_whitelist()`. Use it as a context manager
to apply a whitelist to every `instantiate()` call in a block. This is useful
when another function or framework calls `instantiate()` internally, or when
calling `instantiate()` multiple times with the same whitelist:

```python
from hydra.utils import instantiate, target_whitelist

with target_whitelist("my_app.*"):
    framework_function(cfg)
```

Or pass it directly to one `instantiate()` call:

```python
model = instantiate(
    cfg.model,
    _target_whitelist_=target_whitelist("my_app.models.*"),
)
```

Nested `target_whitelist()` scopes stack by default: an inner scope adds its
targets to the outer scope.

```python
with target_whitelist("my_app.models.*"):
    with target_whitelist("my_app.optimizers.*"):
        train(cfg)
```

Use `reset=True` when the inner scope should replace the outer scope instead of
adding to it:

```python
with target_whitelist("my_app.*"):
    with target_whitelist("my_app.models.*", reset=True):
        instantiate(cfg.model)
```

For simple direct calls, `_target_whitelist_` also accepts a string or list of
strings.

The wildcard `*` by itself is not allowed as a whitelist entry. To explicitly
preserve legacy all-target behavior, use `UNSAFE_ALLOW_ALL_TARGETS`:

```python
from hydra.utils import UNSAFE_ALLOW_ALL_TARGETS, instantiate

component = instantiate(
    cfg.component,
    _target_whitelist_=UNSAFE_ALLOW_ALL_TARGETS,
)
```

**Named arguments** : Config fields (except reserved fields like `_target_`) are passed as named arguments to the target.
Named arguments in the config can be overridden by passing named argument with the same name in the `instantiate()` call-site.

Call-site arguments replace the corresponding arguments passed to the target
without modifying the input configuration. Interpolations in other configured
arguments resolve against those call-site values. Call-site values are not
generally coerced against Structured Config fields. Dictionary overrides of
Structured Config nodes are the exception, as described below.

Plain Python call-site overrides must be concrete runtime values. Hydra rejects
`???` and strings containing OmegaConf interpolation syntax (`${...}`),
including inside native containers. Explicit OmegaConf containers retain
normal OmegaConf semantics and may contain missing values or interpolations.

Configuration values are resolved lazily as instantiation proceeds instead of
resolving the full configuration tree up front. Calls on OmegaConf inputs
without call-site overrides do not make an additional input copy. When
overrides are present, Hydra uses a private copy so configured interpolations
resolve against the call-site values while leaving the input unchanged. Runtime
state established by an earlier target can still be used while resolving a
later argument.

Primitive values, native `list`, `tuple`, and `dict` containers, and OmegaConf
containers passed at the call-site retain Hydra's normal configuration
semantics, including instantiation and conversion where applicable.

When a `dict` or `DictConfig` call-site argument overrides a parameter of the
target being instantiated, it is handled according to the configured parameter
value:

- If the configured value is a Structured Config node, Hydra merges the
  dictionary into a copy of the node, preserving its schema, validation, and
  fields that the dictionary does not name. Interpolations within that node
  resolve against the merged values.
- Otherwise, if the configured mapping contains `_target_`, Hydra merges the
  dictionary into that target config, preserving its target, instantiation
  settings, and arguments that the dictionary does not name. `_recursive_`
  controls whether the result is instantiated or passed through; it does not
  change this merge behavior.
- Any other configured mapping is replaced entirely.

Hydra uses the configured parameter's effective value after interpolation to
select among these cases. If the interpolation cannot be resolved, the
call-site dictionary replaces it.

```python
cfg = OmegaConf.create(
    {
        "_target_": "my_app.Trainer",
        "optimizer": {"_target_": "my_app.Optimizer", "lr": 0.1, "momentum": 0.5},
        "tags": {"env": "prod", "team": "ml"},
    }
)

# optimizer is a nested target, so momentum=0.5 is preserved
# tags is a plain dict, so it is replaced and team is not passed
instantiate(cfg, optimizer={"lr": 0.3}, tags={"env": "dev"})
```

Already-constructed dataclass and attrs instances are regular runtime objects.
They remain unchanged, even if they define `_target_`. To use such an instance
as configuration, explicitly convert it with `OmegaConf.structured(instance)`.

See the [Hydra 1.4 upgrade guide](/docs/upgrades/1.3_to_1.4/instantiate_resolution)
for the compatibility impact and an example.

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
with target_whitelist("my_app.*"):
    opt = instantiate(cfg.optimizer)
print(opt)
# Optimizer(algo=SGD,lr=0.01)
```

</div>
</div>

You can override parameters at the call-site:

```python
with target_whitelist("my_app.*"):
    opt = instantiate(
        cfg.optimizer,
        lr=0.2,
    )
print(opt)
# Optimizer(algo=SGD,lr=0.2)
```


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
with target_whitelist("my_app.*"):
    trainer = instantiate(cfg.trainer)
    print(trainer)
    # Trainer(
    #  optimizer=Optimizer(algo=SGD,lr=0.01),
    #  dataset=Dataset(name=Imagenet, path=/datasets/imagenet)
    # )
```
You can override parameters for nested objects:
```python
with target_whitelist("my_app.*"):
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
with target_whitelist("my_app.*"):
    obj = instantiate(
        cfg.object,
        # pass 1 and 2 as positional arguments
        # to the target object
        1, 2,
        # pass 3 and 4 as positional arguments
        # to a nested child object
        child={"_args_": [3, 4]},
    )
```

### Disable recursive instantiation
You can disable recursive instantiation by setting `_recursive_` to `False` in the config node or in the call-site
In that case the Trainer object will receive an OmegaConf DictConfig for nested dataset and optimizer instead of the instantiated objects.
```python
trainer = instantiate(
    cfg.trainer,
    _recursive_=False,
    _target_whitelist_="my_app.Trainer",
)
print(trainer)
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
float, bool etc) or OmegaConf containers (`DictConfig`, `ListConfig`,
`TupleConfig`). OmegaConf containers have many advantages over primitive dicts,
lists, and tuples,
including convenient attribute access for keys,
[duck-typing as instances of dataclasses or attrs classes](https://omegaconf.readthedocs.io/en/latest/structured_config.html), and
support for [variable interpolation](https://omegaconf.readthedocs.io/en/latest/usage.html#variable-interpolation)
and [custom resolvers](https://omegaconf.readthedocs.io/en/latest/custom_resolvers.html).
If the callable targeted by `instantiate` leverages OmegaConf's features, it
will make sense to pass `DictConfig`, `ListConfig`, and `TupleConfig` instances
directly to that callable.

That being said, in many cases it's desired to pass normal Python dicts and
lists and tuples, rather than `DictConfig`, `ListConfig`, or `TupleConfig`
instances, as arguments to your callable. You can change instantiate's argument
conversion strategy using the `_convert_` parameter. Supported values are:

- `"none"` : Default behavior, Use OmegaConf containers
- `"partial"` : Convert OmegaConf containers to dict, list, and tuple, except
  Structured Configs, which remain as DictConfig instances.
- `"object"` : Convert OmegaConf containers to dict, list, and tuple, except
  Structured Configs, which are converted to instances of the backing dataclass
  / attr class using `OmegaConf.to_object`.
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

obj_none = instantiate(cfg, _convert_="none", _target_whitelist_="__main__.*")
assert isinstance(obj_none, MyTarget)
assert isinstance(obj_none.foo, DictConfig)
assert isinstance(obj_none.bar, DictConfig)

obj_partial = instantiate(cfg, _convert_="partial", _target_whitelist_="__main__.*")
assert isinstance(obj_partial, MyTarget)
assert isinstance(obj_partial.foo, DictConfig)
assert isinstance(obj_partial.bar, dict)

obj_object = instantiate(cfg, _convert_="object", _target_whitelist_="__main__.*")
assert isinstance(obj_object, MyTarget)
assert isinstance(obj_object.foo, Foo)
assert isinstance(obj_object.bar, dict)

obj_all = instantiate(cfg, _convert_="all", _target_whitelist_="__main__.*")
assert isinstance(obj_all, MyTarget)
assert isinstance(obj_all.foo, dict)
assert isinstance(obj_all.bar, dict)
```

Passing the `_convert_` keyword argument to `instantiate` has the same effect as defining
a `_convert_` attribute on your config object. Here is an example creating
instances of `MyTarget` that are equivalent to the above:

```python
cfg_none = OmegaConf.create({..., "_convert_": "none"})
obj_none = instantiate(cfg_none, _target_whitelist_="__main__.*")

cfg_partial = OmegaConf.create({..., "_convert_": "partial"})
obj_partial = instantiate(cfg_partial, _target_whitelist_="__main__.*")

cfg_object = OmegaConf.create({..., "_convert_": "object"})
obj_object = instantiate(cfg_object, _target_whitelist_="__main__.*")

cfg_all = OmegaConf.create({..., "_convert_": "all"})
obj_all = instantiate(cfg_all, _target_whitelist_="__main__.*")
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
with target_whitelist("my_app.*"):
    model = instantiate(cfg.model)
print(model)
# "Model(Optimizer=Optimizer(algo=SGD,lr=0.01),lr=0.01)
```

</div>
</div>

If you are repeatedly instantiating the same config,
using `_partial_=True` may provide a significant speedup as compared with regular (non-partial) instantiation.
```python
factory = instantiate(
    config,
    _partial_=True,
    _target_whitelist_="my_app.*",
)
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

bar_factory = instantiate(
    bar_conf,
    _partial_=True,
    _target_whitelist_="__main__.*",
)
bar1 = bar_factory()
bar2 = bar_factory()

assert bar1 is not bar2
assert bar1.foo is bar2.foo  # the `Foo` instance is re-used here
```
This does not apply if `_partial_=False`,
in which case a new `Foo` instance would be created with each call to `instantiate`.

<details>
<summary>Security considerations</summary>

Hydra distinguishes between two denied-target classes. Generally problematic
targets are blocked in legacy mode but trusted Python code can authorize them
with `_target_whitelist_`. Targets that let config data control executable
behavior, unsafe loading, imports, or generic dispatch cannot be authorized by
a normal target whitelist. Use a narrow trusted wrapper instead. The explicit
`UNSAFE_ALLOW_ALL_TARGETS` escape hatch disables both protections.

Use the native `_partial_: true` option instead of configuring
`_target_: functools.partial`. Direct `functools.partial` targets and equivalent
constructor spellings such as `functools.partial.__new__` are deprecated. When
used with `_target_whitelist_`, both the partial constructor and its effective
callable must be authorized. Direct partial targets cannot themselves use
`_partial_: true` with a real target whitelist because validation would be
deferred. Equivalent constructor spellings also cannot construct partial
subclasses while safety checks are active because subclass overrides can hide
their invocation behavior.

If a config targets `hydra.utils.get_class`, `get_method`,
`get_static_method`, or `get_object`, whitelist both the discovery helper and
the dotpath in its `path` argument. Hydra applies the same target policy to the
selected path and to the canonical identity of a callable result. Discovery
helpers cannot use `_partial_: true` with a real target whitelist because the
path could be supplied after authorization has finished. Hydra's `instantiate`
and `call` functions cannot themselves be authorized as config targets; invoke
them from trusted Python code.

Hydra does not authorize `builtins.getattr`, `hasattr`, `setattr`, or `delattr`
through a real target whitelist. Attribute operations can execute property or
custom descriptor code before Hydra can inspect the operation. Access or mutate
the intended attribute from trusted Python code instead. The equivalent
`object.__getattribute__` and `type.__getattribute__` dispatch targets cannot be
authorized either. These targets remain available on the legacy no-whitelist
path; `getattr` returns non-callable values normally and checks callable results
against the blocklist. The explicit `UNSAFE_ALLOW_ALL_TARGETS` escape hatch
preserves unrestricted legacy behavior.

Hydra also refuses to authorize generic `operator` dispatch and selection
targets, including `call`, `attrgetter`, `methodcaller`, `getitem`, `itemgetter`,
`setitem`, `delitem`, and `contains`, or their canonical `_operator` spellings.
Set `_target_` to the intended callable instead. These generic operator targets
are also blocklisted on the legacy no-whitelist path.

</details>

### Instantiation of builtins

The value of `_target_` passed to `instantiate` should be a "dotpath" pointing
to some callable that can be looked up via a combination of `import` and `getattr`.
If you want to target one of Python's [built-in functions](https://docs.python.org/3/library/functions.html) (such as `len` or `print` or `divmod`),
you will need to provide a dotpath looking up that function in Python's [`builtins`](https://docs.python.org/3/library/builtins.html) module.
```python
from hydra.utils import instantiate
# instantiate({"_target_": "len"}, [1,2,3])  # this gives an InstantiationException
instantiate(
    {"_target_": "builtins.len"},
    [1,2,3],
    _target_whitelist_="builtins.len",
)  # this works, returns the number 3
```

### Dotpath lookup machinery

Hydra looks up a given `_target_` by attempting to find a module that
corresponds to a prefix of the given dotpath and then looking for an object in
that module corresponding to the dotpath's tail. For example, to look up a `_target_`
given by the dotpath `"my_module.my_nested_module.my_object"`, hydra first locates
the module `my_module.my_nested_module`, then find `my_object` inside that nested module.

Hydra exposes an API allowing direct use of this dotpath lookup machinery.
The following three functions, which can be imported from the <GithubLink to="hydra/utils.py">hydra.utils</GithubLink> module,
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

def get_object(path: str) -> Any:
    """
    Look up a callable based on a dotpath.

    >>> import my_module
    >>> from hydra.utils import get_object
    >>> assert get_object("my_module.my_object") is my_module.my_object
    """
    ...
```
