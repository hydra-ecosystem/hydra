# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
import copy
from dataclasses import dataclass, field
from typing import Any

import attr
from omegaconf import MISSING, DictConfig, ListConfig, OmegaConf, TupleConfig
from omegaconf.errors import (
    InterpolationResolutionError,
    UnsupportedValueType,
    ValidationError,
)
from pytest import mark, raises

from hydra._internal.instantiate import _instantiate2 as instantiate_impl
from hydra.errors import InstantiationException
from hydra.utils import instantiate


@dataclass
class Child:
    count: int = 1
    payload: Any = None


@dataclass
class OtherChild:
    count: int = 1


@dataclass
class Config:
    _target_: str = "builtins.dict"
    count: int = 1
    values: list[int] = field(default_factory=lambda: [1])
    tags: dict[str, int] = field(default_factory=lambda: {"old": 1})
    child: Child = field(default_factory=Child)
    payload: Any = None


def call(config: Any, **kwargs: Any) -> Any:
    return instantiate(config, _execution_whitelist_="builtins.dict", **kwargs)


@mark.parametrize(
    "kind",
    [
        "dict",
        "list",
        "tuple",
        "dataclass_type",
        "dataclass_instance",
        "attrs_type",
        "attrs_instance",
    ],
)
def test_input_objects_require_explicit_config_opt_in(kind: str) -> None:
    runtime = object()

    @dataclass
    class ObjectConfig:
        _target_: str = "builtins.dict"
        payload: Any = runtime

    @attr.s(auto_attribs=True)
    class AttrObjectConfig:
        _target_: str = "builtins.dict"
        payload: Any = runtime

    configs = {
        "dict": {"_target_": "builtins.dict", "payload": runtime},
        "list": [runtime],
        "tuple": (runtime,),
        "dataclass_type": ObjectConfig,
        "dataclass_instance": ObjectConfig(),
        "attrs_type": AttrObjectConfig,
        "attrs_instance": AttrObjectConfig(),
    }
    config = configs[kind]
    with raises(UnsupportedValueType):
        call(config)
    opted_in = OmegaConf.structured(config, flags={"allow_objects": True})
    result = call(opted_in)
    assert (result[0] if kind in ("list", "tuple") else result["payload"]) is runtime


def test_object_field_annotation_requires_explicit_config_opt_in() -> None:
    @dataclass
    class ObjectAnnotationConfig:
        _target_: str = "builtins.dict"
        payload: object = None

    with raises(ValidationError, match="Unexpected type annotation: object"):
        call(ObjectAnnotationConfig)
    opted_in = OmegaConf.structured(
        ObjectAnnotationConfig, flags={"allow_objects": True}
    )
    assert call(opted_in, payload=object())["payload"] is not None


@mark.parametrize("attached", [False, True])
def test_null_structured_input_preserves_explicit_object_opt_in(attached: bool) -> None:
    runtime = object()

    @dataclass
    class ObjectConfig:
        _target_: str = "builtins.dict"
        count: int = 1
        payload: object = runtime

    cfg = DictConfig(None, ref_type=ObjectConfig, flags={"allow_objects": True})
    if attached:
        cfg._set_flag("allow_objects", None)
        root = OmegaConf.create({}, flags={"allow_objects": True})
        root["node"] = cfg
        node = root._get_node("node")
        assert isinstance(node, DictConfig)
        cfg = node
    result = call(cfg, count=2)
    assert result["count"] == 2
    assert result["payload"] is runtime
    assert cfg._is_none()


@mark.parametrize("value", ["1", "bad", 1.0, True, None])
def test_scalar_mismatch_is_rejected(value: Any) -> None:
    cfg = OmegaConf.structured(Config)
    with raises(ValidationError):
        call(cfg, count=value)
    assert cfg.count == 1


def test_valid_scalar_and_unspecified_runtime_parameters() -> None:
    runtime = object()
    values = ListConfig([2, 3])
    result = call(
        Config,
        count=2,
        values=values,
        payload=runtime,
        extra=runtime,
        _recursive_=False,
    )
    assert result["count"] == 2
    assert result["values"] is values
    assert result["payload"] is runtime
    assert result["extra"] is runtime


def test_untyped_config_does_not_acquire_schema_validation() -> None:
    assert call({"_target_": "builtins.dict", "count": 1}, count="2") == {"count": "2"}


@mark.parametrize(
    "kwargs", [{"values": ["1"]}, {"tags": {"new": "1"}}, {"child": {"count": "1"}}]
)
def test_container_mismatches_are_rejected(kwargs: Any) -> None:
    with raises(ValidationError):
        call(Config, count=2, **kwargs)


