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

When an application raises, Hydra sanitizes the traceback: it strips its own
frames from the top and OmegaConf frames from the bottom, so that what remains
points at the application code. That is the right output for someone debugging
their own app, but it hides the framework internals needed to diagnose a bug in
Hydra itself.

For exceptions passing through `instantiate()` during a job, Hydra shows the
application call site and available user target frames while filtering routine
instantiation frames.
Target exceptions retain their original type and any user-created chain.
`InstantiationException` is not compact; other compact configuration errors
continue to show their messages without a traceback.

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
