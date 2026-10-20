import sys,tempfile
from pathlib import Path
from unittest.mock import patch
if __name__ != '__main__':
    import unittest
    raise unittest.SkipTest('Run with xvfb-run -a python3 test_audio_eq_editor_live.py')
import audio_eq_editor as ui
from gi.repository import GLib
app=ui.Equalizer();errors=[];calls=[]
def inspect():
    app.adjustments[0].set_value(4.5)
    GLib.timeout_add(250, preview)
    return False
def preview():
    try:
        assert ui.eq.preview_gains()==[4.5,0,0,0,0,0]
        assert ui.eq.selection()=='balanced'
        assert 'Not saved' in app.status.get_text()
        app.save_button.clicked()
        GLib.timeout_add(150, saved)
    except Exception as e:errors.append(e);app.quit()
    return False
def saved():
    try:
        assert calls==[('custom',[4.5,0,0,0,0,0])]
        assert ui.eq.preview_gains() is None
        assert 'now your system default' in app.status.get_text()
        app.adjustments[1].set_value(2)
        GLib.timeout_add(150, closed)
    except Exception as e:errors.append(e);app.quit()
    return False
def closed():
    try:
        assert ui.eq.preview_gains()[1]==2
        app.window.destroy()
        assert ui.eq.preview_gains() is None
        assert ui.eq.selection()=='balanced'
    except Exception as e:errors.append(e)
    app.quit();return False
with tempfile.TemporaryDirectory() as d:
    root=Path(d)
    with patch.multiple(ui.eq,STATE=root/'state.json',PREVIEW=root/'preview.json',STATUS=root/'status.json'), patch.object(ui.eq,'run',return_value=''), patch.object(ui.eq,'configure',side_effect=lambda *args:calls.append(args)):
        ui.eq.save(ui.eq.STATE,dict(preset='balanced'))
        GLib.timeout_add(200,inspect)
        app.run(None)
if errors:raise errors[0]
print('PASS slider preview, saved-default isolation, Save clears preview, close restores')
