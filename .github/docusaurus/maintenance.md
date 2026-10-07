# Docusaurus dependency maintenance

The shared toolchain is Node 24 and pnpm 11.21.0. Dependency resolution uses a
10-day release delay, restricted dependency sources and explicit dependency-script
approvals. Application dependency versions, site configuration, overrides and
exact security exceptions remain project configuration.

`.github/docusaurus.json` selects the documentation directory. The website owns
its normal `build` script and all build prerequisites; the audit runs that script
without configuring or duplicating the website's build internals.

The dependency audit defaults to January 30 at 02:00 UTC and supports manual
dispatch on the default branch. It attempts security fixes at all severities
before other stable upgrades, performs a frozen installation and production
build, and reports the results in a regular umbrella PR. No report is committed.
Only the project's manifest, lockfile and required pnpm security exceptions enter
that dependency PR. Findings and validation failures remain visible.

Documentation vulnerabilities are accepted between maintenance reviews. Scope
Dependabot update suppression and alert dismissal to this deployment's lockfile;
leave other ecosystems unchanged. Repository permissions and alert-dismissal
rules require separate verification.

Generated dependency commits use `[skip ci]`; the audit's frozen installation
and normal build provide validation. Remove that marker from the squash message
for normal post-merge CI/deployment, or use the existing manual deployment trigger.
Ordinary contributor checks remain enabled. Nothing is merged automatically.

Files under `.github/docusaurus/` and the shared audit workflow are copied
unchanged from the producer. Put project customization in project configuration,
not these files. Verify their hashes and a no-change adoption rerun.
