import array
import math
import unittest
from unittest.mock import patch
import audio_spectrum as spectrum


class SpectrumTests(unittest.TestCase):
    def test_real_tones_silence_and_nonfinite_samples(self):
        def pcm(values):
            a=array.array('f',values)
            if spectrum.sys.byteorder!='little':a.byteswap()
            return a.tobytes()
        for hz in (94,375,1000,3000,9000):
            values=(.5*math.sin(2*math.pi*hz*i/spectrum.RATE) for i in range(spectrum.SIZE))
            bands=spectrum.levels(pcm(values))
            peak=max(range(len(bands)),key=bands.__getitem__)
            self.assertLessEqual(spectrum.EDGES[peak],hz+24)
            self.assertGreaterEqual(spectrum.EDGES[peak+1],hz-24)
            self.assertGreater(bands[peak],.7)
        self.assertEqual(spectrum.levels(pcm([0]*spectrum.SIZE)),[0]*16)
        self.assertEqual(spectrum.levels(pcm([float('nan')]*spectrum.SIZE)),[0]*16)

    def test_monitor_is_explicitly_from_default_output_and_never_default_input(self):
        with patch.object(spectrum,'command',side_effect=['speakers','[{"name":"speakers","monitor_source":"speakers.monitor"}]']):
            self.assertEqual(spectrum.output_monitor(),'speakers.monitor')
        with patch.object(spectrum,'command',side_effect=['missing','[]']):
            self.assertIsNone(spectrum.output_monitor())
