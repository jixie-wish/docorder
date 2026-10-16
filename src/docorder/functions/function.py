"""A transform bound to one operator run."""

from __future__ import annotations

from typing import Any

from docorder.core.artifact import Artifact
from docorder.core.environment import Environment


class Function:
    """A transform bound to one operator run.

    ``operator`` is the operator this function is running for.
    ``environment`` is built from that operator. ``operator_props`` is the
    function parameters. ``template_env`` is the nested view a template reads.
    """

    def __init__(
        self,
        artifact: Artifact,
        *,
        operator: Any,
    ) -> None:
        self.artifact = artifact
        self.operator = operator
        self.environment = Environment(operator)
        self.operator_name = operator.name
        self.epoch = operator.run_context.epoch

    @staticmethod
    def create(
        function_cls: type,
        artifact: Artifact,
        *,
        operator: Any,
    ) -> Function:
        """Construct ``function_cls`` with the operator run it belongs to."""
        return function_cls(artifact, operator=operator)
