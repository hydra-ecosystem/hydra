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

See the [shared Docusaurus maintenance policy](../.github/docusaurus/maintenance.md).
The project directory and audit schedule are configured in
[`.github/docusaurus.json`](../.github/docusaurus.json).
The normal website build owns the security parser checks and Landscape
generation; the dependency audit invokes that build without duplicating them.

### Deployment

Done automatically once a website change is landed to main.


### Adding pages

New pages, e.g., for a new plugin, should be added to `docs/`. They can be accessed on a local server via `http://localhost:9134/docs/page_name`.
