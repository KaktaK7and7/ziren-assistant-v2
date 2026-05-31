from dataclasses import dataclass, field


@dataclass
class WindowTarget:
    hwnd: int
    title: str
    process_id: int
    process_name: str = ""
    visible: bool = True
    minimized: bool = False


@dataclass
class WindowActionResult:
    status: str
    message: str
    candidates: list[WindowTarget] = field(default_factory=list)
    target: WindowTarget | None = None
