from dataclasses import dataclass, field
from pathlib import Path

from game.config import GameConfig
from game.core.scene import Scene
from game.runtime import require_pygame


_BACKGROUND_MUSIC_DIR = Path(__file__).resolve().parents[1] / "assets" / "audio"
_SUPPORTED_MUSIC_SUFFIXES = (".ogg", ".wav", ".mp3")


def _find_background_music_file() -> Path | None:
    if not _BACKGROUND_MUSIC_DIR.is_dir():
        return None

    candidates = sorted(
        path
        for path in _BACKGROUND_MUSIC_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in _SUPPORTED_MUSIC_SUFFIXES
    )
    return candidates[0] if candidates else None


def _start_background_music(pygame: object) -> None:
    music_path = _find_background_music_file()
    if music_path is None:
        return

    try:
        mixer = pygame.mixer
        if not mixer.get_init():
            mixer.init()
        mixer.music.load(str(music_path))
        mixer.music.set_volume(0.3)
        mixer.music.play(-1)
    except Exception:
        return


def _stop_background_music(pygame: object) -> None:
    try:
        mixer = pygame.mixer
        if mixer.get_init():
            mixer.music.stop()
    except Exception:
        return


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
        _start_background_music(pygame)
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
            _stop_background_music(pygame)
            pygame.quit()
