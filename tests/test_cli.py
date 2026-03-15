import unittest
import runpy
from unittest.mock import patch

from game.cli import main


class CliTests(unittest.TestCase):
    @patch("game.cli.create_default_app")
    def test_main_creates_and_runs_default_app(self, create_default_app) -> None:
        app = create_default_app.return_value

        main()

        create_default_app.assert_called_once_with()
        app.run.assert_called_once_with()

    @patch("game.cli.main")
    def test_python_m_game_entrypoint_calls_cli_main(self, cli_main) -> None:
        runpy.run_module("game", run_name="__main__")

        cli_main.assert_called_once_with()
