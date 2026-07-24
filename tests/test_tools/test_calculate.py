"""Tests for the calculate tool (AST-based safe evaluation)."""

from claxcode.tools.custom_example import Calculate


async def test_basic_arithmetic():
    assert await Calculate().execute(expression="2 + 2 * 3") == "8"


async def test_functions_and_constants():
    assert await Calculate().execute(expression="sqrt(16) + floor(pi)") == "7.0"


async def test_unary_and_power():
    assert await Calculate().execute(expression="-2 ** 2") == "-4"


async def test_rejects_dunder_breakout():
    result = await Calculate().execute(expression="().__class__.__base__.__subclasses__()")
    assert "出错" in result


async def test_rejects_function_calls_outside_allowlist():
    result = await Calculate().execute(expression="open('/etc/passwd')")
    assert "出错" in result


async def test_rejects_garbage():
    result = await Calculate().execute(expression="not an expression at all")
    assert "出错" in result