@mark.parametrize("value", [[2, "y"], ListConfig([2, "y"])])
def test_tuple_field_rejects_list_container(value: Any) -> None:
    @dataclass
    class TupleConfig:
        _target_: str = "builtins.dict"
        pair: tuple[int, str] = (1, "x")

    with raises(ValidationError):
        call(TupleConfig, pair=value)


@mark.parametrize("value", [(2, 3), OmegaConf.create((2, 3))])
def test_list_field_rejects_tuple_container(value: Any) -> None:
    @dataclass
    class ListConfig:
        _target_: str = "builtins.dict"
        values: list[int] = field(default_factory=list)

    with raises(ValidationError):
        call(ListConfig, values=value)


def test_matching_omega_conf_sequence_override_identity_is_preserved() -> None:
    @dataclass
    class SequenceConfig:
        _target_: str = "builtins.dict"
        values: list[int] = field(default_factory=list)
        pair: tuple[int, int] = (1, 2)

    values = ListConfig([2, 3])
    pair = OmegaConf.create((2, 3))
    result = call(SequenceConfig, values=values, pair=pair, _recursive_=False)
    assert result["values"] is values
    assert result["pair"] is pair


def test_plain_mapping_replacement_is_preserved() -> None:
    tags = {"new": 2}
    result = call(Config, tags=tags, _recursive_=False)
    assert result["tags"] == {"new": 2}


def test_runtime_dataclass_identity_is_preserved() -> None:
    child = Child(count=2, payload=object())
    assert call(Config, child=child)["child"] is child


@mark.parametrize("value", [object(), OtherChild(count=2)])
def test_any_structured_value_accepts_runtime_replacements(value: Any) -> None:
    @dataclass
    class AnyConfig:
        _target_: str = "builtins.dict"
        payload: Any = field(default_factory=Child)

    assert call(AnyConfig, payload=value)["payload"] is value


@mark.parametrize("interpolated", [False, True])
@mark.parametrize("recursive", [False, True])
@mark.parametrize("overlay_kind", ["dict", "dictconfig"])
def test_any_structured_value_mapping_patch_retains_schema_validation(
    interpolated: bool, recursive: bool, overlay_kind: str
) -> None:
    @dataclass
    class AnyConfig:
        _target_: str = "builtins.dict"
        template: Child = field(default_factory=lambda: Child(payload="template"))
        payload: Any = field(default_factory=lambda: Child(payload="default"))

    cfg = OmegaConf.structured(AnyConfig)
    if interpolated:
        cfg.payload = "${template}"

    def overlay(count: Any) -> Any:
        return (
            {"count": count}
            if overlay_kind == "dict"
            else OmegaConf.create({"count": count})
        )

    with raises(ValidationError):
        call(cfg, payload=overlay("2"), _recursive_=recursive)
    result = call(cfg, payload=overlay(2), _recursive_=recursive)
    assert result["payload"].count == 2
    assert result["payload"].payload == ("template" if interpolated else "default")


def test_nested_typed_union_override_preserves_type() -> None:
    @dataclass
    class WithUnion:
        value: Child | OtherChild = field(default_factory=Child)

    cfg = OmegaConf.create({"_target_": "builtins.dict", "payload": WithUnion()})
    result = call(cfg, payload={"value": OmegaConf.structured(OtherChild(count=2))})
    assert OmegaConf.get_type(result["payload"].value) is OtherChild
    assert result["payload"].value.count == 2
    assert OmegaConf.get_type(cfg.payload.value) is Child


def test_any_structured_value_explicit_omegaconf_patch_skips_resolution() -> None:
    calls = []
    OmegaConf.register_resolver("strict_lazy_patch", lambda: calls.append(1) or 2)
    try:

        @dataclass
        class AnyConfig:
            _target_: str = "builtins.dict"
            payload: Any = field(default_factory=Child)

        cfg = OmegaConf.structured(AnyConfig)
        patch = OmegaConf.create({"count": "${strict_lazy_patch:}"})
        config_before = OmegaConf.to_container(cfg, resolve=False)
        instantiate_impl._validate_override_types(cfg, {"payload": patch})
        assert calls == []
        assert OmegaConf.is_interpolation(patch, "count")
        assert OmegaConf.to_container(cfg, resolve=False) == config_before
    finally:
        OmegaConf.clear_resolver("strict_lazy_patch")


