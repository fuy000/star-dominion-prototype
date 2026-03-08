import unittest

from game.bootstrap import create_default_app


class BootstrapTests(unittest.TestCase):
    def test_create_default_app_returns_a_scene_and_config(self) -> None:
        app = create_default_app()

        self.assertEqual(app.config.size, (1280, 720))
        self.assertEqual(app.config.world_size, (4000, 2400))
        self.assertTrue(hasattr(app.scene, "update"))
        self.assertTrue(hasattr(app.scene, "render"))


if __name__ == "__main__":
    unittest.main()
