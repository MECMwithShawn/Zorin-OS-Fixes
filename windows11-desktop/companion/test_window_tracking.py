"""Asynchronous GNOME background tracking without a desktop or live timers."""
import unittest
from unittest.mock import patch,Mock
import gnome_bridge as g

def state(ids=(),focused=None,current=0):
    return dict(windows=[dict(id=i,focused=i==focused) for i in ids],current=current)

class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.callbacks=[];self.requests=[]
        def request(callback):
            cancel=Mock();self.callbacks.append(callback);self.requests.append(cancel);return cancel
        self.patches=[patch.object(g.GLib,'timeout_add',return_value=1),patch.object(g.GLib,'source_remove'),
                      patch.object(g,'snapshot_async',side_effect=request),patch.object(g,'call',return_value=state([1],1))]
        for p in self.patches:p.start();self.addCleanup(p.stop)

    def test_one_pending_request_and_change_events(self):
        screen=g.Screen();events=[]
        screen.connect('window-closed',lambda _,w:events.append(('closed',w.get_xid())))
        screen.connect('active-window-changed',lambda *_:events.append(('focus',)))
        screen.connect('active-workspace-changed',lambda *_:events.append(('workspace',)))
        screen.poll();screen.poll();self.assertEqual(len(self.callbacks),1)
        self.callbacks[0](state([2],2,1),None)
        self.assertEqual(events,[('closed',1),('focus',),('workspace',)])
        screen.poll();self.assertEqual(len(self.callbacks),2);screen.close()
        self.requests[-1].cancel.assert_called_once()

    def test_foreground_refresh_supersedes_old_reply(self):
        screen=g.Screen();screen.poll()
        with patch.object(g,'call',return_value=state([9],9)):screen.force_update()
        self.callbacks[0](state([],None),None)
        self.assertEqual(screen.data,state([9],9));screen.close()

    def test_failure_keeps_state_and_retry_is_allowed(self):
        screen=g.Screen();screen.poll();self.callbacks[0](None,RuntimeError('offline'))
        self.assertEqual(screen.data,state([1],1))
        screen.poll();self.assertEqual(len(self.callbacks),2);screen.close()

    def test_close_cancels_and_late_reply_does_not_emit(self):
        screen=g.Screen();event=Mock();screen.connect('window-closed',event)
        screen.poll();screen.close();screen.close()
        self.requests[0].cancel.assert_called_once()
        self.callbacks[0](state(),None);event.assert_not_called()
        self.assertFalse(screen.poll())

    def test_newly_tracked_windows_are_not_falsely_closed(self):
        closed=Mock();watch=g.LifetimeWatch(closed,Mock());watch.track([1]);watch.tick();watch.tick()
        self.assertEqual(len(self.callbacks),1)
        watch.track([1,2]);self.callbacks[0](state([1]),None)
        closed.assert_not_called();self.assertEqual(watch.ids,{1,2})
        watch.tick();self.callbacks[1](state([2]),None)
        closed.assert_called_once_with(1);self.assertEqual(watch.ids,{2});watch.close()

    def test_lifetime_error_and_cancel_retain_groups(self):
        closed=Mock();watch=g.LifetimeWatch(closed,Mock());watch.track([1]);watch.tick()
        self.callbacks[0](None,RuntimeError('offline'));self.assertEqual(watch.ids,{1})
        watch.tick();watch.close();self.callbacks[1](state(),None)
        closed.assert_not_called();self.assertFalse(watch.tick())

if __name__=='__main__':unittest.main()
