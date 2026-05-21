from dataclasses import dataclass, field


@dataclass
class AppTarget:
    target_id: str
    name: str
    type: str
    launch_uri: str | None = None
    path: str | None = None
    appid: str | None = None
    aliases: list[str] = field(default_factory=list)
    source: str = ""
    confidence_bonus: float = 0.0


@dataclass
class LaunchResolution:
    status: str
    query: str
    target: AppTarget | None = None
    candidates: list[AppTarget] = field(default_factory=list)
    message: str = ""
