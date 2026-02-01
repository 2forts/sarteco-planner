import math


HOURS_PER_DAY = 8


def hours_to_days(hours: float) -> int:
    """Convert a duration in hours to a number of working days.

    This reference implementation uses a non-preemptive, day-granular model:
    each operation occupies an integer number of full working days.
    """
    return int(math.ceil(hours / HOURS_PER_DAY))


def day_to_start_hour(day: int) -> int:
    return day * HOURS_PER_DAY


def day_to_end_hour(day: int) -> int:
    return day * HOURS_PER_DAY
