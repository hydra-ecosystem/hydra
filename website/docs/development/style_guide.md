---
id: style_guide
title: Style Guide
sidebar_label: Style Guide
---

The code needs to pass verification by the following tools:
 - `ruff format .` : Automatic code formatting for Python
 - `ruff check .` : Python linting, copyright verification, and import sorting
 - `pyrefly check` : Ensures code passes static type checking
 - `yamllint .` : Ensures that yaml files are syntactically correct and properly indented.

The easiest way to run the required verifications is:
 - `nox -s lint` : for everything
 - `nox -t lint-core` : for the Hydra core
 - `nox -t lint-plugins` : for the included plugins

All three share the same environments: the `lint` session is parametrized over
Hydra core and each plugin, and the `lint-core` / `lint-plugins` tags select a subset
of it. To lint a single plugin, combine the session with `PLUGINS`:
```
$ PLUGINS=hydra_ray_launcher nox -t lint-plugins
```

Use the `FIX` environment variable to automatically format code and apply safe lint fixes:
```
$ FIX=1 nox -t lint-plugins
```

### Cleaning up stale Nox environments

Nox creates one virtualenv under `.nox/` per session, Python version and parameter, and
never deletes them. Environments are left behind when a session is renamed (for example
the former `lint-core`, `lint-plugins` and `lint_plugins` sessions) or when a Python version
is dropped from the test matrix, and they can add up to tens of gigabytes.

To see which environments the current noxfile would use, list the sessions:
```
$ nox --list
```
Any directory under `.nox/` that does not correspond to one of the listed sessions is stale.
Common examples are directories starting with `lint-core-`, `lint-plugins-` or `lint_plugins-`,
and directories for Python versions that are no longer in `DEFAULT_PYTHON_VERSIONS`.

To see how much space each environment uses:
```
# Linux / macOS
$ du -sh .nox/* | sort -h

# Windows (PowerShell)
> Get-ChildItem .nox -Directory | ForEach-Object { "{0,8:N0} MB  {1}" -f ((Get-ChildItem $_.FullName -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), $_.Name }
```

Remove stale environments individually, for example:
```
$ rm -rf .nox/lint-core-* .nox/lint-plugins-* .nox/lint_plugins-*
```
Deleting the whole `.nox` directory is always safe, but Nox will recreate every environment
the next time the full suite runs.

It is also recommended that you install pre-commit hooks (use `pre-commit install`).
pre-commit will execute some of the above tests when you commit your code locally. 
You can disable it by appending `-n` to your commit command: `git commit -m wip -n`

Pull requests that do not lint will fail the automated testing.
