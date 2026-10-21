"""Preview scheduling, visibility, lifetime and decoding without desktop capture."""
import struct
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
import gi
gi.require_version('GdkPixbuf','2.0')
from gi.repository import GdkPixbuf
from card_previews import CardPreviews,decode


def png():
    pix=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,24,16);pix.fill(0x30cc50ff)
    return bytes(pix.save_to_bufferv('png',[],[])[1])

class CardPreviewTests(unittest.TestCase):
    def setUp(self):
        self.jobs=[];self.minimized=set();self.closed=set()
        self.clients=[NS(get_xid=lambda i=i:i,is_minimized=lambda i=i:i in self.minimized) for i in range(45)]
        self.m=NS(preview_cache={},windows=NS(windows=lambda:[w for w in self.clients if w.get_xid() not in self.closed]),
                  hub=NS(background=lambda *job:self.jobs.append(job)))
        self.p=CardPreviews(self.m)
        for name,value in [('timeout_add',7),('source_remove',True)]:
            patched=patch('card_previews.GLib.'+name,return_value=value);patched.start();self.addCleanup(patched.stop)
        self.children=[self.card(0),self.card(1,y=100)]
        self.view=NS(preview_ready=Mock());self.watch()
    def card(self,ident,y=0,visible=True,mapped=True):
        return NS(xid=ident,get_child_visible=lambda:visible,get_mapped=lambda:mapped,
                  get_allocation=lambda:NS(y=y,height=100),preview_image=NS(set_from_pixbuf=Mock()))
    def watch(self):
        self.flow=NS(get_mapped=lambda:True,get_children=lambda:self.children,connect=Mock())
        self.scroll=NS(get_vadjustment=lambda:NS(get_value=lambda:0,get_page_size=lambda:200))
        self.p.watch(self.scroll,self.flow,self.view)
    def finish(self,data=None):self.jobs[-1][1](png() if data is None else data)
    def test_only_visible_live_nonminimized_cards_are_requested(self):
        self.children=[self.card(0,y=-100),self.card(1,y=200),self.card(2,visible=False),self.card(3,mapped=False),self.card(4),self.card(5),self.card(40,y=150)]
        self.minimized.add(4);self.closed.add(5)
        self.assertEqual([c.xid for c in self.p.targets()],[40])
        self.p.tick();self.finish();self.assertEqual(list(self.m.preview_cache),[40])
    def test_one_pending_job_and_round_robin_refresh(self):
        self.p.tick()
        for _ in range(20):self.p.tick()
        self.assertEqual(len(self.jobs),1)
        self.finish();self.assertEqual(list(self.m.preview_cache),[0])
        self.p.tick();self.finish();self.assertEqual(list(self.m.preview_cache),[0,1])
        self.p.tick();self.finish();self.assertEqual(list(self.m.preview_cache),[1,0])
        self.view.preview_ready.assert_called()
    def test_rebuild_waits_and_discards_old_result(self):
        self.p.tick();old=self.jobs[0]
        self.watch();self.p.tick();self.assertEqual(len(self.jobs),1)
        old[1](png());self.assertFalse(self.m.preview_cache)
        self.p.tick();self.assertEqual(len(self.jobs),2)
        self.finish();self.assertEqual(list(self.m.preview_cache),[0])
    def test_close_skips_queued_capture_and_rejects_completed_data(self):
        self.p.tick();capture,done,_=self.jobs[0];self.p.stop()
        with patch('card_previews.subprocess.run') as child:self.assertEqual(capture(),b'')
        child.assert_not_called();done(png());self.assertFalse(self.m.preview_cache)
        self.assertFalse(self.p.tick());self.assertEqual(self.p.timer,0)
    def test_late_result_after_filter_minimize_or_close_is_ignored(self):
        for change in (lambda:self.children.clear(),lambda:self.minimized.add(0),lambda:self.closed.add(0)):
            self.children=[self.card(0)];self.closed.clear();self.minimized.clear()
            self.p.tick();change();self.finish()
            self.assertFalse(self.m.preview_cache)
    def test_failure_retries_and_cache_is_bounded(self):
        self.p.tick();self.jobs[-1][2]('capture timed out');self.assertFalse(self.p.pending)
        self.m.preview_cache={i:None for i in range(2,38)}
        self.p.tick();self.finish();self.assertEqual(len(self.m.preview_cache),36)
        self.assertNotIn(2,self.m.preview_cache)
    def test_decode_rejects_invalid_or_unbounded_images(self):
        valid=png();self.assertEqual(decode(valid).get_width(),24)
        for data in (b'',b'not PNG',valid[:30],valid+b'x'*1048576,valid[:16]+struct.pack('!II',90000,90000)+valid[24:]):
            self.assertIsNone(decode(data))

if __name__=='__main__':unittest.main()
