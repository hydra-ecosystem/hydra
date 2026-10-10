---
id: prepare_for_1_4
title: Preparing for Hydra 1.4
---

Hydra 1.3.5 emits `Hydra14MigrationWarning` when `version_base` is omitted or
set to `"1.1"`. Those are the two cases that select behavior removed by Hydra
1.4.

This page explains how to address that warning. It is not a complete list of
changes in Hydra 1.4; review the
[current breaking changes](/docs/upgrades/1.3_to_1.4/breaking_changes) and the
other pages in this upgrade section for changes relevant to your application.

## Prepare on Hydra 1.3

While the application is still running on Hydra 1.3:

1. Add `version_base="1.3"` to every `@hydra.main()` and Hydra initialization
   call, replacing any existing value.
2. Address all Hydra and OmegaConf deprecation warnings.
3. Run the application tests. If the application needs to run from Hydra's
   output directory, set `hydra.job.chdir=True` explicitly.

Do not remove `version_base` on Hydra 1.3 because omission still selects the
old 1.1 compatibility behavior. Setting it to `"1.3"` only moves away from
that behavior; it does not establish Hydra 1.4 compatibility.

## Test on Hydra 1.4

Hydra 1.4 is in the release candidate phase. Review the
[1.4.0rc1 release notes](https://github.com/hydra-ecosystem/hydra/releases/tag/v1.4.0rc1),
the [OmegaConf 2.4 migration guide](https://omegaconf.cli.dev/docs/migration/2.4),
and the [current breaking changes](/docs/upgrades/1.3_to_1.4/breaking_changes)
before testing. Testing prereleases provides migration feedback; it does not
establish compatibility with the final release.

Install Hydra 1.4 for testing:

```shell
python -m pip install --upgrade --pre "hydra-core>=1.4.0.dev0,<1.5"
```

Using a separate environment is recommended but not required. The upper bound
prevents installation of a later Hydra release. Install matching Hydra 1.4
versions of any launchers or sweepers used by the application. Do not use a
Hydra 1.4 prerelease in production.

When testing on Hydra 1.4, remove `version_base` to eliminate the expected
`Hydra15MigrationWarning`.

Address any failures and review the other pages in this upgrade section for
changes relevant to the application. Passing tests on Hydra 1.3 with
`version_base="1.3"` is not sufficient to establish Hydra 1.4 compatibility.

## Staying on Hydra 1.3

Applications that are not upgrading should pin Hydra to the 1.3 release line:

```text
hydra-core>=1.3,<1.4
```

Configure the warning filter before evaluating `@hydra.main()` or calling a
Hydra initialization API:

```python
import warnings

from hydra.errors import Hydra14MigrationWarning

warnings.filterwarnings("ignore", category=Hydra14MigrationWarning)
```

This does not suppress unrelated warnings.
