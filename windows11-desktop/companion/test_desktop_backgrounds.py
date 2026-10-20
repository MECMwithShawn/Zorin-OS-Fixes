"""Wallpaper routing/recovery boundaries, without changing the real desktop."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import dbus
import wallpaper as w
import desktop_backgrounds as d


class DesktopBackgroundTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.props={'/backdrop/screen0/monitorscreen/workspace0/last-image':dbus.String(str(self.root/'original.jpg')),
                    '/backdrop/single-workspace-mode':dbus.Boolean(False),'/backdrop/single-workspace-number':dbus.Int32(2)}
        (self.root/'original.jpg').write_bytes(b'original')
        self.original=self.props.copy();self.ids=['a'*24,'b'*24,'c'*24]
        for ident in self.ids:(self.root/(ident+'.image')).write_bytes(b'image')
        self.context={'uid':'desktop-a','all_ids':['desktop-a','desktop-b'],'monitors':['screen']}
        def props(channel):return self.props.copy() if channel=='xfce4-desktop' else {'/general/workspace_count':1}
        def setter(channel,key,value):self.props[key]=value
        self.xf=Mock();self.xf.SetProperty.side_effect=setter
        self.xf.ResetProperty.side_effect=lambda channel,key,_:self.props.pop(key,None)
        self.patches=[patch.object(w,'is_gnome',return_value=False),patch.object(d,'is_gnome',return_value=False),
                      patch.object(w,'CONFIG',self.root),patch.object(w,'ROOT',self.root),patch.object(w,'STATE',self.root/'state.json'),
                      patch.object(d,'CONTEXT',self.context),patch.object(w,'properties',side_effect=props),patch.object(d,'properties',side_effect=props),
                      patch.object(w,'set_property',side_effect=setter),patch.object(d,'set_property',side_effect=setter),
                      patch.object(w.subprocess,'check_output',return_value='screen connected'),
                      patch.object(d.dbus,'SessionBus',return_value=Mock()),patch.object(d.dbus,'Interface',return_value=self.xf)]
        for p in self.patches:p.start()
        w.save({'source':'spotlight','daily':True,'history':[{'id':i} for i in self.ids]})
        w.apply(self.ids[0])
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def displayed(self):return str(self.props['/backdrop/screen0/monitorscreen/workspace0/last-image'])
    def test_spotlight_updates_shared_desktops_without_replacing_a_custom_picture(self):
        d.assign('desktop-a',self.ids[1]);self.assertEqual(self.displayed(),str(self.root/(self.ids[1]+'.image')))
        w.apply(self.ids[2])
        self.assertEqual(self.displayed(),str(self.root/(self.ids[1]+'.image')))
        self.assertTrue(w.load()['daily']);self.assertEqual(w.load()['source'],'spotlight')
        self.context['uid']='desktop-b';d.sync()
        self.assertEqual(self.displayed(),str(self.root/(self.ids[2]+'.image')))
        self.context['uid']='desktop-a';d.sync();d.assign('desktop-a',None)
        self.assertEqual(self.displayed(),str(self.root/(self.ids[2]+'.image')))
        self.assertEqual(self.props['/backdrop/single-workspace-mode'],self.original['/backdrop/single-workspace-mode'])
    def test_full_restore_recovers_original_picture_and_typed_native_mode_after_rotation(self):
        d.assign('desktop-a',self.ids[1]);w.apply(self.ids[2]);w.restore()
        self.assertEqual(self.props,self.original)
        self.assertIsInstance(self.props['/backdrop/single-workspace-mode'],dbus.Boolean)
        self.assertIsInstance(self.props['/backdrop/single-workspace-number'],dbus.Int32)
        self.assertNotIn('desktopPictures',w.load());self.assertNotIn('desktopWrites',w.load())
    def test_restore_keeps_manual_changes(self):
        d.assign('desktop-a',self.ids[1])
        key='/backdrop/screen0/monitorscreen/workspace0/last-image';self.props[key]=dbus.String('manual.jpg')
        w.restore();self.assertEqual(self.props[key],'manual.jpg')
        self.assertFalse(self.props['/backdrop/single-workspace-mode'])
    def test_stale_desktop_and_invalid_history_ids_cannot_change_wallpaper(self):
        before=self.props.copy()
        for uid,ident in [('removed',self.ids[1]),('desktop-a','../../etc/passwd'),('desktop-a','f'*24)]:
            with self.assertRaises(ValueError):d.assign(uid,ident)
        self.assertEqual(self.props,before)
    def test_assigned_photo_survives_history_eviction(self):
        from gi.repository import GdkPixbuf
        d.assign('desktop-a',self.ids[1]);state=w.load()
        state['history']=[{'id':format(i,'024x')} for i in range(60)]+[{'id':self.ids[1]}];w.save(state)
        pix=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,800,450);pix.fill(0x305070ff)
        data=bytes(pix.save_to_bufferv('png',[],[])[1]);w.remember(data,{'source':'local','title':'New image'})
        self.assertTrue(w.image_path(self.ids[1]).is_file())
        self.assertFalse(any(i['id']==self.ids[1] for i in w.load()['history']))
    def test_partial_desktop_write_has_recovery_journal(self):
        real=d.set_property.side_effect;count=[0]
        def fail(channel,key,value):
            count[0]+=1
            if count[0]==2:raise RuntimeError('desktop unavailable')
            real(channel,key,value)
        d.set_property.side_effect=fail
        with self.assertRaises(RuntimeError):d.assign('desktop-a',self.ids[1])
        self.assertTrue(w.load()['desktopWrites'])
        w.restore();self.assertEqual(self.props,self.original)


if __name__=='__main__':unittest.main()
