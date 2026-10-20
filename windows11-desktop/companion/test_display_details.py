import unittest
from unittest.mock import patch
import subprocess
import display_details as d

def fixture():
    panel=('eDP-1','Vendor','Panel','serial')
    external=('DP-1','Vendor','External','serial2')
    mode=lambda ident,w,h,hz,props:(ident,w,h,hz,1.,[1.,1.25,2.],props)
    return (7,[
        (external,[mode('ext',2560,1440,59.95,{'is-current':True,'is-preferred':True})],{'display-name':'External'}),
        (panel,[mode('panel',3840,2160,120.,{'is-current':True,'is-preferred':True})],{'display-name':'Laptop','is-builtin':True})],
        [(0,0,1.25,1,True,[panel],{}),(1728,0,1.,0,False,[external],{})],{'renderer':'native'})

class DisplayTests(unittest.TestCase):
    def test_primary_rotation_scale_and_distinct_identity(self):
        rows=d.parse_state(fixture())
        self.assertEqual([r['connector'] for r in rows],['eDP-1','DP-1'])
        self.assertEqual(rows[0]['scale'],1.25)
        self.assertEqual(rows[0]['rotation'],'Portrait (90°)')
        self.assertEqual(rows[0]['resolution'],(3840,2160))
        self.assertEqual(rows[1]['refresh'],59.95)
        self.assertIn(('Scale','125%'),d.fields(rows[0]))
    def test_mirrored_group_and_inactive_monitor(self):
        state=list(fixture());panel=state[1][1][0];external=state[1][0][0]
        state[2]=[(0,0,2.,0,True,[panel,external],{})]
        self.assertTrue(all(r['mirrored'] for r in d.parse_state(state)))
        state[2]=[(0,0,2.,0,True,[panel],{})]
        row=next(r for r in d.parse_state(state) if r['connector']=='DP-1')
        self.assertFalse(row['active']);self.assertIsNone(row['scale'])
    def test_physical_size_requires_exact_identity_and_nonzero_dimensions(self):
        output=(0,0,0,[],'eDP-1',[],[],{'vendor':'Vendor','product':'Panel','serial':'serial','width-mm':300,'height-mm':200})
        resources=(7,[],[output],[],0,0)
        row=d.parse_state(fixture(),resources)[0]
        self.assertAlmostEqual(row['dpi'][0],325.12)
        output[-1]['serial']='different'
        self.assertIsNone(d.parse_state(fixture(),resources)[0]['dpi'])
        output[-1].update(serial='serial',**{'height-mm':0})
        self.assertIsNone(d.parse_state(fixture(),resources)[0]['size'])
    def test_missing_current_mode_is_not_invented(self):
        state=fixture();state[1][1][1][0][-1].pop('is-current')
        row=d.parse_state(state)[0]
        self.assertIsNone(row['resolution']);self.assertIsNone(row['refresh'])
        self.assertEqual(dict(d.fields(row))['Refresh rate'],'Unavailable')
    def test_gpu_machine_format_and_optional_tools(self):
        rows=d.parse_gpus('0000:01:00.0 "VGA compatible controller" "Vendor" "GPU name" -r01\n0000:00:01.0 "Audio device" "Vendor" "Audio"\n"broken')
        self.assertEqual(rows,[{'slot':'0000:01:00.0','name':'Vendor GPU name'}])
        with patch.object(d.shutil,'which',return_value=None):self.assertEqual(d.run(['missing']),'')
        with patch.object(d.shutil,'which',return_value='/tool'),patch.object(d.subprocess,'run',side_effect=subprocess.TimeoutExpired('tool',3)):
            self.assertEqual(d.run(['tool']),'')
    def test_resource_race_drops_outdated_panel_dimensions(self):
        from unittest.mock import Mock
        bus=Mock()
        bus.call_sync.side_effect=[Mock(unpack=lambda:fixture()),Mock(unpack=lambda:(6,[],[],[],0,0))]
        with patch.object(d.Gio,'bus_get_sync',return_value=bus),patch.object(d,'run',return_value=''):
            data=d.collect()
        self.assertIsNone(data['monitors'][0]['dpi'])
        self.assertIsNone(data['renderer'])
        self.assertEqual([c.args[3] for c in bus.call_sync.call_args_list],['GetCurrentState','GetResources'])

if __name__=='__main__':unittest.main()
