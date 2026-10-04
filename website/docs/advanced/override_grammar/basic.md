---
id: basic
hide_title: true
sidebar_label: Basic Override syntax
---

import GithubLink from "@site/src/components/GithubLink"

## Basic Override syntax
You can manipulate your configuration with overrides (via the command line or the Compose API). This includes:
- Modifying the `Defaults List`
- Modifying the config object

Overrides matching a config group or a Defaults List config entry are modifying the `Defaults List`;
The rest are manipulating the config object.
Bracket paths always manipulate the config object, even if a config group has
the same name.

## Basic examples
### Modifying the Config Object
- Overriding a config value : `foo.bar=value`
- Appending a config value : `+foo.bar=value`
- Appending or overriding a config value : `++foo.bar=value`
- Removing a config value : `~foo.bar`, `~foo.bar=value`

### Modifying the Defaults List
- Overriding selected Option: `db=mysql`, `server/db=mysql`
- Appending to Defaults List: `+db=mysql`, `+server/db=mysql`
- Deleting from Defaults List: `~db`, `~db=mysql`, `~server/db`, `~server/db=mysql`
- Deleting a non-overridable Defaults List config entry: `~server/site/fb`

## Grammar
Hydra supports a rich [DSL](https://en.wikipedia.org/wiki/Domain-specific_language) in the command line.
Below are the parser rules from grammar. You can see the full <GithubLink to="hydra/grammar/OverrideLexer.g4">Lexer</GithubLink> and <GithubLink to="hydra/grammar/OverrideParser.g4">Parser</GithubLink> definitions on GitHub.

```antlr4 title="OverrideParser.g4"
// High-level command-line override.

override: (
      key EQUAL value?                           // key=value, key= (for empty value)
    | TILDE key (EQUAL value?)?                  // ~key | ~key=value
    | PLUS PLUS? key EQUAL value?                // +key= | +key=value | ++key=value
) EOF;

// Key:
key : packageOrGroup (AT package)? | VALUE_PATH; // key | group@pkg | items[0]

packageOrGroup: package | ID (SLASH ID)+;        // db, hydra/launcher
package: ( | ID | KEY_SPECIAL | DOT_PATH);       // db, $db, hydra.launcher, or the empty (for _global_ package)

// Elements (that may be swept over).

value: element | simpleChoiceSweep;

element:
      primitive
    | listContainer
    | dictContainer
    | function
;

simpleChoiceSweep:
      element (COMMA element)+                   // value1,value2,value3
;

// Functions.

argName: ID EQUAL;
function: ID POPEN (argName? element (COMMA argName? element )* )? PCLOSE;

// Data structures.

listContainer: BRACKET_OPEN                      // [], [1,2,3], [a,b,[1,2]]
    (element(COMMA element)*)?
BRACKET_CLOSE;

dictContainer: BRACE_OPEN (dictKeyValuePair (COMMA dictKeyValuePair)*)? BRACE_CLOSE;  // {}, {a:10,b:20}
dictKeyValuePair: dictKey COLON element;

// Primitive types.

primitive:
      QUOTED_VALUE                               // 'hello world', "hello world"
    | (   ID                                     // foo-bar_10
        | NULL                                   // null, NULL
        | INT                                    // 0, 10, -20, 1_000_000
        | FLOAT                                  // 3.14, -20.0, 1e-1, -10e3
        | BOOL                                   // true, TrUe, false, False
        | INTERPOLATION                          // ${foo.bar}, ${oc.env:USER,me}
        | UNQUOTED_CHAR                          // /, -, \, +, ., $, %, *, @, ?, |
        | COLON                                  // :
        | ESC                                    // \\, \(, \), \[, \], \{, \}, \:, \=, \ , \\t, \,
        | WS                                     // whitespaces
    )+;

// Same as `primitive` except that `COLON` and `INTERPOLATION` are not allowed.
dictKey:
    (   ID                                     // foo-bar_10
      | NULL                                   // null, NULL
      | INT                                    // 0, 10, -20, 1_000_000
      | FLOAT                                  // 3.14, -20.0, 1e-1, -10e3
      | BOOL                                   // true, TrUe, false, False
      | UNQUOTED_CHAR                          // /, -, \, +, ., $, %, *, @, ?, |
      | ESC                                    // \\, \(, \), \[, \], \{, \}, \:, \=, \ , \\t, \,
      | WS                                     // whitespaces
    )+;
```

## Elements
### Key
Key is the component before the =. A few examples:
```shell script
foo.bar           # A config key
hydra/launcher    # A config group
group@pkg         # A config group assigned to the package pkg
group@pkg1:pkg2   # A config group changing the package from pkg1 to pkg2
```

#### Bracket paths
Use bracket notation to address list elements or dictionary keys:
```shell script
'items[0]=x'              # Replace the first list element
'items[-1]=x'             # Replace the last list element
'obj[20s_labels]=x'       # Address a dictionary key starting with digits
'items[0].labels[1]=x'    # Combine dotted and bracket segments
'~items[-1]'             # Remove the last list element
'+obj[20s_labels]=x'      # Add an absent dictionary key
'++obj[20s_labels]=x'     # Add or replace a dictionary key
'items[0]=x,y'           # Sweep over the first list element
```
Quote the entire override on the command line to protect brackets from shell
expansion. Bracket paths support the same value override operators and sweeps
as dotted paths. `+` rejects an existing scalar value; it does not append an
indexed list element. An out-of-range list index fails, including with `++`.

Bracket selectors must be nonempty and contain only letters, digits, `_`, `-`,
or `$`. They do not support quoted keys, spaces, commas, dots, `/`, `@`, `=`,
or escapes. Paths must begin with a regular key and contain complete bracket
selectors. Bracket paths address values, so they cannot select config groups
or use an `@package` suffix. Config-group and package syntax is unchanged.

### Quoted values
Hydra supports both double quotes and single quoted values.
Quoted strings can accept any value between the quotes, but some characters need escaping:
* to include a single quote in a single quoted string, use `\'` (for double quotes in a double quoted string, use `\"`)
* any sequence of `\` characters preceding a quote (either an escaped quote as described in the previous point, or the closing quote)
  must be escaped by doubling the number of `\`

<div className="row">
<div className="col col--6">

```python title="Double quotes"
"hello there"
"escaped \"double quote\""
"the path is C:\\\"some folder\"\\"
"1,2,3"
"{a:10} ${xyz}"
"'single quoted string'"
```

</div>

<div className="col  col--6">

```python title="Single quotes"
'hello there'
'escaped \'single quote\''
'the path is C:\\\'some folder\'\\'
'1,2,3'
'{a:10} ${xyz}'
'"double quoted string"'
```
</div>
</div>

It may be necessary to use multiple pairs of quotes to prevent your
shell from consuming quotation marks before they are passed to hydra.

```shell
$ python my_app.py '+foo="{a: 10}"'
foo: '{a: 10}'

$ python my_app.py '+foo={a: 10}'
foo:
  a: 10

```

Here are some best practices around quoting in CLI overrides:
- Quote the whole key=value pair with single quotes, as in the first two
  examples above. These quotes are for the benefit of the shell.
- Do not quote keys.
- Only quote values if they contain a space. It will work if you always quote
  values, but it will turn numbers/dicts/lists into strings (as in the first
  example above).
- When you are quoting values, use double quotes to avoid collision with the
  outer single quoted consumed by the shell.

### Whitespaces in unquoted values
Unquoted Override values can contain non leading or trailing whitespaces.
For example, `msg=hello world` is a legal override (key is `msg` and value is the string `hello world`).
Normally, your shell will interpret values with whitespaces as being multiple parameters (`key=a b` would be interpreted as `key=a` and `b`).
To prevent this you can quote them with a single quote. For example:

```shell
$ python my_app.py 'msg=hello world'
```

Note that trailing and leading whitespace are ignored, the above is equivalent to:

```shell
$ python my_app.py 'msg=    hello world    '
```

### Escaped characters in unquoted values
Hydra's parser considers some characters to be illegal in unquoted strings.
These otherwise special characters may be included in unquoted values by escaping them with a `\`.
These characters are: `\()[]{}:=, \t` (the last two ones being the whitespace and tab characters).

As an example, in the following `dir` is set to the string `job{a=1,b=2,c=3}`:

```shell
$ python my_app.py 'dir=job\{a\=1\,b\=2\,c\=3\}'
```

As an alternative to escaping special characters with a backslash, the value containing the special character may be quoted:

```shell
$ python my_app.py 'dir=A[B'    # parser error
$ python my_app.py 'dir="A[B"'  # ok
$ python my_app.py 'dir=A\[B'   # ok
```

### Primitives
- `id` : oompa10, loompa_12
- `null`: null
- `int`: 10, -20, 0, 1_000_000.
- `float`: 3.14, -10e6, inf, -inf, nan.
- `bool`: true, false
- `dot_path`: foo.bar
- `interpolation`: $\{foo.bar}, $\{oc.env:USER,me}

Constants (null, true, false, inf, nan) are case-insensitive.

:::important
Always single-quote interpolations in the shell, to prevent replacement with shell variables:
```shell
$ python my_app.py 'dir=/root/${name}'
```
In addition, more complex interpolations containing special characters may require being passed within a quoted value
(note the extra double quotes surrounding the interpolation):
```shell
$ python my_app.py 'dir="${get_dir: {root: /root, name: ${name}}}"'
```
:::

## Dictionaries and Lists

### Lists
```python
foo=[1,2,3]
nested=[a,[b,[c]]]
```

Lists are assigned, not merged.

### Dictionaries
```python
foo={a:10,b:20}
nested={a:10,b:{c:30,d:40}}
```

Dictionaries are merged, not assigned. The following example illustrates the point:
<div className="row">
<div className="col col--6">

```yaml title="Input config"
db:
  driver: mysql
  user: ???
  pass: ???
```

</div>

<div className="col  col--6">


```yaml title="db={user:root,pass:1234}"
db:
  driver: mysql
  user: root
  pass: 1234
```

</div>
</div>


:::important
Always single-quote overrides that contains dicts and lists in the shell.
:::

### Sweeper syntax
A choice sweep is comma separated list with two or more elements:
```shell script
key=a,b                       # Simple sweep: ChoiceSweep(a, b)
key="a,b","c,d"               # Elements can be quoted strings, ChoiceSweep("a,b", "c,d")
key=[a,b],[c,d]               # Elements can be real lists, ChoiceSweep([a,b], [c,d])
key={a:10, b:20},{c:30,d:40}  # And dictionaries: ChoiceSweep({a:10, b:20}, {c:30,d:40})
```
More sweeping options are described in the [Extended Grammar page](extended.md).

:::important
You may need to quote your choice sweep in the shell.
:::


### Functions
Hydra supports several functions in the command line.
See the [Extended Grammar page](extended.md) for more information.

## Working with your shell
All shells interprets command line inputs and may change what is passed to the process.
A good way to determine what the shell is doing to your command is to `echo` it.
```shell script
# bash output
$ echo foo_{a:10,b:20} ${HOME} [b,c]*
foo_a:10 foo_b:20 /home/omry build_helpers
$ echo 'foo_{a:10,b:20}' '${HOME}' '[b,c]*'
foo_{a:10,b:20} ${HOME} [b,c]*
```

If in doubt, quote a command line element with a **single quote** (`'`).

If you want to pass quotes to Hydra in a shell quoted string, it's best to pass double quotes.
```shell script
$ echo '"hello world"'
"hello world"
```

You can use some shell specific commands to change their behavior, but the cost will be that their behavior will change.
### Bash
You can disable braces expansion, filename generation (globing) and hist expansion. Please note that this will change
your shell behavior for the current session.
```shell script
$ set +o braceexpand -o noglob +o histexpand
$ echo key1={a:10,b:20} key2=${HOME} key=[b]*
key1={a:10,b:20} key2=/home/omry key=[b]*
# does not help with () though:
$ echo key=choice(a,b,c)
bash: syntax error near unexpected token '('
$ echo 'key=choice(a,b,c)'
key=choice(a,b,c)
```

### Other shells
Send a PR to add information about your favorite shell here.
