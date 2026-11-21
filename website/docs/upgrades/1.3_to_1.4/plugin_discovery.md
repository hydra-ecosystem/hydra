---
id: plugin_discovery
title: Plugin discovery with entry points
---

Hydra 1.4 supports Python package entry points for plugin discovery. The old
`hydra_plugins` namespace scan still works in 1.4, but is deprecated and may
be removed in a later release.

Hydra emits a `FutureWarning` for each plugin class found only through the
namespace scan. The warning names the class and links here. A working entry
point for that same class suppresses the warning, even when the class remains
under `hydra_plugins`. A failed entry point or one that does not load a concrete
plugin class does not count as migration.

Modern setuptools editable installs can make a namespace plugin importable
without making it visible to Hydra's namespace scan. For example,
`import hydra_plugins.my_plugin` can work while `hydra/launcher=my_plugin`
reports that the launcher cannot be found. Entry points avoid that mismatch.

Previously, packaging a plugin under `hydra_plugins` was enough for automatic
discovery. In 1.4, keep the package if you like, but add one `hydra.plugins`
entry point per concrete plugin class. For a setuptools `setup.py`:

Before, discovery relied on the namespace package alone:

```python
from setuptools import find_namespace_packages, setup

setup(packages=find_namespace_packages(include=["hydra_plugins.*"]))
```

After, declare an entry point for each concrete plugin class:

```python
from setuptools import find_namespace_packages, setup

setup(
    packages=find_namespace_packages(include=["hydra_plugins.*"]),
    entry_points={
        "hydra.plugins": [
            "my_launcher = hydra_plugins.my_plugin.launcher:MyLauncher",
        ]
    },
)
```

The entry point imports the class's module, so that module must also import
any code that registers the plugin's Hydra configuration. The class may remain
in `hydra_plugins`; moving it is not required. After changing packaging
metadata, reinstall the plugin. To check discovery, run your application with
`--info plugins` and confirm that your plugin appears.

For an older plugin that has not yet migrated, a temporary editable-install
workaround is:

```shell
pip install -e . --config-settings editable_mode=strict
```

This exposes an enumerable filesystem tree; it is not a substitute for
declaring an entry point. Regular wheel installs of legacy namespace plugins
continue to work in Hydra 1.4. Plugins registered explicitly with
`Plugins.instance().register()` also remain supported, regardless of their
module name.
