# Star Dominion Prototype

A small 2D Python game prototype inspired by *Hades' Star*, built to grow into a larger strategy game.

## Project structure

- `game/` — application package
- `tests/` — automated tests
- `pyproject.toml` — project metadata and tooling configuration
- `.github/workflows/ci.yml` — GitHub Actions test workflow

## Requirements

- Python 3.11+

## Quick start

1. Create a virtual environment:
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
2. Install the project in editable mode:
   - `python -m pip install -e .`
3. Run the game:
   - `python -m game`

You can also use the generated console script after installation:

- `star-dominion`

## Running tests

- `python -m unittest discover -s tests -v`

## License

This project is licensed under the GNU General Public License v3.0.

## Controls

- `WASD` / arrow keys — move camera
- Mouse wheel / `+` / `-` — zoom
- Left click — select a star system

## GitHub readiness

This repository includes:

- package metadata in `pyproject.toml`
- a clean package entrypoint
- a Python-focused `.gitignore`
- GitHub Actions CI

## Recommended next steps before publishing

- create a GitHub repository
- add the repository URL to `pyproject.toml`
- push the local Git repo to GitHub
