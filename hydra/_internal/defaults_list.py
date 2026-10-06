# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

import copy
from dataclasses import dataclass, field
from textwrap import dedent
from typing import Callable

from omegaconf import OmegaConf

from hydra import MissingConfigException
from hydra._internal.config_repository import IConfigRepository
from hydra.core.config_store import ConfigStore
from hydra.core.default_element import (
    ConfigDefault,
    DefaultsTreeNode,
    GroupDefault,
    InputDefault,
    ResultDefault,
    VirtualRoot,
)
from hydra.core.object_type import ObjectType
from hydra.core.override_parser.types import Override
from hydra.errors import ConfigCompositionException

cs = ConfigStore.instance()

cs.store(name="_dummy_empty_config_", node={}, provider="hydra")


@dataclass
class Deletion:
    name: str | None
    used: bool = field(default=False, compare=False)


@dataclass
class OverrideMetadata:
    external_override: bool
    containing_config_path: str | None = None
    used: bool = False
    relative_key: str | None = None


@dataclass
class Overrides:
    override_choices: dict[str, str | list[str] | None]
    override_metadata: dict[str, OverrideMetadata]

    append_group_defaults: list[GroupDefault]
    config_overrides: list[Override]

    known_choices: dict[str, str | None]
    known_choice_origins: dict[str, str | None]
    known_choices_per_group: dict[str, set[str]]

    deletions: dict[str, Deletion]

    def __init__(self, repo: IConfigRepository, overrides_list: list[Override]) -> None:
        self.override_choices = {}
        self.override_metadata = {}
        self.append_group_defaults = []
        self.config_overrides = []
        self.deletions = {}

        self.known_choices = {}
        self.known_choice_origins = {}
        self.known_choices_per_group = {}

        for override in overrides_list:
            if override.is_sweep_override():
                continue
            if override.is_value_path:
                self.config_overrides.append(override)
                continue
            is_group = repo.group_exists(override.key_or_group)
            is_config = repo.config_exists(override.key_or_group)
            value = override.value()
            is_dict = isinstance(override.value(), dict)
            if override.is_delete() and (is_group or is_config):
                key = override.get_key_element()[1:]
                if is_group:
                    if value is not None and not isinstance(value, str):
                        raise ValueError(
                            f"Config group override deletion value must be a string : {override}"
                        )
                    self.deletions[key] = Deletion(name=value)
                else:
                    if value is not None:
                        raise ValueError(
                            f"Config path deletion does not support a value : {override}"
                        )
                    self.deletions[key] = Deletion(name=None)
            elif is_dict or not is_group:
                self.config_overrides.append(override)
            elif override.is_force_add():
                # This could probably be made to work if there is a compelling use case.
                raise ConfigCompositionException(
                    f"force-add of config groups is not supported: '{override.input_line}'"
                )
            elif not isinstance(value, (str, list)):
                raise ValueError(
                    f"Config group override must be a string or a list. Got {type(value).__name__}"
                )
            elif override.is_add():
                self.append_group_defaults.append(
                    GroupDefault(
                        group=override.key_or_group,
                        package=override.package,
                        value=value,
                        external_append=True,
                    )
                )
            else:
                key = override.get_key_element()
                self.override_choices[key] = value
                self.override_metadata[key] = OverrideMetadata(external_override=True)

    def add_override(self, parent_config_path: str, default: GroupDefault) -> None:
        assert default.override
        key = default.get_override_key()
        # Called during the reverse traversal of the defaults tree, so the first
        # override registered for a key is the last one in depth first order and
        # first-wins keeps it. External (command line) overrides are registered in
        # __init__, before the traversal, and therefore always take priority.
        if key not in self.override_choices:
            self.override_choices[key] = default.value
            self.override_metadata[key] = OverrideMetadata(
                external_override=False,
                containing_config_path=parent_config_path,
                relative_key=default.get_relative_override_key(),
            )

    def is_overridden(
        self,
        default: InputDefault,
        eligible_override_keys: set[str] | None = None,
    ) -> bool:
        if isinstance(default, GroupDefault):
            key = default.get_override_key()
            return key in self.override_choices and (
                eligible_override_keys is None or key in eligible_override_keys
            )

        return False

    def override_default_option(self, default: GroupDefault) -> None:
        key = default.get_override_key()
        if key in self.override_choices:
            if isinstance(default, GroupDefault):
                default.value = self.override_choices[key]
            default.config_name_overridden = True
            self.override_metadata[key].used = True

    def ensure_overrides_used(self) -> None:
        for key, meta in self.override_metadata.items():
            if not meta.used:
                if not meta.external_override:
                    # A Defaults List override must target a Group Default that
                    # precedes it in the effective depth-first Defaults List.
                    # Later entries, such as command line appends, are not
                    # eligible targets and are not suggested as candidates.
                    value = self.override_choices[key]
                    msg = (
                        f"Invalid Defaults List override '{meta.relative_key}: {value}'."
                        f"\nNo earlier Group Default for '{key}' exists to override."
                    )
                    if meta.containing_config_path is not None:
                        msg = f"In '{meta.containing_config_path}': {msg}"
                    raise ConfigCompositionException(msg)

                group = key.split("@")[0]
                choices = (
                    self.known_choices_per_group[group]
                    if group in self.known_choices_per_group
                    else set()
                )

                if len(choices) > 1:
                    msg = (
                        f"Could not override '{key}'."
                        f"\nDid you mean to override one of {', '.join(sorted(list(choices)))}?"
                    )
                elif len(choices) == 1:
                    msg = (
                        f"Could not override '{key}'."
                        f"\nDid you mean to override {copy.copy(choices).pop()}?"
                    )
                elif len(choices) == 0:
                    msg = f"Could not override '{key}'. No match in the defaults list."
                else:
                    assert False

                if meta.containing_config_path is not None:
                    msg = f"In '{meta.containing_config_path}': {msg}"

                if meta.external_override:
                    msg += f"\nTo append to your default list use +{key}={self.override_choices[key]}"

                raise ConfigCompositionException(msg)

    def ensure_deletions_used(self) -> None:
        for key, deletion in self.deletions.items():
            if not deletion.used:
                desc = f"{key}={deletion.name}" if deletion.name is not None else key
                msg = f"Could not delete '{desc}'. No match in the defaults list"
                raise ConfigCompositionException(msg)

    def set_known_choice(
        self, default: InputDefault, containing_config_path: str | None
    ) -> None:
        if isinstance(default, GroupDefault):
            key = default.get_override_key()
            origin = (
                "command line"
                if default.is_external_append()
                else containing_config_path
            )
            if key not in self.known_choices:
                self.known_choices[key] = default.get_name()
                self.known_choice_origins[key] = origin
            else:
                prev = self.known_choices[key]
                if default.get_name() != prev:
                    previous_origin = self.known_choice_origins[key]
                    previous_choice = f"'{prev}'"
                    current_choice = f"'{default.get_name()}'"
                    if previous_origin is not None:
                        previous_choice += f" from '{previous_origin}'"
                    if origin is not None:
                        current_choice += f" from '{origin}'"
                    raise ConfigCompositionException(
                        f"Multiple values for {key}."
                        f" To override a value use 'override {key}: {prev}'"
                        f"\nConflicting choices: {previous_choice} and {current_choice}"
                    )

            group = default.get_group_path()
            if group not in self.known_choices_per_group:
                self.known_choices_per_group[group] = set()
            self.known_choices_per_group[group].add(key)

    def is_deleted(self, default: InputDefault) -> bool:
        if isinstance(default, GroupDefault):
            key = default.get_override_key()
            if key in self.deletions:
                deletion = self.deletions[key]
                if deletion.name is None:
                    return True
                else:
                    return deletion.name == default.get_name()
        elif isinstance(default, ConfigDefault):
            key = default.get_config_path()
            if key in self.deletions:
                return self.deletions[key].name is None
        return False

    def delete(self, default: InputDefault) -> None:
        if isinstance(default, GroupDefault):
            default.deleted = True
            key = default.get_override_key()
        else:
            assert isinstance(default, ConfigDefault)
            default.deleted = True
            key = default.get_config_path()
        self.deletions[key].used = True


