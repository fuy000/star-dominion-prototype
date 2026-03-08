import unittest
from importlib.util import find_spec

from game.runtime import is_pygame_available, require_pygame


class RuntimeTests(unittest.TestCase):
    def test_availability_matches_import_probe(self) -> None:
        self.assertEqual(is_pygame_available(), find_spec("pygame") is not None)

    def test_require_pygame_returns_module_or_helpful_error(self) -> None:
        if is_pygame_available():
            self.assertEqual(require_pygame().__name__, "pygame")
            return

        with self.assertRaises(RuntimeError) as context:
            require_pygame()

        self.assertIn("python3 -m pip install pygame", str(context.exception))


if __name__ == "__main__":
    unittest.main()