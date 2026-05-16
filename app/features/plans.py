from enum import StrEnum


class Plan(StrEnum):
    FREE = "free"
    PLUS = "plus"
    PRO = "pro"


PLAN_FREE = Plan.FREE.value
PLAN_PLUS = Plan.PLUS.value
PLAN_PRO = Plan.PRO.value