@dataclass
class DefaultsList:
    defaults: list[ResultDefault]
    defaults_tree: DefaultsTreeNode
    config_overrides: list[Override]
    overrides: Overrides


def _validate_self(
    containing_node: InputDefault,
    defaults: list[InputDefault],
) -> bool:
    # check that self is present only once
    has_self = False
    has_non_override = False
    for d in defaults:
        if not d.is_override():
            has_non_override = True
        if d.is_self():
            if has_self:
                raise ConfigCompositionException(
                    f"Duplicate _self_ defined in {containing_node.get_config_path()}"
                )
            has_self = True

    if not has_self and has_non_override or len(defaults) == 0:
        defaults.append(ConfigDefault(path="_self_"))

    return not has_self


def update_package_header(repo: IConfigRepository, node: InputDefault) -> None:
    if node.is_missing():
        return
    # This loads the same config loaded in _create_defaults_tree
    # To avoid loading it twice, the repo implementation is expected to cache loaded configs
    loaded = repo.load_config(config_path=node.get_config_path())
    if loaded is not None:
        node.set_package_header(loaded.header["package"])


def _expand_virtual_root(
    repo: IConfigRepository,
    root: DefaultsTreeNode,
    overrides: Overrides,
    skip_missing: bool,
    deferred_interpolation_override_keys: dict[int, set[str]],
) -> DefaultsTreeNode:
    children: list[DefaultsTreeNode | InputDefault] = []
    assert root.children is not None
    for d in reversed(root.children):
        assert isinstance(d, InputDefault)
        new_root = DefaultsTreeNode(node=d, parent=root)
        d.update_parent("", "")

        subtree = _create_defaults_tree_impl(
            repo=repo,
            root=new_root,
            is_root_config=d.primary,
            skip_missing=skip_missing,
            interpolated_subtree=False,
            overrides=overrides,
            deferred_interpolation_override_keys=deferred_interpolation_override_keys,
        )
        if subtree.children is None:
            children.append(d)
        else:
            children.append(subtree)

    if len(children) > 0:
        root.children = list(reversed(children))

    return root


