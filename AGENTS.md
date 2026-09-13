# Agent guidelines for this repo

## Layout
- CLI scripts live in `src/tools/bin/`, shared code in `src/tools/libs/`.
- Every script gets an entry point in `pyproject.toml` under `[project.scripts]`
  (e.g. `net-watch = "tools.bin.net_watch:main"`).
- Platform- or feature-specific dependencies go in `[project.optional-dependencies]`
  extras (e.g. `ldap`, `mac`) and are referenced in the entry point (`main [mac]`).
- Optional imports should not break module import: wrap them in
  `try: import x / except ModuleNotFoundError: x = None` so tests run everywhere.

## Coding
- All imports go at the top of the file — never import in the middle of a file
  (not even in test bodies); optional dependencies use the try/except pattern above.
- Prefer `click` for new CLIs (some older tools use ConfigArgParse or typer).
- New CLIs should support a config file: add an eager `-c/--config` option whose
  callback loads an INI file (section named after the app) into `ctx.default_map`,
  defaulting to `~/.config/<app>.cfg`. CLI options must override config values.
- Formatting is enforced by black (via pytest-black): line length 120,
  `skip-string-normalization` (keep single quotes). Run black before committing.
- mypy is enforced via pytest-mypy; keep type hints on public functions.
- Long-running/GUI tools should default to running detached (daemon) with a
  `-F/--foreground` flag. On macOS do not `fork()` after importing Objective-C
  frameworks (AppKit/rumps): re-exec the command with `--foreground` in a new
  session instead.

## Testing
- Tests live in `test/test_<module>.py`; run them with tox:
  `tox -e py312 -- test/test_<module>.py`
  If `tox` is not on PATH, use uv (the repo's `.python-version` is a pyenv alias
  uv cannot parse, so pass the interpreter explicitly):
  `uv run --python 3.12 --group dev tox -e py312 -- test/test_<module>.py`
- pytest runs with `--doctest-modules`, `--black`, `--mypy` and coverage
  (see `addopts` in `pyproject.toml`): docstring examples are executed as tests.
- Prefer pytest fixtures with `monkeypatch` over inline `mock.patch` in test
  bodies; print the mock calls at teardown for debugging:

  ```python
  @pytest.fixture
  def mock_time(monkeypatch):
      mock_obj = mock.Mock(name='time')
      monkeypatch.setattr('tools.libs.xymon.time', mock_obj)
      yield mock_obj
      print(f'{mock_obj} {mock_obj.mock_calls}')
  ```

- Use `@pytest.mark.parametrize` for input/output tables and `tmp_path` for
  files (e.g. config files); never touch the real `$HOME`.
- Test CLIs through `click.testing.CliRunner`, asserting both exit code and
  output (`assert result.exit_code == 0, result.output`).
