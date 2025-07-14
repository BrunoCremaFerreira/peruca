from abc import ABC, abstractmethod


class Graph(ABC):
    """
    Graph Interface
    """

    @abstractmethod
    def invoke(self, user_message) -> dict:
        pass