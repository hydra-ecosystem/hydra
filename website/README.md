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

Website dependency vulnerabilities at all severities are accepted between annual
reviews. This policy applies only to `website/pnpm-lock.yaml`; Python dependencies
and GitHub Actions retain their existing maintenance policy. Routine website
Dependabot update PRs and implicit npm audits are disabled. The explicit annual
pnpm audit still reports all findings.

`annual-npm-audit.yml` runs January 30 at 02:00 UTC and supports manual
dispatch on the repository's default branch.
It attempts security fixes before stable direct dependency upgrades, preserves
project overrides and policy, then installs and builds the proposal with the
Landscape prebuild. It reports remaining findings and failures in the Actions
summary and a regular umbrella PR on `maintenance/annual-website-dependencies`.
Only the website manifest, lockfile and pnpm workspace policy enter that PR.
Review compatibility and run normal PR validation before merging.

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
