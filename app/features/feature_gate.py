from app.features.plans import Plan


_PLAN_RANK = {
    Plan.FREE: 0,
    Plan.PLUS: 1,
    Plan.PRO: 2,
}


class FeatureGate:
    def __init__(self, active_plan: Plan | str = Plan.FREE) -> None:
        self.active_plan = Plan(active_plan)

    def set_active_plan(self, plan: Plan | str) -> None:
        self.active_plan = Plan(plan)

    def is_allowed(self, feature_id: str, plan: Plan | str) -> bool:
        del feature_id  # reserved for future per-feature server overrides
        required = Plan(plan)
        return _PLAN_RANK[self.active_plan] >= _PLAN_RANK[required]
