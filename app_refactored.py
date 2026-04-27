"""
Refactored FolioIQ entrypoint with separated modules:
- refactored_app/ui_theme.py (UI styling/theme)
- refactored_app/logic.py (business logic and analytics)
- refactored_app/ui_flow.py (screen rendering flow)
"""

from pathlib import Path

from refactored_app.ui_theme import apply_theme
from refactored_app import logic as logic_mod

# Export all logic symbols (including underscore-prefixed helpers)
# so ui_flow can run with the same runtime context as monolithic app.py.
for _name, _value in logic_mod.__dict__.items():
	if not _name.startswith("__"):
		globals()[_name] = _value

apply_theme()

_ui_file = Path(__file__).with_name("refactored_app").joinpath("ui_flow.py")
_ui_code = _ui_file.read_text(encoding="utf-8")
exec(compile(_ui_code, str(_ui_file), "exec"), globals(), globals())
