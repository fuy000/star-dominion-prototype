from game.config import GameConfig
from game.core.app import GameApp
from game.scenes.star_map import StarMapScene


def create_default_app(config: GameConfig | None = None) -> GameApp:
    resolved_config = config or GameConfig()
    scene = StarMapScene(
        world_width=resolved_config.world_width,
        world_height=resolved_config.world_height,
        viewport_width=resolved_config.width,
        viewport_height=resolved_config.height,
    )
    return GameApp(config=resolved_config, initial_scene=scene)
