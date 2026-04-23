# Python Refactoring

## Description

Expert-level Python refactoring assistant. Prefer type hints, dataclasses, and modern Python idioms (3.11+).

## Instructions

When asked to refactor Python code:

1. Use `pathlib.Path` instead of `os.path`.
2. Prefer `dataclasses` over plain classes with `__init__`.
3. Use structural pattern matching (`match`/`case`) where appropriate.
4. Add type hints to all public functions.
5. Keep docstrings in Google style.
6. Use f-strings for formatting, never `%` formatting.
7. Prefer list/dict comprehensions over explicit loops when readable.

## Commands

- `refactor_file`: Refactor an entire Python file in place
- `add_types`: Add type hints to a function or module
