from dataclasses import dataclass


@dataclass(slots=True)
class GameConfig:
    title: str = "Star Dominion Prototype"
    width: int = 1280
    height: int = 720
    world_width: int = 4000
    world_height: int = 2400
    target_fps: int = 60
    background_color: tuple[int, int, int] = (7, 10, 18)

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)

    @property
    def world_size(self) -> tuple[int, int]:
        return (self.world_width, self.world_height)
