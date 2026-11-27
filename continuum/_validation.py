"""Small, explicit input contracts; no coercion or hardware policy."""
import math


def real(name, value, *, positive=False, allow_infinity=False):
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be an ordinary int or float, excluding bool")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        raise ValueError(f"{name} exceeds the finite numeric range") from None
    if not finite and not (allow_infinity and value == math.inf):
        raise ValueError(f"{name} must be finite")
    if value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be {'> 0' if positive else '>= 0'}")


def count(name, value, minimum):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}, excluding bool")
    real(name, value)


def name_string(name, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


def choice(name, value, options):
    if type(value) is not str or value not in options:
        raise ValueError(f"{name} must be one of {', '.join(options)}")


def boolean(name, value):
    if type(value) is not bool:
        raise ValueError(f"{name} must be bool")
