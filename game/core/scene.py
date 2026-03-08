from abc import ABC, abstractmethod


class Scene(ABC):
    def on_enter(self) -> None:
        """Called when the scene becomes active."""

    def on_exit(self) -> None:
        """Called when the scene is replaced or closed."""

    def handle_event(self, event: object) -> None:
        """Called for each framework event."""

    @abstractmethod
    def update(self, dt: float) -> None:
        """Advance simulation by delta time in seconds."""

    @abstractmethod
    def render(self, surface: object) -> None:
        """Draw the scene to the active surface."""
