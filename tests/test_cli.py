import unittest
from unittest.mock import patch

from game.cli import main


class CliTests(unittest.TestCase):
    @patch("game.cli.create_default_app")
    def test_main_creates_and_runs_default_app(self, create_default_app) -> None:
        app = create_default_app.return_value

        main()

        create_default_app.assert_called_once_with()
        app.run.assert_called_once_with()