"""Tiny buggy calculator used for synthetic RepoMedic demos."""


def add(a: int, b: int) -> int:
    return a + b


def subtract(a: int, b: int) -> int:
    return a - b


def multiply(a: int, b: int) -> int:
    return a * b


def divide(a: int, b: int) -> float:
    # BUG: should raise ZeroDivisionError for b == 0
    if b == 0:
        return 0.0
    return a / b
