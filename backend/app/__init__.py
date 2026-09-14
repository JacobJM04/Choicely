"""Load backend/.env into the environment before any module reads a setting.

Dependency-free (no python-dotenv): only KEY=VALUE lines, '#' comments, and
optional surrounding quotes. Real environment variables always win over the
file, so a deploy that sets ANTHROPIC_API_KEY in its dashboard is unaffected.
"""
import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

if _ENV_FILE.is_file():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _key, _, _val = _line.partition("=")
        _key, _val = _key.strip(), _val.strip().strip('"').strip("'")
        if _key and _key not in os.environ:
            os.environ[_key] = _val
