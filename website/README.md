# Website

This website is built using Docusaurus 3, a modern static website generator.

### Installation

The website requires Node.js 24 or newer and Python 3.10 or newer. Python runs
the deterministic Hydra Landscape generator before website commands.

```
$ corepack pnpm install
```

pnpm is configured to avoid resolving npm package versions published in the
last 10 days during dependency updates.

### Local Development

```
$ corepack pnpm start
```

This regenerates `src/data/landscape.json` from the canonical Landscape
decisions in `../tools/landscape/data/decisions.json` before starting the
development server. Edit the decisions rather than the generated JSON.

This command starts a local development server and open up a browser window. Most changes are reflected live without having to restart the server.

### Build

```
$ corepack pnpm build
```

The build also regenerates the Landscape data automatically.

This command generates static content into the `build` directory and can be served using any static contents hosting service.

### Dependency maintenance

The pinned pnpm toolchain keeps the 10-day release delay, restricted dependency
sources and explicit dependency-script approvals in `pnpm-workspace.yaml`.
Use `nvm use` in this directory to select the Node 24 lane, and use
`corepack pnpm install --frozen-lockfile` to reproduce the committed dependencies.

Website dependency vulnerabilities at all severities are accepted between
maintenance reviews. This policy applies only to `website/pnpm-lock.yaml`; Python
dependencies and GitHub Actions retain their existing maintenance policy. Routine
website Dependabot update PRs and implicit npm audits are disabled. The explicit
dependency audit still reports all findings.

`dependency-audit.yml` runs January 30 at 02:00 UTC and supports manual dispatch
on the repository's default branch; its schedule can be changed independently.
It attempts compatible security fixes at every severity before stable direct
dependency upgrades, including major versions. Stable upgrades respect the
10-day release delay and retain direct security fixes. The helper preserves
project overrides and workspace policy across commands; security fixes may add
only exact release-age exceptions for versions introduced by that fix.
Failed resolution restores the preceding security proposal. Unavailable audit
or publication metadata remains explicit rather than claiming a clean result.

The workflow installs and builds the proposal, including malformed-image security
checks and the Landscape prebuild. It reports security changes first, other
upgrades, remaining findings and validation failures in the Actions summary and
the body of a regular umbrella PR on `maintenance/dependency-audit`. Full audit
details are collapsed in the PR body. No report is committed. Only the website
manifest, lockfile and pnpm workspace policy enter that PR. The publisher retains
unrelated default-branch changes and refuses publication if dependency inputs
changed since the triggering revision.

Generated dependency commits carry `[skip ci]` to suppress duplicate GitHub
Actions and CircleCI checks; review the audit's frozen install and production
build evidence before merging. Failures remain visible and require human review.
Remove the marker from the squash message for normal post-merge CI/deployment,
or run the existing manual website deployment. Ordinary contributor PR checks
remain enabled. Nothing is merged automatically.

The workflow must be landed before it can run. Verify GitHub Actions is allowed
to create PRs with default token permissions kept read-only, and configure an
enabled Dependabot dismissal rule for npm and `website/pnpm-lock.yaml`, all
severities, both scopes and any fix availability, dismissing indefinitely.
These GitHub settings require separate verification; the Dependabot ignore entry
suppresses update PRs, not alerts. The initial manual audit is a separate step.

### Deployment

Done automatically once a website change is landed to main.


### Adding pages

New pages, e.g., for a new plugin, should be added to `docs/`. They can be accessed on a local server via `http://localhost:9134/docs/page_name`.
