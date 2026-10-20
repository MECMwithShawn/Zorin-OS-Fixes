#!/usr/bin/python3
"""Add shared system EQ to an existing Axentra Mini Media Rust source tree."""
from pathlib import Path
import argparse

def integrate(root):
    main=root/'src/main.rs';ui=root/'src/ui.rs'
    original_main=main.read_text();original_ui=ui.read_text()
    module=Path(__file__).with_name('system_eq.rs').read_bytes()
    destination=root/'src/system_eq.rs'
    if destination.exists() and destination.read_bytes()!=module:
        raise RuntimeError('Player has a different EQ implementation; preserve it and review integration manually.')
    updated_main=original_main
    if 'mod system_eq;' not in updated_main:updated_main='mod system_eq;\n'+updated_main
    updated_ui=original_ui
    anchor='        root.pack_end(&appearance_panel, false, false, 0);'
    addition='\n        root.pack_end(&crate::system_eq::widget(), false, false, 0);'
    if addition not in updated_ui:
        if updated_ui.count(anchor)!=1:raise RuntimeError('Player layout changed; review the common appearance-panel insertion point.')
        updated_ui=updated_ui.replace(anchor,anchor+addition)
    # Refuse concurrent changes rather than overwriting another editor's work.
    if main.read_text()!=original_main or ui.read_text()!=original_ui:
        raise RuntimeError('Player source changed during integration; retry after reviewing it.')
    destination.write_bytes(module)
    main.write_text(updated_main);ui.write_text(updated_ui)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    integrate(parser.parse_args().source.resolve())
