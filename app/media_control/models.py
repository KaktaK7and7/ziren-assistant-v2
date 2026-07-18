from dataclasses import dataclass, field


@dataclass
class MusicPreset:
    preset_id: str
    name: str
    url: str
    aliases: list[str] = field(default_factory=list)
    enabled: bool = True


@dataclass
class MediaActionResult:
    status: str  # success | not_found | error
    message: str
    preset: MusicPreset | None = None
