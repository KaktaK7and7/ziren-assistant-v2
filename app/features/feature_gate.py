from app.features.plans import Plan


class FeatureGate:
    def is_allowed(self, feature_id: str, plan: Plan | str) -> bool:
        return Plan(plan) == Plan.FREE