def _check_not_missing(
    repo: IConfigRepository,
    default: InputDefault,
    skip_missing: bool,
    containing_config_path: str | None,
) -> bool:
    path = default.get_config_path()
    if default.is_missing():
        if skip_missing:
            return True
        if isinstance(default, GroupDefault):
            group_path = default.get_group_path()
            override_key = default.get_override_key()
            options = repo.get_group_options(
                group_path,
                results_filter=ObjectType.CONFIG,
            )
            opt_list = "\n".join("\t" + x for x in options)
            msg = dedent(f"""\
                You must specify '{override_key}', e.g, {override_key}=<OPTION>
                Available options:
                """)
            if containing_config_path is not None:
                msg = f"In '{containing_config_path}': {msg}"
            raise ConfigCompositionException(msg + opt_list)
        elif isinstance(default, ConfigDefault):
            raise ValueError(f"Missing ConfigDefault is not supported : {path}")
        else:
            assert False

    return False


def _create_defaults_tree(
    repo: IConfigRepository,
    root: DefaultsTreeNode,
    is_root_config: bool,
    skip_missing: bool,
    interpolated_subtree: bool,
    overrides: Overrides,
) -> DefaultsTreeNode:
    deferred_interpolation_override_keys: dict[int, set[str]] = {}
    ret = _create_defaults_tree_impl(
        repo=repo,
        root=root,
        is_root_config=is_root_config,
        skip_missing=skip_missing,
        interpolated_subtree=interpolated_subtree,
        overrides=overrides,
        deferred_interpolation_override_keys=deferred_interpolation_override_keys,
    )

    if is_root_config:
        _resolve_deferred_interpolations(
            repo=repo,
            root=ret,
            skip_missing=skip_missing,
            overrides=overrides,
            deferred_interpolation_override_keys=deferred_interpolation_override_keys,
        )

    return ret


