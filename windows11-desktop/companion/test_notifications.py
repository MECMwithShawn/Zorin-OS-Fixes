"""GNOME notification markup is converted to text without dispatching content."""
import unittest
from unittest.mock import patch
import notifications

class NotificationTests(unittest.TestCase):
    def test_gnome_markup_and_entities_are_plain_text(self):
        rows=[{'id':'1','title':'5 < 7','body':'<b>Ready</b><br>Tom &amp; Jane <a href="file:///tmp/private">open</a>','app':'Test','appId':'test','time':100,'read':False}]
        with patch.object(notifications,'is_gnome',return_value=True),patch.object(notifications,'properties',return_value={}),patch.object(notifications,'gnome_call',return_value=rows) as bridge:
            result=notifications.snapshot()
        self.assertTrue(result['available'])
        self.assertEqual(result['entries'][0]['body'],'Ready\nTom & Jane open')
        self.assertEqual(result['entries'][0]['title'],'5 < 7')
        self.assertIn('<b>',rows[0]['body'])
        bridge.assert_called_once_with('notifications')
    def test_missing_body_and_unavailable_shell(self):
        with patch.object(notifications,'is_gnome',return_value=True),patch.object(notifications,'properties',return_value={}),patch.object(notifications,'gnome_call',return_value=[{'id':'1'}]) as bridge:
            self.assertEqual(notifications.snapshot()['entries'][0]['body'],'')
            bridge.side_effect=RuntimeError('bridge unavailable')
            self.assertFalse(notifications.snapshot()['available'])

if __name__=='__main__':unittest.main()
