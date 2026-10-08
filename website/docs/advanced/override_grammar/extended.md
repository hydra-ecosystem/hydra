---
id: extended
sidebar_label: Extended Override syntax
hide_title: true
---

##  Extended Override syntax
Hydra Overrides supports functions.
When calling a function, one can optionally name parameters. This is following the Python
convention of naming parameters.

<div className="row">
<div className="col col--6">

```python title="Example function"
def func(a:int, b:str) -> bool:
    ...


```
</div>

<div className="col  col--6">

```python title="Calling function"
func(10,foo)     # Positional only
func(a=10,b=foo) # Named only
func(10,b=foo)   # Mixed
func(a=10,foo)   # Error
```

</div>
</div>


Note the lack of quotes in the examples above. Despite some similarities, this is **not Python**.

:::important
Hydra supports very specific functions. If you would like to have
another function added, please file an issue and explain the use case.
:::

## Sweeps
Sweep overrides are used by Sweepers to determine what to do. For example,
one can instruct the Basic Sweeper to sweep over all combinations of the
ranges `num1=range(0,3)` and `num2=range(0,3)` - resulting in `9` jobs, each getting a
different pair of numbers from `0`, `1` and `2`.

### Choice sweep
```python title="Signature"
def choice(
    *args: str | int | float | bool | dict[Any, Any] | list[Any] | ChoiceSweep
) -> ChoiceSweep:
    """
    A choice sweep over the specified values
    """
```
Choice sweeps are the most common sweeps.
A choice sweep is described in one of two equivalent forms.
```python title="Examples"
db=mysql,postgresql          # a comma separated list of two or more elements.
db=choice(mysql,postgresql)  # choice
```
### Glob choice sweep
```python title="Signature"
def glob(
    include: list[str] | str, exclude: list[str] | str | None = None
) -> Glob:
    """
    A glob selects from all options in the config group.
    inputs are in glob format. e.g: *, foo*, *foo.
    :param include: a string or a list of strings to use as include globs
    :param exclude: a string or a list of strings to use as exclude globs
    :return: A Glob object
    """
```
Assuming the config group **schema** with the options **school**, **support** and **warehouse**:
```python title="Examples"
schema=glob(*)                                # school,support,warehouse
schema=glob(*,exclude=support)                # school,warehouse
schema=glob([s*,w*],exclude=school)           # support,warehouse
```

### Range sweep
Unlike Python, Hydra's range can be used with both integer and floating-point numbers.
In both cases, the range represents a discrete list of values.
```python title="Signature"
def range(
    start: int | float, stop: int | float | None = None, step: int | float = 1
) -> RangeSweep:
    """
    Range is defines a sweeep over a range of integer or floating-point values.
    For a positive step, the contents of a range r are determined by the formula
     r[i] = start + step*i where i >= 0 and r[i] < stop.
    For a negative step, the contents of the range are still determined by the formula
     r[i] = start + step*i, but the constraints are i >= 0 and r[i] > stop.
    """
```

```python title="Examples"
num=range(5)                          # 0,1,2,3,4
num=range(0,5)                        # 0,1,2,3,4
num=range(0,5,2)                      # 0,2,4
num=range(0,10,3.3)                   # 0.0,3.3,6.6,9.9
num=range(-5,step=-1)                 # 0,-1,-2,-3,-4
```

### Interval sweep
An interval sweep represents all the floating point value between two values.
This is used by optimizing sweepers like Ax and Nevergrad. The basic sweeper does not support interval.

```python title="Signature"
def interval(start: int | float, end: int | float) -> IntervalSweep:
    """
    A continuous interval between two floating point values.
    value=interval(x,y) is interpreted as x <= value < y
    """
```
```python title="Examples"
interval(1.0,5.0)  # 1.0 <= x < 5.0
interval(1,5)      # 1.0 <= x < 5.0, auto-cast to floats
```

### Tag
With tags you can add arbitrary metadata to a sweep. The metadata can be used by advanced sweepers.
```python title="Signature"
def tag(*args: str | Sweep, sweep: Sweep | None = None) -> Sweep:
    """
    Tags the sweep with a list of string tags.
    """
```
```python title="Examples"
tag(log,interval(0,1))          # 1.0 <= x < 1.0, tags=[log]
tag(foo,bar,interval(0,1))      # 1.0 <= x < 1.0, tags=[foo,bar]
```

## Reordering lists and sweeps