def _resolve_deferred_interpolations(
    repo: IConfigRepository,
    root: DefaultsTreeNode,
    skip_missing: bool,
    overrides: Overrides,
    deferred_interpolation_override_keys: dict[int, set[str]],
) -> None:
    """Expand interpolated defaults after the non-interpolated tree is known."""

    def resolve_one(tree: DefaultsTreeNode) -> bool:
        if tree.children is None:
            return False

        for index, child in enumerate(tree.children):
            if isinstance(child, DefaultsTreeNode):
                if resolve_one(child):
                    return True
                continue

            if not child.is_interpolation():
                continue

            candidate = copy.deepcopy(child)
            try:
                candidate.resolve_interpolation(
                    OmegaConf.create(overrides.known_choices)
                )
            except ConfigCompositionException:
                # Another deferred subtree may provide the missing choice.
                continue

            _validate_paths(candidate, tree.node)
            candidate.update_parent(
                tree.node.get_group_path(),
                tree.node.get_final_package(),
            )
            eligible_override_keys = deferred_interpolation_override_keys.pop(id(child))
            subtree = DefaultsTreeNode(node=candidate, parent=tree)
            subtree = _create_defaults_tree_impl(
                repo=repo,
                root=subtree,
                is_root_config=False,
                skip_missing=skip_missing,
                interpolated_subtree=True,
                overrides=overrides,
                deferred_interpolation_override_keys=deferred_interpolation_override_keys,
                eligible_override_keys=eligible_override_keys,
            )
            tree.children[index] = (
                subtree if subtree.children is not None else subtree.node
            )
            return True

        return False

    while resolve_one(root):
        pass

    def fail_on_unresolved(tree: DefaultsTreeNode) -> None:
        if tree.children is None:
            return

        for child in tree.children:
            if isinstance(child, DefaultsTreeNode):
                fail_on_unresolved(child)
            elif child.is_interpolation():
                child.resolve_interpolation(OmegaConf.create(overrides.known_choices))
                raise AssertionError("Deferred interpolation unexpectedly resolved")

    fail_on_unresolved(root)


def _validate_paths(default: InputDefault, parent: InputDefault) -> None:
    if isinstance(default, ConfigDefault):
        assert default.path is not None
        paths = [("config", default.path)]
    elif isinstance(default, GroupDefault):
        assert default.group is not None
        paths = [("config group", default.group)]
        if default.is_name():
            name = default.get_name()
            if name is not None:
                paths.append(("config option", name))
        else:
            paths.extend(("config option", option) for option in default.get_options())
    else:
        return

    for path_type, path in paths:
        # Check for backslashes before parent traversal: the traversal check
        # splits on '/', so a path like '..\secret' would otherwise slip through
        # as a single segment and reach operating-system path handling, where
        # Windows interprets '\' as a separator but POSIX and ConfigStore do not.
        if "\\" in path:
            location = ""
            if not parent.is_virtual():
                location = f"In {parent.get_config_path()}: "
            raise ConfigCompositionException(
                f"{location}Backslash ('\\') in Defaults List "
                f"{path_type} paths is not supported ('{path}').\n"
                "Use '/' as the config group separator; it is the only "
                "supported separator, regardless of the operating system.\n"
                "See https://hydra.cc/docs/advanced/defaults_list/ for more "
                "information."
            )
        if ".." not in path.split("/"):
            continue

        guidance = {
            "config": "Use an absolute config path instead, such as '/group/config'.",
            "config group": (
                "Use an absolute config group path instead, such as '/group: option'."
            ),
            "config option": (
                "Config options cannot contain parent traversal. Select the target "
                "config directly. Use '/config' or '/group: option' in a Defaults "
                "List, or 'group=option' (with '+' when adding a new default) on the "
                "command line."
            ),
        }[path_type]
        location = ""
        if not parent.is_virtual():
            location = f"In {parent.get_config_path()}: "
        raise ConfigCompositionException(
            f"{location}Parent traversal ('..') in Defaults List "
            f"{path_type} paths is not supported ('{path}').\n"
            f"{guidance}\n"
            "See https://hydra.cc/docs/advanced/defaults_list/ for more "
            "information."
        )