@mark.parametrize("marker", ["???", "${strict_missing_marker}"])
def test_standalone_omegaconf_marker_node_is_rejected(marker: str) -> None:
    source = OmegaConf.create({"value": marker})
    node = source._get_node("value")
    with raises(InstantiationException):
        call({"_target_": "builtins.dict"}, value=node, _recursive_=False)


@mark.parametrize("interpolated_base", [False, True])
@mark.parametrize("marker", ["???", "${strict_lazy_merge_marker}"])
def test_any_structured_value_explicit_lazy_patch_survives_merge_validation(
    interpolated_base: bool, marker: str
) -> None:
    @dataclass
    class MergeChild:
        count: int = 7
        other: int = 9

    @dataclass
    class AnyConfig:
        _target_: str = "builtins.dict"
        template: MergeChild = field(default_factory=MergeChild)
        payload: Any = field(default_factory=MergeChild)

    cfg = OmegaConf.structured(AnyConfig)
    if interpolated_base:
        cfg.payload = "${template}"
    patch = OmegaConf.create({"count": marker})
    result = call(cfg, payload=patch, _recursive_=False)
    assert OmegaConf.is_config(result["payload"])
    assert result["payload"].other == 9
    if marker == "???":
        with raises(InterpolationResolutionError):
            _ = result["payload"].count
        assert OmegaConf.is_missing(patch, "count")
    else:
        assert OmegaConf.is_interpolation(result["payload"], "count")
        assert OmegaConf.is_interpolation(patch, "count")


def test_unresolvable_interpolated_mapping_is_replaced_without_factories() -> None:
    calls = []

    def factory() -> int:
        calls.append(1)
        return len(calls)

    @dataclass
    class FactoryChild:
        count: int = 0
        generated: int = field(default_factory=factory)

    @dataclass
    class AnyConfig:
        _target_: str = "builtins.dict"
        template: FactoryChild = field(default_factory=FactoryChild)
        payload: Any = "${strict_missing_patch}"

    cfg = OmegaConf.structured(AnyConfig)
    calls.clear()
    result = call(cfg, payload={"count": 2})
    assert result["payload"] == {"count": 2}
    assert calls == []


def test_runtime_object_must_match_structured_field() -> None:
    with raises(ValidationError):
        call(Config, child=object())


@mark.parametrize("value", [MISSING, None])
def test_absent_structured_value_retains_field_validation(value: Any) -> None:
    @dataclass
    class OptionalConfig:
        _target_: str = "builtins.dict"
        child: Child | None = value

    with raises(ValidationError):
        call(OptionalConfig, child={"count": "1"})
    assert call(OptionalConfig, child={"count": 2})["child"].count == 2


def test_any_fields_inside_structured_patch_accept_runtime_objects() -> None:
    runtime = object()
    result = call(Config, child={"count": 2, "payload": runtime})
    assert result["child"].payload is runtime


def test_readonly_source_and_argument_flags_are_preserved() -> None:
    cfg = OmegaConf.structured(Config)
    values = OmegaConf.create([2])
    OmegaConf.set_readonly(cfg, True)
    OmegaConf.set_readonly(values, True)
    before = copy.deepcopy(cfg)
    result = call(cfg, values=values, _recursive_=False)
    assert result["values"] is values
    assert cfg == before
    assert OmegaConf.is_readonly(cfg)
    assert OmegaConf.is_readonly(values)


def test_local_convert_flag_cannot_enable_override_coercion() -> None:
    cfg = OmegaConf.structured(Config)
    cfg._get_node("count")._set_flag("convert", True)
    with raises(ValidationError):
        call(cfg, count="1")
    assert cfg._get_node("count")._get_node_flag("convert") is True


def test_replaced_interpolation_is_not_evaluated() -> None:
    calls = []
    OmegaConf.register_resolver("strict_replaced", lambda: calls.append(1) or 2)
    try:
        cfg = OmegaConf.structured(Config)
        cfg.count = "${strict_replaced:}"
        assert call(cfg, count=3)["count"] == 3
        assert calls == []
        assert OmegaConf.is_interpolation(cfg, "count")
    finally:
        OmegaConf.clear_resolver("strict_replaced")


def test_configured_interpolation_keeps_normal_conversion() -> None:
    @dataclass
    class AliasConfig:
        _target_: str = "builtins.dict"
        text: str = "1"
        number: int = "${text}"  # type: ignore[assignment]

    assert call(AliasConfig, text="2") == {"text": "2", "number": 2}


def test_interpolated_runtime_argument_retains_parent_and_lazy_resolution() -> None:
    source = OmegaConf.create({"value": "bad", "values": ["${value}"]})
    values = source["values"]
    result = call(Config, values=values, _recursive_=False)
    assert result["values"] is values
    assert OmegaConf.to_container(values, resolve=False) == ["${value}"]
    assert values[0] == "bad"
    source.value = 2
    assert values[0] == 2


