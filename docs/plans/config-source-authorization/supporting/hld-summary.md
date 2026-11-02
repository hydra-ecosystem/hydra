# Historical HLD approval summary

This summary records the previously accepted HLD
`4aac3ec633f26ff49327e0374f5fdbb96a592815011e90a62d1ee5c2dfa03a48`.
Its API names, opt-outs and next-step statements are historical. Use the current
[overview](../overview.md) and [HLD](../high-level-design.md) for the revised
contract. The text below does not approve those later changes.

## Earlier summary

The [HLD](../high-level-design.md) now incorporates the individually accepted
[API decisions](hld-api-discussion.md). The
[requirements](../requirements.md) have matching revisions. Earlier review
records and approvals remain history. The revised requirements now have a clean
current-agent review in round 4 and have owner acceptance. The HLD's refreshed
current-agent review is also clean in round 2. Whole-HLD approval and any
additional specialist review were separate gates. The owner approved the bounded
DBB challenge; it has now completed clean, with zero findings, and the helper
validated combined durable closeout. The owner then approved the revised HLD
with "Go ahead."; the implementation-plan refresh/review is the next phase.
Nothing is implemented or committed.

## The normal path

Declare a source once. Python `config_path` / `config_search_path`, CLI source
flags, and explicit CLI or Compose `hydra.searchpath` selections add and authorize
sources. Config-selected additions need an existing grant. YAML, dataclass
configs and resulting DictConfig all carry no authority. Config-defined aliases
cannot turn configuration-selected sources into grants. Config loading cannot
expand policy through Hydra's grant-making APIs; registering ConfigStore data
remains allowed. This is not a sandbox for Python import side effects.

```python
@hydra.main(
    config_path="conf",
    config_name="train",
    config_search_path=["pkg://shared.conf"],
)
def app(cfg):
    ...
```

Initialize gets the same optional primary-plus-additional-source interface.
Primary comes first, then additional list order; plugins and CLI ordering retain
existing behavior. Deprecate `initialize_config_search_path()` as an adapter.

## Additional permission

```python
from hydra.authorization import AuthorizationPolicy, LEGACY, replace

policy = AuthorizationPolicy(
    config_sources=["pkg://app.conf"],
    plugins=["joblib", "colorlog"],
    execution_whitelist=replace(["app.Model"]),
)
```

Use this immutable policy as a context or `authorization=` argument on main,
initialize-family methods, or compose. Source grants permit later requests;
they do not add sources. Plugins are identified by entry-point names or explicit
`module:Class`; ambiguous entry-point names fail before import.

Lists add, `replace([...])` replaces one category, and context exit restores.
Omission inherits. An explicit list enables checks under LEGACY. An inherited
execution unsafe opt-out remains active until replaced. Keep existing local
execution APIs; supplying a policy and the old execution argument on one call
is an error with consolidation guidance.
Configuration-driven instantiate cannot call the authorization API, including
through ordinary exact grants or aliases. Trusted Python can use it normally.

CLI plugin grants accept both `--authorize-plugin joblib,colorlog` and repeated
`--authorize-plugin` flags. There is no new config-source flag. Compose needs
no new source-list parameter because its explicit search-path overrides already
activate and authorize. Callers own the trust of inputs they pass as overrides.

## Release behavior and boundaries

1.4 defaults each category to LEGACY with warnings. 1.5 defaults to empty lists
and rejects LEGACY. Explicit declarations and Hydra's built-in setup remain
available. The separate scoped source-unsafe flag and execution unsafe sentinel
remain; source-unsafe use never disables containment or plugin checks.

Plugin authorization precedes imports. Missing-config errors may show skipped
entry-point metadata without claiming which plugin would register that config.
Namespace diagnostics and migration warnings link to the guide. Initializer
contexts restore Hydra-owned registries; workers receive trusted policy before
discovery. Python imports and their normal effects are not rolled back.

Containment is an immediate 1.4 error for filesystem/package escapes, under the
accepted stable-environment assumption. It does not promise a Python sandbox,
installation authenticity, or protection against concurrent file replacement.

The detailed plan is explicitly stale and awaits refreshed upstream approvals.
Package-loader coverage, platform cases, origin tracking and worker integration
remain engineering work. DBB's clean result is HLD-level review, not runtime
security validation. Review sidecars were issued only by the helper; no human
HLD approval is inferred from them.