def _update_overrides(
    defaults_list: list[InputDefault],
    overrides: Overrides,
    parent: InputDefault,
    interpolated_subtree: bool,
) -> None:
    seen_override = False
    last_override_seen = None
    for d in defaults_list:
        if d.is_self():
            continue
        d.update_parent(parent.get_group_path(), parent.get_final_package())

        if seen_override and not (d.is_override() or d.is_external_append()):
            assert isinstance(last_override_seen, GroupDefault)
            pcp = parent.get_config_path()
            okey = last_override_seen.get_override_key()
            oval = last_override_seen.get_name()
            dvalue = (
                d.get_options()
                if isinstance(d, GroupDefault) and d.is_options()
                else d.get_name()
            )
            raise ConfigCompositionException(
                dedent(f"""\
                    In {pcp}: Override '{okey} : {oval}' is defined before '{d.get_override_key()}: {dvalue}'.
                    Overrides must be at the end of the defaults list""")
            )

        if isinstance(d, GroupDefault):
            if d.override:
                seen_override = True
                last_override_seen = d
                if interpolated_subtree:
                    # Since interpolations are deferred for until all the config groups are already set,
                    # Their subtree may not contain config group overrides
                    raise ConfigCompositionException(
                        dedent(f"""\
                            {parent.get_config_path()}: Default List Overrides are not allowed in the subtree
                            of an in interpolated config group (override {d.get_override_key()}={d.get_name()}).
                            """)
                    )
                # Overrides are registered when they are encountered during the
                # reverse traversal in _create_defaults_tree_impl, not here, so
                # that the last override in depth first order wins.


