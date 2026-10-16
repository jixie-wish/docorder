from abc import ABC, abstractmethod

from docorder.core.entity import Entity
from docorder.functions.function import Function


class ReduceFunction(Function, ABC):

    @abstractmethod
    def transform_data(self, source_entity: list[Entity], target_entity: Entity):
        pass

    @abstractmethod
    def transform_props(self, source_entity: list[Entity], target_entity: Entity):
        pass
