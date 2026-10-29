"""Settings for the zorin11-glass GNOME Shell extension.

The extension watches this file and applies changes live; the clamping here
mirrors gnome-glass-extension/model.js so both sides agree on every value.
"""
import json
import os
from pathlib import Path

PATH = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home()/'.config')/'zorin11-hub/glass.json'
UUID = 'zorin11-glass@zorin-os-fixes'
DEFAULTS = {'enabled': True, 'active': 90, 'inactive': 85, 'blur': 30}


def _number(value, low, high, fallback):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number != number or number in (float('inf'), float('-inf')):
        return fallback
    return int(round(max(low, min(high, number))))


def normalize(raw):
    cfg = raw if isinstance(raw, dict) else {}
    return {
        'enabled': DEFAULTS['enabled'] if cfg.get('enabled') is None else bool(cfg['enabled']),
        'active': _number(cfg.get('active'), 60, 100, DEFAULTS['active']),
        'inactive': _number(cfg.get('inactive'), 60, 100, DEFAULTS['inactive']),
        'blur': _number(cfg.get('blur'), 0, 80, DEFAULTS['blur']),
    }


def read(path=None):
    try:
        return normalize(json.loads((path or PATH).read_text()))
    except (OSError, ValueError):
        return dict(DEFAULTS)


def installed():
    home = Path(os.environ.get('XDG_DATA_HOME') or Path.home()/'.local/share')
    return any((base/'gnome-shell/extensions'/UUID/'extension.js').is_file()
               for base in (home, Path('/usr/share')))


def save(changes, path=None):
    path = path or PATH
    cfg = normalize({**read(path), **(changes if isinstance(changes, dict) else {})})
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(cfg)+'\n')
    os.replace(temp, path)
    return cfg