def _create_defaults_tree_impl(
    repo: IConfigRepository,
    root: DefaultsTreeNode,
    is_root_config: bool,
    skip_missing: bool,
    interpolated_subtree: bool,
    overrides: Overrides,
    deferred_interpolation_override_keys: dict[int, set[str]],
    eligible_override_keys: set[str] | None = None,
) -> DefaultsTreeNode:
    parent = root.node
    children: list[InputDefault | DefaultsTreeNode] = []
    if parent.is_virtual():
        if is_root_config:
            return _expand_virtual_root(
                repo,
                root,
                overrides,
                skip_missing,
                deferred_interpolation_override_keys,
            )
        else:
            return root

    if is_root_config:
        root.node.update_parent("", "")
        if not repo.config_exists(root.node.get_config_path()):
            config_not_found_error(repo=repo, tree=root)

    update_package_header(repo=repo, node=parent)

    if overrides.is_deleted(parent):
        overrides.delete(parent)
        return root

    containing_config = root.parent_node()
    containing_config_path = (
        containing_config.get_config_path()
        if containing_config is not None and not containing_config.is_virtual()
        else None
    )
    overrides.set_known_choice(parent, containing_config_path)

    if parent.get_name() is None:
        return root

    if _check_not_missing(
        repo=repo,
        default=parent,
        skip_missing=skip_missing,
        containing_config_path=(
            None if parent.is_external_append() else containing_config_path
        ),
    ):
        return root

    path = parent.get_config_path()
    loaded = repo.load_config(config_path=path)

    if loaded is None:
        if parent.is_optional():
            assert isinstance(parent, (GroupDefault, ConfigDefault))
            parent.deleted = True
            return root
        config_not_found_error(repo=repo, tree=root)

    assert loaded is not None
    defaults_list = copy.deepcopy(loaded.defaults_list)
    if defaults_list is None:
        defaults_list = []

    if (
        len(defaults_list) > 0
        or is_root_config
        and len(overrides.append_group_defaults) > 0
    ):
        _validate_self(containing_node=parent, defaults=defaults_list)

    if is_root_config:
        defaults_list.extend(overrides.append_group_defaults)

    for d in defaults_list:
        _validate_paths(d, parent)

    _update_overrides(defaults_list, overrides, parent, interpolated_subtree)

    def add_child(
        child_list: list[InputDefault | DefaultsTreeNode],
        new_root_: DefaultsTreeNode,
    ) -> None:
        subtree_ = _create_defaults_tree_impl(
            repo=repo,
            root=new_root_,
            is_root_config=False,
            interpolated_subtree=interpolated_subtree,
            skip_missing=skip_missing,
            overrides=overrides,
            deferred_interpolation_override_keys=deferred_interpolation_override_keys,
            eligible_override_keys=eligible_override_keys,
        )
        if subtree_.children is None:
            child_list.append(new_root_.node)
        else:
            child_list.append(subtree_)

    for d in reversed(defaults_list):
        if d.is_self():
            d.update_parent(root.node.parent_base_dir, root.node.get_package())
            children.append(d)
        else:
            if d.is_override():
                assert isinstance(d, GroupDefault)
                overrides.add_override(parent.get_config_path(), d)
                continue

            d.update_parent(parent.get_group_path(), parent.get_final_package())

            if overrides.is_overridden(d, eligible_override_keys):
                assert isinstance(d, GroupDefault)
                overrides.override_default_option(d)

            _validate_paths(d, parent)

            if isinstance(d, GroupDefault) and d.is_options():
                # overriding may change from options to name
                for item in reversed(d.get_options()):
                    if "${" in item:
                        raise ConfigCompositionException(
                            f"In '{path}': Defaults List interpolation is not supported in options list items"
                        )

                    assert d.group is not None
                    if d.is_external_append():
                        node = ConfigDefault(
                            path=f"{d.get_group_path()}/{item}",
                            package=d.package,
                            optional=d.is_optional(),
                        )
                        # External appends are already absolute in Hydra's config namespace.
                        node.update_parent("", "")
                    else:
                        node = ConfigDefault(
                            path=f"{d.group}/{item}",
                            package=d.package,
                            optional=d.is_optional(),
                        )
                        node.update_parent(
                            parent.get_group_path(), parent.get_final_package()
                        )
                    new_root = DefaultsTreeNode(node=node, parent=root)
                    add_child(children, new_root)

            else:
                if d.is_interpolation():
                    # Preserve which overrides are eligible at this point in
                    # the reverse depth-first traversal.
                    keys = (
                        overrides.override_choices.keys()
                        if eligible_override_keys is None
                        else eligible_override_keys
                    )
                    deferred_interpolation_override_keys[id(d)] = set(keys)
                    children.append(d)
                    continue

                new_root = DefaultsTreeNode(node=d, parent=root)
                add_child(children, new_root)

    if len(children) > 0:
        root.children = list(reversed(children))

    return root


def _create_result_default(
    tree: DefaultsTreeNode | None, node: InputDefault
) -> ResultDefault | None:
    if node.is_virtual():
        return None
    if node.get_name() is None:
        return None

    res = ResultDefault()

    if node.is_self():
        assert tree is not None
        res.config_path = tree.node.get_config_path()
        res.is_self = True
        pn = tree.parent_node()
        if pn is not None:
            res.parent = pn.get_config_path()
        else:
            res.parent = None
        res.package = tree.node.get_final_package()
        res.primary = tree.node.primary
    else:
        res.config_path = node.get_config_path()
        if tree is not None:
            res.parent = tree.node.get_config_path()
        res.package = node.get_final_package()
        if isinstance(node, GroupDefault):
            res.override_key = node.get_override_key()
        res.primary = node.primary

    if res.config_path == "_dummy_empty_config_":
        return None

    return res


