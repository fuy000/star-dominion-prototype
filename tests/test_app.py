import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from game.core import app as app_module


class GameAppMusicTests(unittest.TestCase):
    def test_find_background_music_file_returns_first_supported_track(self) -> None:
        with TemporaryDirectory() as temp_dir:
            audio_dir = Path(temp_dir)
            (audio_dir / "notes.txt").write_text("ignore me", encoding="utf-8")
            first_track = audio_dir / "alpha_theme.wav"
            second_track = audio_dir / "zeta_theme.ogg"
            first_track.write_bytes(b"")
            second_track.write_bytes(b"")

            with patch.object(app_module, "_BACKGROUND_MUSIC_DIR", audio_dir):
                self.assertEqual(app_module._find_background_music_file(), first_track)

    def test_start_background_music_initializes_mixer_and_loops_track(self) -> None:
        music = Mock()
        mixer = SimpleNamespace(get_init=Mock(return_value=False), init=Mock(), music=music)
        pygame = SimpleNamespace(mixer=mixer)
        music_path = Path("/tmp/theme.wav")

        with patch.object(app_module, "_find_background_music_file", return_value=music_path):
            app_module._start_background_music(pygame)

        mixer.init.assert_called_once_with()
        music.load.assert_called_once_with(str(music_path))
        music.set_volume.assert_called_once_with(0.3)
        music.play.assert_called_once_with(-1)

    def test_start_background_music_swallows_audio_errors(self) -> None:
        mixer = SimpleNamespace(get_init=Mock(return_value=False), init=Mock(side_effect=RuntimeError("no audio")), music=Mock())
        pygame = SimpleNamespace(mixer=mixer)

        with patch.object(app_module, "_find_background_music_file", return_value=Path("/tmp/theme.wav")):
            app_module._start_background_music(pygame)


if __name__ == "__main__":
    unittest.main()