### sort
```python title="Signature"
def sort(
    *args: ElementType | ChoiceSweep | RangeSweep,
    sweep: ChoiceSweep | RangeSweep | None = None,
    list: list[Any] | None = None,
    reverse: bool = False,
) -> Any:
    """
    Sort an input list or sweep.
    reverse=True reverses the order
    """
```
```python title="Examples"
# sweep
sort(1,3,2)                         # ChoiceSweep(1,2,3)
sort(1,3,2,reverse=true)            # ChoiceSweep(3,2,1)
sort(choice(1,2,3))                 # ChoiceSweep(1,2,3)
sort(sweep=choice(1,2,3))           # ChoiceSweep(1,2,3)
sort(choice(1,2,3),reverse=true)    # ChoiceSweep(3,2,1)
sort(range(10,1))                   # range in ascending order
sort(range(1,10),reverse=true)      # range in descending order

# lists
sort([1,3,2])                       # [1,2,3]
sort(list=[1,3,2])                  # [1,2,3]
sort(list=[1,3,2], reverse=true)    # [3,2,1]

# single value returned as is
sort(1)                             # 1
```

Sorting a sweep clears any preceding `shuffle()`. Use `shuffle(sort(...))` to
shuffle the sorted sweep again.

### shuffle
```python title="Signature"
def shuffle(
    *args: ElementType | ChoiceSweep | RangeSweep,
    sweep: ChoiceSweep | RangeSweep | None = None,
    list: list[Any] | None = None,
) -> list[Any] | ChoiceSweep | RangeSweep:
    """
    Shuffle input list or sweep (does not support interval)
    """
```
```python title="Examples"
shuffle(a,b,c)                                       # shuffled a,b,c
shuffle(choice(a,b,c)), shuffle(sweep=choice(a,b,c)) # shuffled choice(a,b,c)
shuffle(range(1,10))                                 # shuffled range(1,10)
shuffle([a,b,c]), shuffle(list=[a,b,c])              # shuffled list [a,b,c]
```

## Type casting
You can cast values and sweeps to `int`, `float`, `bool` or `str`.
```python title="Example"
int(3.14)                  # 3 (int)
int(value=3.14)            # 3 (int)
float(10)                  # 10.0 (float)
str(10)                    # "10" (str)
bool(1)                    # true (bool)
float(range(1,10))         # choice of 1.0,2.0,...,9.0
str([1,2,3])               # ['1','2','3']
str({a:10})                # {a:'10'}
```

Below are pseudo code snippets that illustrates the differences between Python's casting and Hydra's casting.

#### Casting string to bool

<div className="row">
<div className="col col--6">

```python title="Python"
def bool(value: Any) -> bool:
    if isinstance(value, str):
        return len(value) > 0
    else:
        return bool(value)




```
</div>

<div className="col  col--6">

```python title="Hydra"
def bool(s: str) -> bool:
    if isinstance(value, str):
        if value.lower() == "false":
            return False
        elif value.lower() == "true":
            return True
        else:
            raise ValueError()
    return bool(value)
```

</div>
</div>

#### Casting lists
Casting lists results in a list where each element is recursively cast.
Failure to cast an element in the list fails the cast of the list.

<div className="row">
<div className="col col--6">

```python title="Python"
def cast_int(value: Any):
    if isinstance(value, list):
        raise TypeError()
    else:
        return int(v)


```
</div>

<div className="col  col--6">

```python title="Hydra"
def cast_int(value: Any):
    if isinstance(v, list):
        return list(map(cast_int, v))
    else:
        return int(v)


```

</div>
</div>


#### Casting dicts
Casting dicts results in a dict where values are recursively cast, but keys are unchanged.
Failure to cast a value in the dict fails the cast of the entire dict.

<div className="row">
<div className="col col--6">

```python title="Python"
def cast_int(value: Any):
    if isinstance(value, dict):
        raise TypeError()
    else:
        return int(v)


```
</div>

<div className="col  col--6">

```python title="Hydra"
def cast_int(value: Any):
    if isinstance(value, dict):
        return apply_to_values(
            value, cast_int
        )
    else:
        return int(v)
```

</div>
</div>

#### Casting ranges
Ranges can be cast to float or int. Each generated value is cast, producing a
choice sweep with the same number of elements, including duplicates. Tags and
shuffling are preserved. Cast ranges are materialized during parsing.

```python title="Examples"
int(range(0,5,1.5))        # choice(0,1,3,4)
int(range(0,1,0.25))       # choice(0,0,0,0)
```

