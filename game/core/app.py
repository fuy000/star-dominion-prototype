from dataclasses import dataclass, field

from game.config import GameConfig
from game.core.scene import Scene
from game.runtime import require_pygame


@dataclass(slots=True)
class GameApp:
    config: GameConfig
    initial_scene: Scene
    _running: bool = field(init=False, default=False)
    _scene: Scene = field(init=False)

    def __post_init__(self) -> None:
        self._running = False
        self._scene = self.initial_scene

    @property
    def scene(self) -> Scene:
        return self._scene

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        pygame = require_pygame()
        pygame.init()
        pygame.display.set_caption(self.config.title)
        screen = pygame.display.set_mode(self.config.size)
        clock = pygame.time.Clock()
        self._running = True
        self._scene.on_enter()

        try:
            while self._running:
                dt = clock.tick(self.config.target_fps) / 1000.0
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.stop()
                        continue
                    self._scene.handle_event(event)

                self._scene.update(dt)
                screen.fill(self.config.background_color)
                self._scene.render(screen)
                pygame.display.flip()
        finally:
            self._scene.on_exit()
            pygame.quit()
