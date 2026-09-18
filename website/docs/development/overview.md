---
id: overview
title: Developer Guide Overview
---

import GithubLink from "@site/src/components/GithubLink"

This guide assumes you have checked-out the [repository](https://github.com/hydra-ecosystem/hydra).

## Environment setup
Contributor setup instructions are maintained in
<GithubLink to="CONTRIBUTING.md">CONTRIBUTING.md</GithubLink>.

The core Hydra framework supports Python 3.10 through 3.14. You may need to
create additional environments for different Python versions if CI detects
issues on a supported Python version.

## Unsanitized tracebacks

When an application raises, Hydra removes its startup frames before the
application entry point. After that point, it replaces spans of Hydra frames
with a "Hydra frames hidden" marker while retaining application and third-party
frames, including OmegaConf frames. User-created exception chains remain
visible. This output highlights application code but hides Hydra internals that
may be needed to diagnose a framework bug.

This also applies to failures during `instantiate()`: the application call site
and available user target frames remain visible. Target exceptions retain their
original type and chain within the process. Across process boundaries, an
exception that fails a local pickle round-trip becomes a `RuntimeError` naming
its original type; its serialized traceback and chain remain available.
`InstantiationException` is not compact; compact configuration errors before
the application starts still show only their messages.

Set `HYDRA_FULL_ERROR=1` to disable the sanitization and get the complete Hydra
and OmegaConf call stack:

```bash
HYDRA_FULL_ERROR=1 python my_app.py
```

Hydra also skips sanitization automatically when it detects that the process is
running under a debugger.

This is a framework debugging facility rather than a troubleshooting step for
application users, so Hydra does not suggest it after runtime failures. Ask for
it when triaging a bug report that needs the unsanitized traceback.
