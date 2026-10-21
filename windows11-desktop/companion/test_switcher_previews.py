"""Alt+Tab capture must follow visible cards and their window lifetimes."""
import struct
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from switcher import Switcher
from test_card_previews import png


class SwitcherPreviewTests(unittest.TestCase):
    def setUp(self):
        self.jobs=[];self.minimized=set();self.closed=set()
        self.clients=[NS(get_xid=lambda i=i:i,is_minimized=lambda i=i:i in self.minimized) for i in range(5)]
        self.m=NS(preview_cache={},windows=NS(
            windows=lambda:[w for w in self.clients if w.get_xid() not in self.closed],
            get=lambda i:None if i in self.closed else self.clients[i]),
            hub=NS(background=lambda *job:self.jobs.append(job)),close=Mock())
        self.s=Switcher.__new__(Switcher)
        self.s.m=self.m;self.s.window=object();self.s.epoch=1;self.s.pending_capture=False;self.s.capture_cursor=0
        self.s.selected=0;self.s.items=[self.entry(0),self.entry(1)]
        self.s.entries=lambda:self.s.items.copy()
        self.s.cards=[self.card(),self.card(y=100)];self.s.drawings=[Mock(),Mock()]
        self.s.flow=NS(get_mapped=lambda:True)
        self.s.scroll=NS(get_vadjustment=lambda:NS(get_value=lambda:0,get_page_size=lambda:200))
        self.s.build_cards=Mock();self.s.highlight=Mock()
    def entry(self,i):return dict(key=('window',i),members=[(i,(0,0,1,1))],title=str(i),subtitle='Window')
    def card(self,y=0,mapped=True,visible=True):
        return NS(get_mapped=lambda:mapped,get_parent=lambda:NS(get_child_visible=lambda:visible,
            get_allocation=lambda:NS(y=y,height=100)))
    def finish(self,data=None):self.jobs[-1][1](png() if data is None else data)
    def test_close_skips_queued_capture_and_late_result(self):
        self.s.capture();capture,done,_=self.jobs[0]
        self.s.window=None;self.s.epoch+=1
        with patch('switcher.subprocess.run') as child:self.assertEqual(capture(),b'')
        child.assert_not_called();done(png())
        self.assertFalse(self.m.preview_cache);self.assertFalse(self.s.capture())
    def test_minimized_closed_and_scrolled_out_results_are_discarded(self):
        for change in (lambda:self.minimized.add(0),lambda:self.closed.add(0),lambda:self.s.cards.__setitem__(0,self.card(y=200))):
            self.setUp();self.s.capture();change();self.finish()
            self.assertFalse(self.m.preview_cache)
    def test_visible_targets_exclude_minimized_and_boundary_cards(self):
        self.s.items=[self.entry(i) for i in range(5)]
        self.s.cards=[self.card(y=-100),self.card(y=200),self.card(mapped=False),self.card(),self.card()]
        self.minimized.add(3)
        self.s.capture();self.finish()
        self.assertEqual(list(self.m.preview_cache),[4])
    def test_group_members_are_deduplicated_and_hidden_groups_skipped(self):
        group=dict(key=('group','token'),members=[(0,(0,0,1,1)),(1,(1,0,1,1))],title='Group',subtitle='')
        self.s.items=[self.entry(0),group,self.entry(2)]
        self.s.cards=[self.card(),self.card(y=100),self.card(visible=False)]
        for _ in range(2):self.s.capture();self.finish()
        self.assertEqual(list(self.m.preview_cache),[0,1])
    def test_reopen_waits_for_pending_then_rejects_old_result(self):
        self.s.capture();old=self.jobs[0];self.s.epoch+=2
        self.s.capture();self.assertEqual(len(self.jobs),1)
        old[1](png());self.assertFalse(self.m.preview_cache)
        self.s.capture();self.finish();self.assertEqual(len(self.m.preview_cache),1)
    def test_decode_limits_failure_retry_and_cache_eviction(self):
        self.s.capture();self.jobs[-1][2]('timeout');self.assertFalse(self.s.pending_capture)
        valid=png();oversized=valid[:16]+struct.pack('!II',481,280)+valid[24:]
        self.s.capture();self.finish(oversized);self.assertFalse(self.m.preview_cache)
        self.m.preview_cache={i:None for i in range(2,38)}
        self.s.capture();self.finish();self.assertEqual(len(self.m.preview_cache),36)
        self.assertNotIn(2,self.m.preview_cache)
    def test_stopped_worker_pool_does_not_leave_pending_stuck(self):
        self.m.hub.background=Mock(side_effect=RuntimeError('pool closed'))
        self.s.capture();self.assertFalse(self.s.pending_capture)

if __name__=='__main__':unittest.main()
