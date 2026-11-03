from datetime import datetime

from app.tools import calculator, get_current_time


def test_calculator_basic():
    assert calculator.invoke({"expression": "(1+2)*3"}) == "9"


def test_calculator_float():
    assert calculator.invoke({"expression": "7/2"}) == "3.5"


def test_calculator_rejects_names():
    assert calculator.invoke({"expression": "__import__('os')"}).startswith("error")


def test_calculator_rejects_huge_power():
    assert calculator.invoke({"expression": "2**1000000"}).startswith("error")


def test_calculator_division_by_zero():
    assert calculator.invoke({"expression": "1/0"}).startswith("error")


def test_current_time_is_iso():
    datetime.fromisoformat(get_current_time.invoke({}))
