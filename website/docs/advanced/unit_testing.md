---
id: unit_testing
title: Hydra in Unit Tests
---

import GithubLink from "@site/src/components/GithubLink"

Use `initialize()`, `initialize_config_module()`, `initialize_config_dir()` or `initialize_config_search_path()` in conjunction with `compose()`
to compose configs inside your unit tests.  
Be sure to read the [Compose API documentation](compose_api.md).

The Hydra example application contains an <GithubLink to="examples/advanced/hydra_app_example/tests/test_example.py">example test</GithubLink>.

```python title="Testing example with initialize()"
from hydra import initialize, compose
# 1. initialize will add config_path the config search path within the context
# 2. The module with your configs should be importable. 
#    it needs to have a __init__.py (can be empty).
# 3. THe config path is relative to the file calling initialize (this file)
def test_with_initialize() -> None:
    with initialize(config_path="../hydra_app/conf"):
        # config is relative to a module
        cfg = compose(config_name="config", overrides=["app.user=test_user"])
        assert cfg == {
            "app": {"user": "test_user", "num1": 10, "num2": 20},
            "db": {"host": "localhost", "port": 3306},
        }
```

For an idea about how to modify Hydra's search path when using `compose` in
unit tests, see the page on
[adding config sources with `hydra.searchpath`](search_path/hydra_searchpath.md).
