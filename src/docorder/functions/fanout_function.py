from abc import ABC, abstractmethod

from docorder.core.entity import Entity
from docorder.functions.function import Function


class FanoutFunction(Function, ABC):

    def output_names(self, source_entity: Entity) -> list[str]:
        """Output entity names produced from this upstream entity.

        The default is the upstream entity's own name. Override it to expand
        one entity into many.
        """
        return [source_entity.name]

    @abstractmethod
    def transform_data(self, source_entity: Entity, target_entity: Entity):
        pass

    @abstractmethod
    def transform_props(self, source_entity: Entity, target_entity: Entity):
        pass
