import unittest,tempfile,json
from pathlib import Path
from window_layouts import encode,decode
from saved_groups import Recipes,validate

OUTPUTS=[dict(index=0,model='Laptop',manufacturer='A',primary=True,area=[400,900,1600,1000]),dict(index=1,model='Dell',manufacturer='B',primary=False,area=[0,0,2400,900])]
def member(rect=(50,20,800,700)):
    return dict(app='one.desktop',**{'class':'One'},state='normal',**encode(rect,OUTPUTS))
class LayoutTests(unittest.TestCase):
    def test_geometry_round_trip_and_scale_and_reordered_outputs(self):
        for rect in [(50,20,800,700),(500,980,800,700),(100,300,2400,1000)]:
            r=member(rect)
            self.assertEqual(decode(r,list(reversed(OUTPUTS))),rect)
        r=member();changed=[dict(OUTPUTS[1],area=[100,0,1200,450])]
        self.assertEqual(decode(r,changed),(125,10,400,350))
    def test_missing_display_fits_to_remaining_display(self):
        rect=decode(member(),OUTPUTS[:1]);x,y,w,h=rect;a,b,c,d=OUTPUTS[0]['area']
        self.assertTrue(a<=x and b<=y and x+w<=a+c and y+h<=b+d)
    def test_persistence_and_legacy_groups(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'layouts.json';r=Recipes(p);ident=r.put([member() for _ in range(12)],name='Desk',kind='layout')
            loaded=Recipes(p);self.assertEqual(len(loaded.groups[0]['members']),12)
            loaded.rename(ident,'Work');self.assertEqual(Recipes(p).groups[0]['name'],'Work')
            loaded.remove(ident);self.assertFalse(Recipes(p).groups)
    def test_invalid_monitor_and_state_do_not_get_saved(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Recipes(Path(folder)/'layout.json')
            for bad in [dict(member(),monitor={}),dict(member(),state='execute'),dict(member(),rect=[float('inf'),0,1,1])]:
                with self.assertRaises(ValueError):store.put([bad],kind='layout')
            self.assertFalse(store.path.exists())
if __name__=='__main__':unittest.main()
