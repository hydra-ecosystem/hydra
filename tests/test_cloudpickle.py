# SPDX-FileCopyrightText: Contributors to Hydra
# SPDX-License-Identifier: MIT
import copyreg
import io
import pickle
from functools import partial
from types import CodeType, FunctionType
from typing import Any

from pytest import importorskip, mark

cloudpickle = importorskip("cloudpickle")
source_pickle = importorskip("hydra._internal.cloudpickle")


@mark.parametrize("filename", [__file__, "<generated-task>"])
def test_preserves_nested_code_locations(filename: str) -> None:
    def task() -> CodeType:
        def helper() -> None:
            pass

        return helper.__code__

    original = task.__code__
    task.__code__ = original.replace(
        co_filename=filename,
        co_consts=tuple(
            value.replace(co_filename=filename)
            if isinstance(value, CodeType)
            else value
            for value in original.co_consts
        ),
    )
    dispatch_before = dict(cloudpickle.CloudPickler.dispatch_table)
    stream = io.BytesIO()
    source_pickle.SourcePickler(stream).dump(task)
    restored = pickle.loads(stream.getvalue())  # nosec B301: trusted test data

    assert restored.__code__.co_filename == filename
    assert restored().co_filename == filename
    assert cloudpickle.CloudPickler.dispatch_table == dispatch_before


def test_serializes_shared_task_state_only_once() -> None:
    class Once:
        calls = 0

        def __reduce__(self) -> Any:
            self.calls += 1
            assert self.calls == 1
            return list, ()

    shared = Once()

    def task(other: Any) -> bool:
        return shared is other

    stream = io.BytesIO()
    source_pickle.SourcePickler(stream).dump((partial(task, shared), shared))
    restored, other = pickle.loads(stream.getvalue())  # nosec B301: trusted test data

    assert restored()
    assert restored.func(other)
    assert shared.calls == 1


def test_reducer_preserves_other_code_fields() -> None:
    def task() -> None:
        pass

    constructor, args = source_pickle.reduce_code(task.__code__)
    restored = constructor(*args)

    assert restored == task.__code__
    assert restored.co_filename == task.__code__.co_filename


def test_distinct_filenames_for_otherwise_identical_functions() -> None:
    def task() -> None:
        pass

    functions = tuple(
        FunctionType(task.__code__.replace(co_filename=name), {})
        for name in ("first.py", "second.py")
    )
    stream = io.BytesIO()
    source_pickle.SourcePickler(stream).dump(functions)
    first, second = pickle.loads(stream.getvalue())  # nosec B301: trusted test data

    assert first.__code__.co_filename == "first.py"
    assert second.__code__.co_filename == "second.py"


def test_honors_reducers_registered_after_import() -> None:
    class LateRegistered:
        def __reduce__(self) -> Any:
            raise AssertionError("copyreg reducer was bypassed")

    def reduce_late(value: LateRegistered) -> Any:
        return str, ("late reducer",)

    copyreg.pickle(LateRegistered, reduce_late)
    try:
        stream = io.BytesIO()
        source_pickle.SourcePickler(stream).dump(LateRegistered())
        restored = pickle.loads(stream.getvalue())  # nosec B301: trusted test data
        assert restored == "late reducer"
    finally:
        copyreg.dispatch_table.pop(LateRegistered)