def _dfs_walk(
    tree: DefaultsTreeNode,
    operator: Callable[[DefaultsTreeNode | None, InputDefault], None],
) -> None:
    if tree.children is None or len(tree.children) == 0:
        operator(tree.parent, tree.node)
    else:
        for child in tree.children:
            if isinstance(child, InputDefault):
                operator(tree, child)
            else:
                assert isinstance(child, DefaultsTreeNode)
                _dfs_walk(tree=child, operator=operator)


def _tree_to_list(
    tree: DefaultsTreeNode,
) -> list[ResultDefault]:
    class Collector:
        def __init__(self) -> None:
            self.output: list[ResultDefault] = []

        def __call__(
            self, tree_node: DefaultsTreeNode | None, node: InputDefault
        ) -> None:
            if node.is_deleted():
                return

            if node.is_missing():
                return

            rd = _create_result_default(tree=tree_node, node=node)
            if rd is not None:
                self.output.append(rd)

    visitor = Collector()
    _dfs_walk(tree, visitor)
    return visitor.output


def _create_root(config_name: str | None, with_hydra: bool) -> DefaultsTreeNode:
    primary: InputDefault
    if config_name is None:
        primary = ConfigDefault(path="_dummy_empty_config_", primary=True)
    else:
        primary = ConfigDefault(path=config_name, primary=True)

    if with_hydra:
        root = DefaultsTreeNode(
            node=VirtualRoot(),
            children=[ConfigDefault(path="hydra/config"), primary],
        )
    else:
        root = DefaultsTreeNode(node=primary)
    return root


def ensure_no_duplicates_in_list(result: list[ResultDefault]) -> None:
    keys = set()
    for item in result:
        if not item.is_self:
            key = item.override_key
            if key is not None:
                if key in keys:
                    raise ConfigCompositionException(
                        f"{key} appears more than once in the final defaults list"
                    )
                keys.add(key)


def _create_defaults_list(
    repo: IConfigRepository,
    config_name: str | None,
    overrides: Overrides,
    prepend_hydra: bool,
    skip_missing: bool,
) -> tuple[list[ResultDefault], DefaultsTreeNode]:
    root = _create_root(config_name=config_name, with_hydra=prepend_hydra)

    defaults_tree = _create_defaults_tree(
        repo=repo,
        root=root,
        overrides=overrides,
        is_root_config=True,
        interpolated_subtree=False,
        skip_missing=skip_missing,
    )

    output = _tree_to_list(tree=defaults_tree)
    ensure_no_duplicates_in_list(output)
    return output, defaults_tree


def create_defaults_list(
    repo: IConfigRepository,
    config_name: str | None,
    overrides_list: list[Override],
    prepend_hydra: bool,
    skip_missing: bool,
) -> DefaultsList:
    """
    :param repo:
    :param config_name:
    :param overrides_list:
    :param prepend_hydra:
    :param skip_missing: True to skip config group with the value '???' and not fail on them. Useful when sweeping.
    :return:
    """
    overrides = Overrides(repo=repo, overrides_list=overrides_list)
    defaults, tree = _create_defaults_list(
        repo,
        config_name,
        overrides,
        prepend_hydra=prepend_hydra,
        skip_missing=skip_missing,
    )
    overrides.ensure_overrides_used()
    overrides.ensure_deletions_used()
    return DefaultsList(
        defaults=defaults,
        config_overrides=overrides.config_overrides,
        defaults_tree=tree,
        overrides=overrides,
    )


def _has_normalized_ancestor(
    tree: DefaultsTreeNode,
) -> GroupDefault | None:
    curr: DefaultsTreeNode | None = tree
    while curr is not None:
        node = curr.node
        if isinstance(node, GroupDefault) and getattr(
            node, "normalized_shorthand", False
        ):
            return node
        curr = curr.parent
    return None


