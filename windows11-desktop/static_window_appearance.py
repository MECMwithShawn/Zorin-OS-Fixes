#!/usr/bin/env python3
"""Opt out of the optional global Window Glass effect; preserve app styling."""
import json
from pathlib import Path
import gnome_install
import gnome_setup


def apply():
    Gio,GLib=gnome_setup.bindings()
    path=Path.home()/'.config/zorin11-hub/glass.json'
    data=json.loads(path.read_text()) if path.exists() else {}
    data.update(enabled=False,active=100,inactive=100,blur=0)
    gnome_install.write_files({path:(json.dumps(data,indent=2)+'\n').encode()})
    settings=Gio.Settings.new('org.gnome.shell');uuid='zorin11-glass@zorin-os-fixes'
    gnome_setup.install(gnome_setup.plan({'org.gnome.shell':{
        'enabled-extensions':[v for v in settings.get_strv('enabled-extensions') if v!=uuid],
        'disabled-extensions':list(dict.fromkeys([*settings.get_strv('disabled-extensions'),uuid]))}}))
    print('Static window appearance enabled; global window opacity and blur disabled.')

if __name__=='__main__':apply()
