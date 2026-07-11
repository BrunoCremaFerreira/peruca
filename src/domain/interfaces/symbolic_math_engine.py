from abc import ABC, abstractmethod


class SymbolicMathEngine(ABC):
    """
    Port for the CAS backend. Operates on canonical expression strings so the
    domain stays free of any concrete math library.
    """

    @abstractmethod
    def integrate(self, expression: str, variable: str) -> str: ...

    @abstractmethod
    def diff(self, expression: str, variable: str) -> str: ...

    @abstractmethod
    def gradient(self, expression: str, variables: list[str]) -> list[str]: ...

    @abstractmethod
    def limit(self, expression: str, variable: str, to: str) -> str: ...

    @abstractmethod
    def simplify(self, expression: str) -> str: ...
