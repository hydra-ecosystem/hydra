# Contributing to hydra
We want to make contributing to this project as easy and transparent as
possible.

Please see the [developer guide](https://hydra.cc/docs/development/overview/) on the website.
Maintainers can find the release process in the [release guide](website/docs/development/release.md).

## Development Environment

Use a project-local virtual environment at `.venv` for Hydra development:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements/dev.txt
pip install -e .
```

The core Hydra framework supports multiple Python versions. Use additional
environments when you need to reproduce or validate behavior on a specific
supported Python version, but keep the default local checkout environment in
`.venv`.

## Pull Requests
Please open an issue and get maintainer agreement before starting substantial
work. Only open a PR once a maintainer has agreed that the change is wanted,
and link to that discussion in your PR.

1. Fork the repo and create your feature branch from `main`.
2. If you've added code add suitable tests.
3. If you've changed APIs, update the documentation.
4. Ensure the test suite and lint pass.
5. Review the Contributor License Agreement ("CLA") transition note below.

## News fragments

All non-trivial user-visible changes should include a news fragment.

Use the issue or pull request number as the filename, with one of these
extensions:

- `api_change`: API changes, renames, deprecations, and removals
- `feature`: new features
- `bugfix`: bug fixes
- `docs`: documentation additions or updates
- `config`: configuration structure changes
- `maintenance`: maintainability improvements

For Hydra core changes, place the fragment in `news/`, for example
`news/1234.bugfix`. For plugin changes, place it in the relevant plugin's
`news/` directory, for example
`plugins/hydra_optuna_sweeper/news/1234.feature`.

Pull requests can span multiple categories by creating multiple fragments. For
example, if a pull request adds a feature and deprecates an old feature at the
same time, create both `news/1234.feature` and `news/1234.api_change`.
Likewise, if a pull request touches multiple issues or pull requests, you may
create one fragment for each number with the same contents; the release tooling
deduplicates them when rendering release notes.

Keep the fragment concise and user-facing. Prefer sentence case, under 80
characters, and imperative tone. A fragment should complete the sentence "This
change will ...". You do not need to mention issue or pull request numbers in
the fragment text; the release tooling adds references when rendering release
notes.

## Copyright headers

New first-party source files must use this header, adapted to the file's comment
syntax:

```text
SPDX-FileCopyrightText: Contributors to Hydra
SPDX-License-Identifier: MIT
```

Do not use a Facebook or Meta notice as Hydra's copyright notice on a new
first-party file. Existing copyright notices must be preserved when modifying a
file. Files copied or derived from another project must retain all notices
required by their source license. Generated, vendored, and otherwise externally
licensed files are exempt from Hydra's new-file header but remain subject to
their applicable licenses and notices. When adding an exempt Python file outside
an already excluded tree, add its narrowest stable path to `EXCLUDED_PREFIXES`
in `tools/copyright/check_new_files.py` in the same change.

CI enforces this policy for newly added Python files. Other first-party source
files are checked during review.

## Contributor License Agreement ("CLA")
Hydra requires contributors to accept the
[Hydra Individual Contributor License Agreement](https://hydra.cc/legal/individual-cla/)
before their contributions can be accepted. CLA Assistant checks pull requests
and provides a signing link when a signature is required.

Before signing, make sure that you have the right to grant the rights in the
agreement. Employment alone does not automatically require an Entity CLA, but
you must obtain any approval or waiver required by your employment or other
obligations. If your employer wants to contribute to Hydra as an entity,
contact [cla@hydra.cc](mailto:cla@hydra.cc). Entity CLAs are handled
manually and are not signed through CLA Assistant.

## Issues
We use GitHub issues to track public bugs. Please ensure your description is
clear and has sufficient instructions to be able to reproduce the issue.

## Security

Report security vulnerabilities privately through
[GitHub Security Advisories](https://github.com/hydra-ecosystem/hydra/security/advisories/new).
Do not file a public issue or pull request for a suspected security vulnerability.

Hydra will request CVEs for vulnerabilities assessed as Medium severity or higher.
Low-severity vulnerabilities may be fixed and documented in a security advisory
without requesting a CVE.

## License
By contributing to hydra, you agree that your contributions will be licensed
under the LICENSE file in the root directory of this source tree.
