from importlib.util import find_spec


def is_pygame_available() -> bool:
    return find_spec("pygame") is not None


def require_pygame():
    if not is_pygame_available():
        raise RuntimeError(
            "pygame is required to run the game window. Install it with: "
            "python3 -m pip install pygame"
        )

    import pygame

    return pygame
