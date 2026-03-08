import unittest

from game.config import GameConfig


class GameConfigTests(unittest.TestCase):
    def test_default_size_is_hd_ready(self) -> None:
        config = GameConfig()

        self.assertEqual(config.size, (1280, 720))
        self.assertEqual(config.world_size, (4000, 2400))
        self.assertEqual(config.target_fps, 60)
        self.assertEqual(config.background_color, (7, 10, 18))

    def test_world_is_larger_than_viewport_for_camera_navigation(self) -> None:
        config = GameConfig()

        self.assertGreater(config.world_width, config.width)
        self.assertGreater(config.world_height, config.height)



if __name__ == "__main__":
    unittest.main()
