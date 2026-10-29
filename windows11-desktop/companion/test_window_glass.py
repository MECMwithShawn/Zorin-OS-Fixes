import json,tempfile,unittest
from pathlib import Path
import window_glass

class WindowGlassTests(unittest.TestCase):
    def test_defaults_and_clamping_match_the_extension(self):
        self.assertEqual(window_glass.normalize(None),window_glass.DEFAULTS)
        self.assertEqual(window_glass.normalize({'active':5,'inactive':300,'blur':-4,'enabled':0}),
                         {'enabled':False,'active':60,'inactive':100,'blur':0})
        self.assertEqual(window_glass.normalize({'active':'x','blur':float('nan')}),window_glass.DEFAULTS)

    def test_save_merges_changes_and_survives_a_bad_file(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'zorin11-hub/glass.json'
            self.assertEqual(window_glass.read(path),window_glass.DEFAULTS)
            self.assertEqual(window_glass.save({'active':70},path)['active'],70)
            self.assertEqual(window_glass.save({'blur':999},path),{'enabled':True,'active':70,'inactive':85,'blur':80})
            self.assertEqual(json.loads(path.read_text())['blur'],80)
            path.write_text('{broken')
            self.assertEqual(window_glass.save({'enabled':False},path),dict(window_glass.DEFAULTS,enabled=False))
            self.assertFalse(path.with_name('glass.json.tmp').exists())

if __name__=='__main__':unittest.main()
