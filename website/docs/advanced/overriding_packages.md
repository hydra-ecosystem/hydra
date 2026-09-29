---
id: overriding_packages
title: Packages
---

The package determines where the content of each input config is placed in the output config.
The default package of an input config is derived from its Config Group. e.g. The default package of `server/db/mysql.yaml` is `server.db`.

The default package can be overridden [in the Defaults List](#overriding-packages-using-the-defaults-list)
or via a [Package Directive](#overriding-the-package-via-the-package-directive) at the top of the config file.
Changing the package of a config can be useful when using a config from another library, or when using the same
config group twice in the same app.

The priority for determining the final package for a config is as follows:
1. The package specified in the Defaults List (relative to the package of the including config)
2. The package specified in the Package Directive (absolute)
3. The default package

We will use the following configs in the examples below:
<div className="row">
<div className="col col--4">

```yaml title="config.yaml"
defaults:
  - server/apache

debug: false



```
</div>

<div className="col col--4">

```yaml title="server/apache.yaml"
defaults:
  - db: mysql

name: apache



```
</div>

<div className="col col--4">

```yaml title="server/db/mysql.yaml"
name: mysql
```

```yaml title="server/db/sqlite.yaml"
name: sqlite
```
</div></div>

```text title="Config directory structure"
├── server
│   ├── db
│   │   ├── mysql.yaml
│   │   └── sqlite.yaml
│   └── apache.yaml
└── config.yaml
```


### An example using only default packages
The default package of *config.yaml* is the global package, of *server/apache.yaml* is *server* and of *server/db/mysql.yaml* is *server.db*.
<div className="row">
<div className="col col--6">

```yaml title="$ python my_app.py" {1-2}
server:
  db:
    name: mysql
  name: apache
debug: false
```
</div></div>

### Overriding packages using the Defaults List
By default, packages specified in the Defaults List are relative to the package of containing config.
As a consequence, overriding a package relocates the entire subtree.

<div className="row">
<div className="col col--4">

```yaml title="config.yaml" {2}
defaults:
  - server/apache@admin

debug: false

```
</div>
<div className="col col--4">

```yaml title="server/apache.yaml" {2}
defaults:
 - db@backup: mysql

name: apache

```
</div>
<div className="col col--4">

```yaml title="Output config" {1-4}
admin:
  backup:
    name: mysql
  name: apache
debug: false
```
</div></div>

Note that content of *server/apache.yaml* is relocated to *admin*
and the content of *server/db/mysql.yaml* to *admin.backup*.

#### Default List package keywords
We will use this example, replacing *\<\@PACKAGE>* to demonstrate different cases:
```yaml title="config_group/config.yaml"
defaults:
  - /server/db<@PACKAGE>: mysql
```

Without a package override, the resulting package is `config_group.server.db`.
With the **@\_here\_** keyword, the resulting package is the same as the containing config (`config_group`).
With **@\_global\_**, the resulting package is the global package. Anything following \_global\_ is absolute; for example, **@\_global\_.foo** becomes `foo`.

### Overriding the package via the package directive

The @package directive changes the package of a config file. The package specified by a @package directive is always absolute.

```yaml title="server/db/mysql.yaml" {1}
# @package foo.bar
name: mysql
```

To change the package to the global (empty) package, use the keyword `_global_`.

### Using a config group more than once
The following example adds the `server/db/mysql` config in the packages `src` and `dst`.

<div className="row">
<div className="col col--6">

```yaml title="config.yaml"
defaults:
 - server/db@src: mysql
 - server/db@dst: mysql

```
</div><div className="col  col--6">

```yaml title="$ python my_app.py"
src:
  name: mysql
dst:
  name: mysql
```
</div></div>

When overriding config groups with a non-default package, the package must be used:
```yaml title="$ python my_app.py server/db@src=sqlite"
src:
  name: sqlite
dst:
  name: mysql
```
