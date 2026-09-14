"""maps task names to callables, the queue's only knowledge of what work exists"""

from typing import Callable

_registry: dict[str, Callable] = {}


def task(name: str) -> Callable[[Callable], Callable]:
    """
    the decorated function is returned unchanged,
    so it stays directly callable and unit-testable without going through the queue
    """

    def decorator(fn: Callable) -> Callable:
        if name in _registry:
            raise ValueError(f"task '{name}' is already registered")
        _registry[name] = fn
        return fn

    return decorator


def get_task(name: str) -> Callable:
    if name not in _registry:
        raise KeyError(f"no task registered under '{name}'")
    return _registry[name]


def is_registered(name: str) -> bool:
    return name in _registry