def test_runtime_argument_allows_late_resolver_registration() -> None:
    values = OmegaConf.create(["${strict_late:}"])
    try:
        result = call(Config, values=values, _recursive_=False)
        assert result["values"] is values
        OmegaConf.register_resolver("strict_late", lambda: "1")
        assert values[0] == "1"
    finally:
        OmegaConf.clear_resolver("strict_late")


@mark.parametrize("partial", [False, True])
def test_validation_applies_to_partial_capture(partial: bool) -> None:
    with raises(ValidationError):
        call(Config, count="1", _partial_=partial)


@mark.parametrize("value", [[{"count": "1"}], [{"count": 1.0}]])
def test_structured_list_elements_cannot_be_coerced(value: Any) -> None:
    @dataclass
    class ListConfig:
        _target_: str = "builtins.dict"
        children: list[Child] = field(default_factory=list)

    with raises(ValidationError):
        call(ListConfig, children=value)
    assert call(ListConfig, children=[{"count": 2}])["children"][0].count == 2


def test_fixed_tuple_with_any_rejects_coercion() -> None:
    @dataclass
    class TupleConfig:
        _target_: str = "builtins.dict"
        pair: tuple[int, Any] = (1, None)

    runtime = object()
    with raises(ValidationError):
        call(TupleConfig, pair=("1", runtime))
    result = call(TupleConfig, pair=(2, runtime))
    assert result["pair"][0] == 2
    assert result["pair"][1] is runtime


@mark.parametrize("value", [None, DictConfig(None)])
def test_optional_mapping_accepts_null_override(value: Any) -> None:
    @dataclass
    class OptionalMapping:
        _target_: str = "builtins.dict"
        tags: dict[str, int] | None = field(default_factory=lambda: {"old": 1})

    assert call(OptionalMapping, tags=value, _recursive_=False)["tags"] is value


def test_optional_sequence_accepts_explicit_null_override() -> None:
    @dataclass
    class OptionalSequence:
        _target_: str = "builtins.dict"
        values: list[int] | None = field(default_factory=list)

    assert call(OptionalSequence, values=ListConfig(None))["values"] is None


@mark.parametrize(
    ("key", "value"),
    [("values", TupleConfig(None)), ("pair", ListConfig(None))],
)
def test_optional_sequence_accepts_cross_kind_null_override(
    key: str, value: Any
) -> None:
    @dataclass
    class OptionalSequence:
        _target_: str = "builtins.dict"
        values: list[int] | None = field(default_factory=list)
        pair: tuple[int, ...] | None = (1, 2)

    result = call(OptionalSequence, **{key: value}, _recursive_=False)
    assert result[key] is None or result[key]._is_none()


def test_null_structured_root_without_overrides_does_not_construct_defaults() -> None:
    calls = []

    @dataclass
    class NullConfig:
        _target_: str = "builtins.dict"
        values: list[int] = field(default_factory=lambda: calls.append(1) or [])

    cfg = DictConfig(None, ref_type=NullConfig)
    assert call(cfg) is None
    assert calls == []


@mark.parametrize(
    "scenario", ["null_root", "null_child", "missing_child", "structured_list"]
)
def test_validation_does_not_construct_structured_defaults(scenario: str) -> None:
    calls = []

    def factory() -> int:
        calls.append(1)
        return len(calls)

    @dataclass
    class FactoryChild:
        count: int = 0
        generated: int = field(default_factory=factory)

    @dataclass
    class FactoryConfig:
        _target_: str = "builtins.dict"
        count: int = 0
        generated: int = field(default_factory=factory)
        child: FactoryChild | None = None
        children: list[FactoryChild] = field(default_factory=list)

    cfg = (
        DictConfig(None, ref_type=FactoryConfig)
        if scenario == "null_root"
        else OmegaConf.structured(FactoryConfig)
    )
    if scenario == "missing_child":
        cfg.child = MISSING
    calls.clear()

    if scenario == "null_root":
        result = call(cfg, count=2)
        assert result["generated"] == 1
    elif scenario == "structured_list":
        result = call(cfg, children=[{"count": 2}])
        assert result["children"][0].count == 2
    else:
        result = call(cfg, child={"count": 2})
        assert result["child"].generated == 1

    assert len(calls) == (0 if scenario == "structured_list" else 1)


