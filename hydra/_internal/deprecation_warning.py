# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import os
import warnings

from hydra.errors import HydraDeprecationError


def deprecation_warning(
    message: str, stacklevel: int = 1, category: type[Warning] = UserWarning
) -> None:
    warnings_as_errors = os.environ.get("HYDRA_DEPRECATION_WARNINGS_AS_ERRORS")
    if warnings_as_errors:
        raise HydraDeprecationError(message)
    else:
        warnings.warn(message, category=category, stacklevel=stacklevel + 1)
