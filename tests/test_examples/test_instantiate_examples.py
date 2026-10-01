# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
from pathlib import Path
from textwrap import dedent

from pytest import mark, param

from hydra.test_utils.test_utils import (
    assert_text_same,
    chdir_hydra_root,
    run_python_script,
)

chdir_hydra_root()


@mark.parametrize(
    "overrides,output",
    [
        ([], "MySQL connecting to localhost"),
        (["db=postgresql"], "PostgreSQL connecting to localhost"),
    ],
)
def test_instantiate_object(tmpdir: Path, overrides: list[str], output: str) -> None:
    cmd = [
        "examples/instantiate/object/my_app.py",
        f'hydra.run.dir="{tmpdir}"',
        "hydra.job.chdir=True",
    ] + overrides
    result, _err = run_python_script(cmd)
    assert result == output


@mark.parametrize(
    "overrides,output",
    [
        ([], "Driver : James Bond, 4 wheels"),
        (
            ["car.wheels=[{_target_:my_app.Wheel,radius:7,width:1}]"],
            "Driver : James Bond, 1 wheels",
        ),
    ],
)
def test_instantiate_object_recursive(
    tmpdir: Path, overrides: list[str], output: str
) -> None:
    cmd = [
        "examples/instantiate/object_recursive/my_app.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
    ] + overrides
    result, _err = run_python_script(cmd)
    assert result == output


def test_instantiate_object_partial(tmpdir: Path) -> None:
    cmd = [
        "examples/instantiate/partial/my_app.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
    ]
    result, _err = run_python_script(cmd)
    assert result == "Model(Optimizer=Optimizer(algo=SGD,lr=0.1))"


@mark.parametrize(
    "overrides,output",
    [
        ([], "MySQL connecting to localhost"),
        (["db=postgresql"], "PostgreSQL connecting to localhost"),
    ],
)
def test_instantiate_schema(tmpdir: Path, overrides: list[str], output: str) -> None:
    cmd = [
        "examples/instantiate/schema/my_app.py",
        f'hydra.run.dir="{str(tmpdir)}"',
        "hydra.job.chdir=True",
    ] + overrides
    result, _err = run_python_script(cmd)
    assert result == output


@mark.parametrize(
    "overrides,expected",
    [
        (
            [],
            dedent("""\
                root(1)
                  left(20)
                    right(30)
                      left(400)
                      right(300)
                """),
        ),
    ],
)
def test_instantiate_schema_recursive(
    tmpdir: Path, overrides: list[str], expected: str
) -> None:
    cmd = [
        "examples/instantiate/schema_recursive/my_app.py",
        f'hydra.run.dir="{tmpdir}"',
        "hydra.job.chdir=True",
    ] + overrides
    result, _err = run_python_script(cmd)
    assert_text_same(result, expected)


@mark.parametrize(
    "overrides,expected",
    [
        param(
            [],
            dedent("""\
                Optimizer(algo=SGD,lr=0.01)
                Optimizer(algo=SGD,lr=0.2)
                Trainer(
                  optimizer=Optimizer(algo=SGD,lr=0.01),
                  dataset=Dataset(name=Imagenet, path=/datasets/imagenet)
                )
                Trainer(
                  optimizer=Optimizer(algo=SGD,lr=0.3),
                  dataset=Dataset(name=cifar10, path=/datasets/cifar10)
                )
                Trainer(
                  optimizer={'_target_': 'my_app.Optimizer', 'algo': 'SGD', 'lr': 0.01},
                  dataset={'_target_': 'my_app.Dataset', 'name': 'Imagenet', 'path': '/datasets/imagenet'}
                )
                """),
            id="default-output",
        ),
    ],
)
def test_instantiate_docs_example(
    tmpdir: Path, overrides: list[str], expected: str
) -> None:
    cmd = [
        "examples/instantiate/docs_example/my_app.py",
        f'hydra.run.dir="{tmpdir}"',
        "hydra.job.chdir=True",
    ] + overrides
    result, _err = run_python_script(cmd)
    assert_text_same(result, expected)
