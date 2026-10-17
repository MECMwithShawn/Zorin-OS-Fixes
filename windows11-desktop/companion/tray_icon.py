"""Fluent tray artwork; update only files still owned by us."""
import json
import re

def generate(destination):
    def glyph(name):
        svg=(destination/'fluent'/(name+'.svg')).read_text()
        return re.sub(r'fill="[^"]*"','fill="#f3f3f3"',re.search(r'<svg[^>]*>(.*)</svg>',svg,re.S)[1])
    for network,name in {'wifi':'wifi','wired':'plug-connected','offline':'globe-prohibited'}.items():
        for muted in (False, True):
            svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="48" height="20" viewBox="0 0 48 20">{glyph(name)}<g transform="translate(28 0)">{glyph("speaker-mute" if muted else "speaker-2")}</g></svg>'
            (destination/f'tray-{network}-{int(muted)}.svg').write_text(svg)

def update_icon(base, config, status):
    # Genmon draws the SVG at its intrinsic 48x20 size and rereads this small
    # status file. No scaling a two-glyph strip into a square launcher icon.
    destination=config/'tray-status.json'
    value=json.dumps({'networkType':status.get('networkType','offline'),
                      'muted':bool(status.get('muted',False)),
                      'volume':status.get('volume')},sort_keys=True)+'\n'
    if not destination.exists() or destination.read_text()!=value:
        temporary=destination.with_suffix('.tmp');temporary.write_text(value);temporary.replace(destination)
