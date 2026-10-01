# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import logging
from typing import Any, Mapping

log = logging.getLogger(__name__)


class EarlyStopper:
    """Class to implement the early stopping mechanism.
    The optimization process is stopped when the performance does not
    improve for a threshold number of consecutive epochs. The performance
    is considered to have improved when the change is more than a given
    threshold (epsilon)."""

    def __init__(
        self, max_epochs_without_improvement: int, epsilon: float, minimize: bool
    ):
        self.max_epochs_without_improvement = max_epochs_without_improvement
        self.epsilon = epsilon
        self.minimize = minimize
        self.current_best_value: float | None = None
        self.current_epochs_without_improvement = 0

    def should_stop(
        self, potential_best_value: float, best_parameters: Mapping[str, Any]
    ) -> bool:
        """Check if the optimization process should be stopped."""
        is_improving = True
        if self.current_best_value is not None:
            if self.minimize:
                is_improving = (
                    potential_best_value + self.epsilon < self.current_best_value
                )
            else:
                is_improving = (
                    potential_best_value - self.epsilon > self.current_best_value
                )

        if is_improving:
            self.current_epochs_without_improvement = 0
            self.current_best_value = potential_best_value
            log.info(
                f"New best value: {potential_best_value}, best parameters: {best_parameters}"
            )

            return False
        else:
            self.current_epochs_without_improvement += 1

        if (
            self.current_epochs_without_improvement
            >= self.max_epochs_without_improvement
        ):
            log.info(
                f"Early stopping, best known value {self.current_best_value}"
                f" did not improve for {self.current_epochs_without_improvement} epochs"
            )
            return True
        return False
