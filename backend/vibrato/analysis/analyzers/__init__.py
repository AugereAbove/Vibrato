from importlib import import_module

MODULES = (
    "pitch",
    "vibrato",
    "vowels",
    "voice_quality",
    "phonation",
    "register",
    "nonlinear",
    "articulation",
    "breath",
    "dynamics",
    "timbre",
    "quality",
)


def load_all() -> None:
    for name in MODULES:
        import_module(f"{__name__}.{name}")
