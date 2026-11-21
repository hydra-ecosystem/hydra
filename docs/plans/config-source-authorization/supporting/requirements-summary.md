# Requirements summary for approval

This is the exact proposed phase summary. It is not approved merely because it
has been written. The current specification is [requirements](../requirements.md).

- Require authorization for all config sources, including filesystem, package,
  structured, and custom sources, before initialization. Explicit trusted setup
  and dedicated user selections count as grants; ordinary config additions do
  not. Config/group selection within an authorized source needs no further grant.
  R10 requires basic filesystem and package-resource
  containment: allow paths within the selected source
  root, including internal links, and refuse escaping reads/listings. A grant for
  a second root would not permit an escaping link from the first. This assumes a
  trusted, stable filesystem and excludes concurrent replacement protection.
  For archives, the boundary is the selected package's resource subtree, without
  extraction. The owner requires immediate containment errors in Hydra 1.4,
  without a warning-only transition. Unsafe-option interactions need explicit
  HLD treatment; bypassing containment is not implied by source authorization.
- Let framework users supply plain YAML folders and multiple explicitly chosen
  Python-backed sources without editing framework code or installing packages.
  Uninstalled source trees on `PYTHONPATH` remain supported, but importability
  alone is not permission.
- Trusted Python initialization and dedicated user source selections establish
  source permission. Ordinary composed YAML and config overrides, including
  `compose(overrides=...)`, cannot grant it. Keep existing source lookup order.
- Sources added programmatically by an authorized SearchPathPlugin are
  automatically authorized, preserving organization defaults through the existing
  platform activation mechanism. No separate platform activation system is
  required. Ordinary YAML, `hydra/env` selection, and precedence do not themselves
  grant authority for additional sources. Organizations own how they arrange
  trusted startup authorization for their plugins; no organization-specific
  automatic authorization mechanism is included.
- Provide the same boundary for Compose and framework-owned `hydra.main()`.
  Preserve the explicit, default-false Compose caller option
  `unsafe_allow_undeclared_config_sources=True`, scoped to one call and separate
  from target execution authorization.
- Use one authorization object for separate source, plugin, and execution grants,
  as a context manager or explicit policy argument. Grants do not themselves add
  sources. Nested contexts restore prior permissions, including on exceptions.
  Preserve call-specific `instantiate()` grants and local execution contexts,
  including existing additive and explicit-reset semantics, under an entry-point
  policy. Execution-only local changes do not change source or plugin permissions.
  Evolve the existing policy foundation; assess a staged deprecation of the
  execution-only `execution_whitelist()` object rather than maintain two policy
  systems. Names, affected arguments, and release decisions remain open.
- Link diagnostics to a web page explaining source and execution authorization,
  with both CLI and Python migration examples. Design an explicit restricted mode
  and a staged source-authorization compatibility transition. Containment is a
  separate, immediate breaking change in 1.4. No runtime defaults change during
  design authoring.
- Warn when plugins rely on legacy namespace discovery, identify the affected
  plugin, and link to the migration guide. Keep migrated plugins under
  `hydra_plugins` working without that warning. Ensure the guide covers packaging,
  config registration, reinstalling, and verification. No removal release is
  selected here.
- Establish plugin permission before discovery in `hydra.main()` and the
  initialize family, including dedicated framework-user selections. Config
  overrides cannot grant it. Check before imports, including for cached plugins.
  Trusted explicit class registration authorizes that class in its scope without
  importing unrelated plugins; built-in Hydra plugins need no duplicate grants.
- Restore Hydra-owned plugin registry visibility and permissions on context exit,
  exceptions, and failed initialization. Preserve the previous application
  baseline. Python imports and their arbitrary effects cannot be undone.
- Propagate the effective policy through trusted worker/bootstrap state before
  discovery and composition. Job YAML cannot supply grants or broaden access.
- Provide a switch disabling legacy namespace scanning and its imports while
  allowing authorized entry points whose code remains under `hydra_plugins`.
  Its name and compatibility default are HLD decisions. It can become a
  deprecated no-op after namespace scanning is removed.

Propose zero additional interview questions in the initial round, using the
conversation already held. The scope decision above is presented for explicit
approval, not silently accepted. Any later material correction requires renewed
affected review and approval.

Approval permits formal requirements review and, after a clean current review,
HLD authoring. It does not approve the future HLD, implementation plan, commits,
or product implementation.
