"""Control boundaries and notification safety without changing the desktop."""
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch,Mock
import dbus
import notifications
import quick_controls
import settings_backend

class NotificationTests(unittest.TestCase):
    def test_markup_stays_plain_text_and_actions_are_not_exported(self):
        row=['id',1234567890000,'UTC','example','Example','https://remote/icon','<b>Hello</b>','Text<br/><a href="https://remote">link</a> &amp; more',[['action','Do something']],5000,False]
        with patch.object(notifications,'properties',return_value={}),patch.object(notifications,'call',return_value=[row]):result=notifications.snapshot()
        n=result['entries'][0]
        self.assertEqual(n['time'],1234567890);self.assertEqual(n['title'],'Hello');self.assertEqual(n['body'],'Text\nlink & more')
        self.assertNotIn('actions',n);self.assertNotIn('icon',n)
    def test_unavailable_service_does_not_invent_history(self):
        with patch.object(notifications,'properties',return_value={}),patch.object(notifications,'call',side_effect=dbus.DBusException('unavailable')):
            self.assertFalse(notifications.snapshot()['available']);self.assertFalse(notifications.has_unread())
    def test_dismiss_targets_only_selected_existing_ids(self):
        with patch.object(notifications,'call') as call:
            notifications.change('dismiss',['owned-test'])
            self.assertEqual(call.call_args_list[0].args,('Get','owned-test'))
            self.assertEqual(call.call_args.args[0],'Delete');self.assertEqual(list(call.call_args.args[1]),['owned-test'])
        with patch.object(notifications,'call') as call:
            for ids in [[],[''],['a']*201,'x',[1]]:
                with self.assertRaises(ValueError):notifications.change('dismiss',ids)
            call.assert_not_called()
    def test_retention_is_bounded_in_ui(self):
        row=['id',1234567890000,'UTC','app','App','','Title','Body',[],0,True]
        with patch.object(notifications,'properties',return_value={}),patch.object(notifications,'call',return_value=[row]*201):
            data=notifications.snapshot();self.assertTrue(data['hasMore']);self.assertEqual(len(data['entries']),200)

class ControlTests(unittest.TestCase):
    def test_tile_editor_rejects_unknown_or_empty_configuration(self):
        for value in [[],['wifi','wifi'],['shell'],None,['wifi',1]]:
            with self.assertRaises(ValueError):quick_controls.validate_tiles(value)
        self.assertEqual(quick_controls.validate_tiles(['wifi','display']),['wifi','display'])
    def test_new_updates_tile_joins_saved_layouts_once(self):
        self.assertEqual(quick_controls.saved_tiles({}),list(quick_controls.TILES))
        self.assertEqual(quick_controls.saved_tiles({'quick_tiles':['wifi','display','dnd']}),['wifi','display','updates','dnd'])
        self.assertEqual(quick_controls.saved_tiles({'quick_tiles':['wifi']}),['wifi','updates'])
        removed={'quick_tiles':['wifi','display'],'quick_tiles_known':list(quick_controls.TILES)}
        self.assertEqual(quick_controls.saved_tiles(removed),['wifi','display'])
    def test_update_status_reads_agent_inventory_defensively(self):
        with tempfile.TemporaryDirectory() as t,patch.object(settings_backend.Path,'home',return_value=Path(t)):
            self.assertIsNone(settings_backend.update_status())
            path=Path(t)/'.config/zorin11-hub/update-status.json';path.parent.mkdir(parents=True)
            path.write_text('{"count":3,"security":1,"reboot":false,"checked":1700000000}')
            self.assertEqual(settings_backend.update_status(),{'count':3,'security':1,'reboot':False,'checked':1700000000})
            for bad in ('[]','{"count":"x"}','not json'):
                path.write_text(bad);self.assertIsNone(settings_backend.update_status())
    def test_brightness_discovers_hardware_and_validates_device(self):
        with tempfile.TemporaryDirectory() as t,patch.object(quick_controls,'BACKLIGHT',Path(t)):
            self.assertEqual(quick_controls.backlights(),[])
            dev=Path(t)/'intel_backlight';dev.mkdir();(dev/'brightness').write_text('300');(dev/'max_brightness').write_text('1000')
            self.assertEqual(quick_controls.backlights()[0]['value'],30)
            with patch.object(quick_controls.dbus,'SystemBus') as bus:
                for ident,value in [('intel_backlight',0),('intel_backlight',True),('../../bad',50),('intel_backlight',101)]:
                    with self.assertRaises(ValueError):quick_controls.brightness(ident,value)
                bus.assert_not_called()
            interface=Mock();session=Mock();bus=Mock()
            with patch.object(quick_controls.dbus,'SystemBus',return_value=bus),patch.object(quick_controls,'login_session',return_value=session),patch.object(quick_controls.dbus,'Interface',return_value=interface):
                quick_controls.brightness('intel_backlight',42)
                interface.SetBrightness.assert_called_once_with('backlight','intel_backlight',dbus.UInt32(420),timeout=4)
    def test_brightness_rejects_other_users_inactive_or_remote_sessions(self):
        manager=Mock();manager.GetSessionByPID.side_effect=dbus.DBusException('not in session');manager.GetSession.return_value='/session/test'
        props=Mock();obj=object();bus=Mock();bus.get_object.return_value=obj
        def interface(_,name):return manager if name.endswith('.Manager') else props
        with patch.object(quick_controls.dbus,'Interface',side_effect=interface),patch.object(quick_controls.os,'getuid',return_value=1000),patch.dict(quick_controls.os.environ,{'XDG_SESSION_ID':'test'}):
            for uid,active,remote in [(2000,True,False),(1000,False,False),(1000,True,True)]:
                props.GetAll.return_value={'User':[uid],'Active':active,'Remote':remote}
                with self.assertRaises(ValueError):quick_controls.login_session(bus)
            props.GetAll.return_value={'User':[1000],'Active':True,'Remote':False}
            self.assertIs(quick_controls.login_session(bus),obj)
            manager.GetSession.assert_called_with('test',timeout=3)

    def test_audio_switch_moves_default_streams_but_preserves_custom_routes(self):
        calls=[]
        def run(args):
            calls.append(args)
            if args==['pactl','get-default-sink']:return 'old'
            if args==['pactl','--format=json','list','sinks']:return json.dumps([{'index':4,'name':'old'},{'index':5,'name':'new'}])
            if args==['pactl','--format=json','list','sink-inputs']:return json.dumps([{'index':20,'sink':4},{'index':21,'sink':8}])
            return ''
        with patch.object(settings_backend,'sound_outputs',return_value=[{'id':'new'}]),patch.object(settings_backend,'run',side_effect=run):settings_backend.apply('output','new')
        self.assertIn(['pactl','move-sink-input','20','new'],calls)
        self.assertFalse(any(c[:3]==['pactl','move-sink-input','21'] for c in calls))

if __name__=='__main__':unittest.main()