def _get_old_path(tree: DefaultsTreeNode) -> str:
    # 1. Collect nodes from root to tree
    nodes = []
    curr: DefaultsTreeNode | None = tree
    while curr is not None:
        nodes.append(curr)
        curr = curr.parent
    nodes.reverse()

    # 2. Save original groups and parent_base_dirs
    saved_groups = {}
    saved_parent_base_dirs = {}
    for n in nodes:
        node = n.node
        saved_parent_base_dirs[id(n)] = node.parent_base_dir
        if isinstance(node, GroupDefault):
            saved_groups[id(n)] = node.group

    try:
        # 3. Temporarily restore original group name for normalized nodes
        for n in nodes:
            node = n.node
            if isinstance(node, GroupDefault):
                if getattr(node, "normalized_shorthand", False):
                    node.group = getattr(node, "original_group", node.group)

        # 4. Re-calculate parent_base_dir from root to tree
        parent_base_dir = ""
        for n in nodes:
            node = n.node
            node.parent_base_dir = parent_base_dir
            if node.is_virtual():
                parent_base_dir = ""
            else:
                parent_base_dir = node.get_group_path()

        # 5. Get the old config path
        old_path = tree.node.get_config_path()
    finally:
        # 6. Safely restore all original groups and parent_base_dirs
        for n in nodes:
            node = n.node
            node.parent_base_dir = saved_parent_base_dirs[id(n)]
            if id(n) in saved_groups and isinstance(node, GroupDefault):
                node.group = saved_groups[id(n)]

    return old_path


def config_not_found_error(repo: IConfigRepository, tree: DefaultsTreeNode) -> None:
    element = tree.node
    options = None
    group = None
    if isinstance(element, GroupDefault):
        group = element.get_group_path()
        options = repo.get_group_options(group, ObjectType.CONFIG)

    # Check if the failure is caused by relying on the old slash-containing group defaults behavior
    norm_node = _has_normalized_ancestor(tree)
    if norm_node is not None:
        old_path = _get_old_path(tree)
        if repo.config_exists(old_path):
            orig_gp = getattr(norm_node, "original_group", "")
            norm_gp = norm_node.group
            assert norm_gp is not None
            msg = dedent(f"""\
            Could not load '{element.get_config_path()}'.
            However, a config was found at '{old_path}', which indicates this application
            relies on the deprecated slash-containing default option shorthand behavior.
            In Hydra 1.4, defaults list items like '{orig_gp}: {norm_gp[len(orig_gp) + 1 :]}/...' are
            normalized early to '{norm_gp}: ...'. Please update your configs or refer to the
            migration page: https://hydra.cc/docs/upgrades/1.3_to_1.4/slash_in_default/
            """)
            raise ConfigCompositionException(msg)

    if element.primary:
        msg = dedent(f"""\
        Cannot find primary config '{element.get_config_path()}'. Check that it's in your config search path.
        """)
    else:
        parent = tree.parent.node if tree.parent is not None else None
        if isinstance(element, GroupDefault):
            msg = f"Could not find '{element.get_config_path()}'\n"
            if options is not None and len(options) > 0:
                opt_list = "\n".join("\t" + x for x in options)
                msg = f"{msg}\nAvailable options in '{group}':\n" + opt_list
        else:
            msg = dedent(f"""\
            Could not load '{element.get_config_path()}'.
            """)

        if parent is not None:
            msg = f"In '{parent.get_config_path()}': {msg}"

    descs = []
    for src in repo.get_sources():
        descs.append(f"\t{repr(src)}")
    lines = "\n".join(descs)
    msg += "\nConfig search path:" + f"\n{lines}"

    raise MissingConfigException(
        missing_cfg_file=element.get_config_path(),
        message=msg,
        options=options,
    )