def test_validation_does_not_construct_attrs_defaults() -> None:
    calls = []

    def factory() -> int:
        calls.append(1)
        return len(calls)

    @attr.s(auto_attribs=True)
    class FactoryChild:
        count: int = 0
        generated: int = attr.Factory(factory)

    @attr.s(auto_attribs=True)
    class FactoryConfig:
        _target_: str = "builtins.dict"
        child: FactoryChild | None = None

    cfg = OmegaConf.structured(FactoryConfig)
    result = call(cfg, child={"count": 2})
    assert result["child"].generated == 1
    assert calls == [1]


def test_runtime_dataclass_fields_are_validated_without_coercion() -> None:
    child = Child(count="2")  # type: ignore[arg-type]
    with raises(ValidationError):
        call(Config, child=child)
    assert child.count == "2"


@mark.parametrize("kind", ["dataclass", "attrs"])
@mark.parametrize("marker", ["${missing}", MISSING])
@mark.parametrize("placement", ["child", "optional", "children", "lookup"])
def test_runtime_structured_fields_reject_config_markers(
    kind: str, marker: str, placement: str
) -> None:
    @attr.s(auto_attribs=True)
    class AttrChild:
        count: int = 1

    child_type = Child if kind == "dataclass" else AttrChild

    @dataclass
    class RuntimeConfig:
        _target_: str = "builtins.dict"
        child: child_type = field(default_factory=child_type)
        optional: child_type | None = None
        children: list[child_type] = field(default_factory=list)
        lookup: dict[str, child_type] = field(default_factory=dict)

    child = child_type(count=marker)  # type: ignore[arg-type]
    value = (
        [child]
        if placement == "children"
        else {"entry": child}
        if placement == "lookup"
        else child
    )
    with raises(InstantiationException, match="Call-site override.*count"):
        call(RuntimeConfig, **{placement: value})
    assert child.count == marker


def test_constrained_runtime_dataclass_keeps_unrestricted_fields() -> None:
    child = Child(payload=Child(count="${missing}"))  # type: ignore[arg-type]
    assert call(Config, child=child)["child"] is child
    assert child.payload.count == "${missing}"


def test_runtime_dataclass_keeps_explicit_lazy_omegaconf_fields() -> None:
    values = OmegaConf.create(["${missing}"])

    @dataclass
    class RuntimeChild:
        values: list[int] = field(default_factory=list)

    @dataclass
    class RuntimeConfig:
        _target_: str = "builtins.dict"
        child: RuntimeChild = field(default_factory=RuntimeChild)

    child = RuntimeChild(values=values)  # type: ignore[arg-type]
    assert call(RuntimeConfig, child=child)["child"] is child
    assert child.values is values
    assert OmegaConf.is_interpolation(values, 0)


@mark.parametrize("nullable", [False, True])
def test_absent_root_any_field_accepts_unconstrained_runtime_instance(
    nullable: bool,
) -> None:
    @dataclass
    class AnyConfig:
        _target_: str = "builtins.dict"
        payload: Any = None

    @dataclass
    class NullableAnyConfig(AnyConfig):
        payload: Any | None = None

    cfg = DictConfig(None, ref_type=NullableAnyConfig if nullable else AnyConfig)
    child = Child(count="2")  # type: ignore[arg-type]
    assert call(cfg, payload=child)["payload"] is child


def test_overrides_without_field_constraints_skip_validation(monkeypatch: Any) -> None:
    cfg = OmegaConf.structured(Config)
    runtime = object()

    def unexpected_validation(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("No constrained override needs validation")

    monkeypatch.setattr(instantiate_impl, "_validate", unexpected_validation)
    assert call(cfg)["count"] == 1
    result = call(cfg, payload=runtime, extra=runtime, _recursive_=False)
    assert result["payload"] is runtime
    assert result["extra"] is runtime


def test_rejected_override_preserves_config_and_attached_source() -> None:
    cfg = OmegaConf.structured(Config)
    source = OmegaConf.create({"values": ["2"]})
    values = source["values"]
    OmegaConf.set_readonly(cfg, True)
    OmegaConf.set_readonly(source, True)
    values._set_flag("convert", True)
    config_before = OmegaConf.to_container(cfg, resolve=False)
    source_before = OmegaConf.to_container(source, resolve=False)

    with raises(ValidationError):
        call(cfg, values=values, _recursive_=False)

    assert OmegaConf.to_container(cfg, resolve=False) == config_before
    assert OmegaConf.to_container(source, resolve=False) == source_before
    assert values._get_parent() is source
    assert OmegaConf.is_readonly(cfg)
    assert OmegaConf.is_readonly(values)
    assert values._get_node_flag("convert") is True
