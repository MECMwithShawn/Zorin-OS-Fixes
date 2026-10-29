import json
import tempfile
import unittest
from pathlib import Path
from saved_groups import Recipes,validate,identify,matches_member
from types import SimpleNamespace


def members():return [dict(app='one.desktop',**{'class':'One'},rect=[0,0,.5,1]),dict(app='two.desktop',**{'class':'Two'},rect=[.5,0,.5,1])]


class RecipeTests(unittest.TestCase):
    def test_wayland_app_identity_overrides_shared_or_changed_classes(self):
        member=dict(app='one.desktop',**{'class':'Electron'})
        one=SimpleNamespace(get_application_id=lambda:'one.desktop',get_class_group_name=lambda:'NewWaylandClass')
        wrong=SimpleNamespace(get_application_id=lambda:'two.desktop',get_class_group_name=lambda:'Electron')
        self.assertEqual(identify(one,{'one.desktop':object()}),'one.desktop')
        self.assertTrue(matches_member(one,member))
        self.assertFalse(matches_member(wrong,member))
        self.assertFalse(matches_member(SimpleNamespace(get_application_id=lambda:'hidden.desktop'),member))

    def test_x11_and_unidentified_clients_keep_class_fallback(self):
        member=dict(app='one.desktop',**{'class':'Electron'})
        old=SimpleNamespace(get_class_group_name=lambda:'electron')
        unknown=SimpleNamespace(get_application_id=lambda:'',get_class_group_name=lambda:'Electron')
        self.assertTrue(matches_member(old,member))
        self.assertTrue(matches_member(unknown,member))
        self.assertFalse(matches_member(old,dict(member,**{'class':'Other'})))

    def test_restart_rename_update_and_remove_without_window_ids(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'snap-groups.json';store=Recipes(path)
            ident=store.put(members(),name='Work')
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            store=Recipes(path);self.assertEqual(store.groups[0]['id'],ident)
            self.assertEqual(store.put(members()),ident)
            store.rename(ident,'Writing');self.assertEqual(Recipes(path).groups[0]['name'],'Writing')
            changed=members();changed[0]['rect']=[0,0,.6,1];changed[1]['rect']=[.6,0,.4,1]
            store.put(changed,ident=ident);self.assertEqual(len(store.groups),1)
            self.assertNotIn('xid',path.read_text());self.assertNotIn('command',path.read_text())
            store.remove(ident);self.assertEqual(Recipes(path).groups,[])

    def test_invalid_geometry_launcher_and_schema_are_rejected(self):
        for field,value in [('app','../../bad.desktop'),('rect',[0,0,float('nan'),1]),('rect',[0,0,4,1]),('class','')]:
            data={'version':1,'groups':[dict(id='a'*32,name='Test',members=members())]}
            data['groups'][0]['members'][0][field]=value
            with self.assertRaises(ValueError):validate(data)
        with self.assertRaises(ValueError):validate({'version':2,'groups':[]})

    def test_corrupt_original_is_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'snap-groups.json';path.write_text('{broken')
            store=Recipes(path);self.assertTrue(store.error)
            with self.assertRaises(ValueError):store.put(members())
            self.assertEqual(path.read_text(),'{broken')


if __name__=='__main__':unittest.main()