This changed in Hydra 1.4. See
[Range sweep casting](/docs/upgrades/1.3_to_1.4/breaking_changes#range-sweep-casting).

<div className="row">
<div className="col col--6">

```python title="Python"
def cast_int(value: Any):
    if isinstance(value, RangeSweep):
        raise TypeError()
    else:
        return int(v)




```
</div>

<div className="col  col--6">

```python title="Hydra"
def cast_int(value: Any):
    if isinstance(value, RangeSweep):
        return ChoiceSweep(
            list=[int(item) for item in value.range()],
            tags=value.tags.copy(),
            shuffle=value.shuffle,
        )
    else:
        return int(v)
```

</div>
</div>

### Conversion matrix
Below is the conversion matrix from various inputs to all supported types.
Input are grouped by type.


[//]: # (Conversion matrix source: https://docs.google.com/document/d/1JDZGHKk4PrZHqsTTS6ao-DQOu2eVD4ULR6uAxVUR-WI/edit#)

|                    	| int()       	| float()           	| str()             	| bool()                	| json()                 |
|--------------------	|-------------	|-------------------	|-------------------	|-----------------------	|--------------------	 |
|         10         	| 10          	| 10.0              	| “10”              	| true                  	| “10”                   |
|          0         	| 0           	| 0.0               	| “0”               	| false                 	| “0”                    |
|        10.0        	| 10          	| 10.0              	| “10.0”            	| true                  	| “10.0”                 |
|         0.0        	| 0           	| 0.0               	| “0.0”             	| false                 	| “0.0”                  |
|         inf        	| error       	| inf               	| ‘inf’             	| true                  	| “Infinity”             |
|         nan        	| error       	| nan               	| ‘nan’             	| true                  	| “NaN”                  |
|         1e6        	| 1,000,000   	| 1e6               	| ‘1000000.0’       	| true                  	| “1000000.0”            |
|         foo        	| error       	| error             	| foo               	| error                 	| '“foo”'                |
|  “” (empty string) 	| error       	| error             	| “”                	| error                 	| '“”'                   |
|        “10”        	| 10          	| 10.0              	| “10”              	| error                 	| '“10”'                 |
|       “10.0”       	| error       	| 10.0              	| “10.0”            	| error                 	| '“10.0”'               |
|       “true”       	| error       	| error             	| “true”            	| true                  	| '“true”'               |
|       “false”      	| error       	| error             	| “false”           	| false                 	| '“false”'              |
|      “[1,2,3]”     	| error       	| error             	| “[1,2,3]”         	| error                 	| '“[1,2,3]”'            |
|      “\{a:10}”      	| error       	| error             	| “\{a:10}”          	| error                 	| '“\{a:10}”'             |
|        true        	| 1           	| 1.0               	| “true”            	| true                  	| “true”                 |
|        false       	| 0           	| 0.0               	| “false”           	| false                 	| “false”                |
|         []         	| []          	| []                	| []                	| []                    	| “[]”                   |
|       [0,1,2]      	| [0,1,2]     	| [0.0,1.0,2.0]     	| [“0”,”1”,”2”]     	| [false,true,true]     	| “[1, 2, 3]”            |
|       [1,[2]]      	| [1,[2]]     	| [1.0,[2.0]]       	| [“1”,[“2”]]       	| [true,[true]]         	| “[1, [2]]”             |
|        [a,1]       	| error       	| error             	| [“a”,”1”]         	| error                 	| '[“a”, 1]'             |
|         \{}         	| \{}          	| \{}                	| \{}                	| \{}                    	| “\{}”                   |
|       \{a:10}       	| \{a:10}      	| \{a:10.0}          	| \{a:”10”}          	| \{a: true}               	| '\{“a”: 10}'            |
|     \{a:[0,1,2]}    	| \{a:[0,1,2]} 	| \{a:[0.0,1.0,2.-]} 	| \{a:[“0”,”1”,”2”]} 	| \{a:[false,true,true]} 	| '\{“a”: [1, 2, 3]}'     |
|    \{a:10,b:xyz}    	| error       	| error             	| \{a:”10”,b:”xyz”}  	| error                 	| '\{“a”: 10, “b”: “xyz”}'|
|     choice(0,1)    	| choice(0,1) 	| choice(0.0,1.0)   	| choice(“0”,“1”)   	| choice(false,true)    	| choice(“0”, “1”)       |
|     choice(a,b)    	| error       	| error             	| choice(“a”,”b”)   	| error                 	| choice('“a”', '“b”')   |
|     choice(1,a)    	| error       	| error             	| choice(“1”,”a”)   	| error                 	| choice(“1”, '“a”')     |
| interval(1.0, 2.0) 	| interval(1, 2)| interval(1.0, 2.0)   	| error             	| error                 	| interval(“1.0”, “2.0”) |
| interval(1, 2)     	| interval(1, 2)| interval(1.0, 2.0)   	| error             	| error                 	| interval(“1”, “2”)     |
|     range(1,10)    	| choice(1,...,9) 	| choice(1.0,...,9.0)   	| error             	| error                 	| error                  |
|  range(1.0, 10.0)  	| choice(1,...,9) 	| choice(1.0,...,9.0)   	| error             	| error                 	| error                  |
