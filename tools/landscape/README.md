# Hydra Landscape tools

These tools support discovery, analysis, review, and publication of projects in
the [Hydra Landscape](../../website/docs/landscape.mdx). They do not approve
projects automatically. Inclusion and featured status are maintainer decisions.

The tracked files under this directory are reusable tooling and durable human
decisions. Large crawls, AI output, refreshed GitHub metadata, and generated
review queues remain under `temp/hydra-dependents/`.

Install the Python 3.10 compatibility dependency when needed:

```bash
.venv/bin/pip install -r tools/landscape/requirements.txt
```

`data/decisions.json` is the canonical source for both curation decisions and
the public listing of every included project. Do not edit
`website/src/data/landscape.json` directly; website commands regenerate it from
the decision ledger.

## Pipeline

1. Collect mechanical Hydra usage evidence from the dependency crawl:

   ```bash
   .venv/bin/python tools/landscape/analyze_hydra_usage.py
   ```

2. Route projects for review, optionally using the locally authenticated Codex
   CLI to analyze a resumable batch:

   ```bash
   .venv/bin/python tools/landscape/analyze_hydra_projects.py
   .venv/bin/python tools/landscape/analyze_hydra_projects.py --ai
   ```

   Analyze explicit repositories with repeated `--repo owner/name` arguments.
   The default AI model is `gpt-5.6-terra` with medium reasoning effort.

3. Refresh current GitHub maintenance metadata:

   ```bash
   .venv/bin/python tools/landscape/refresh_landscape_metadata.py
   ```

4. Build the evidence-backed human review queue:

   ```bash
   .venv/bin/python tools/landscape/build_landscape_review.py
   ```

5. Record maintainer decisions in `data/decisions.json`. Every included
   decision must contain its complete public `listing`. A listing may also
   carry an optional `homepage`, which must use HTTPS and must differ from
   `listing.url`; the review queue reports each repository's homepage from
   GitHub metadata so it can be copied in. Regenerate the public data directly
   when needed:

   ```bash
   .venv/bin/python tools/landscape/build_public_landscape.py
   ```

The public generator reads no crawl, AI, review, or live GitHub data. It writes
`website/src/data/landscape.json` deterministically from the decision ledger.
The website's `start`, `build`, and `deploy` commands run it automatically.

## Tests

Run the focused suite with:

```bash
PYTHONPATH=tools/landscape .venv/bin/pytest tools/landscape
```
