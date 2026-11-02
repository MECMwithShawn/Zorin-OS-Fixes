"""Explorer's Delete action: Recycle Bin first, ask before deleting what can't go there, always refresh."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('GDK_BACKEND', 'x11')
import app
import explorer


class Dialog:
    answers = []
    def __init__(self, **kwargs): self.text = kwargs.get('text')
    def __getattr__(self, name): return lambda *a, **k: None
    def run(self): return Dialog.answers.pop(0)


class Surface:
    def __init__(self): self.sent, self.location, self.file_state, self.mode = [], '/folder', {}, 'explorer'
    def send(self, data): self.sent.append(data)


class Hub:
    file_task = app.Hub.file_task
    confirm_delete = app.Hub.confirm_delete
    dispatch = app.Hub.dispatch
    file_action = app.Hub.file_action
    def __init__(self, surface):
        self.surfaces, self.loads = {str(id(surface)): surface}, []
    def background(self, task, success, failure=None):
        try: value = task()
        except Exception as error: return failure(str(error))
        success(value)
    def load_folder(self, surface, location, hidden=False): self.loads.append(location)


class DeleteFlowTests(unittest.TestCase):
    def run_trash(self, answers, unsupported):
        surface = Surface(); hub = Hub(surface); deleted = []
        Dialog.answers = list(answers)
        with patch.object(app.Gtk, 'MessageDialog', Dialog), \
             patch.object(explorer, 'trash', return_value=unsupported), \
             patch.object(explorer, 'delete', side_effect=deleted.extend), \
             patch.object(explorer, 'online_recycle_bin', return_value='OneDrive'):
            hub.dispatch(surface, {'action': 'file-trash', 'paths': ['/folder/a', '/folder/b']})
        return surface, hub, deleted

    def test_recycled_items_refresh_the_folder(self):
        surface, hub, deleted = self.run_trash([app.Gtk.ResponseType.OK], [])
        self.assertEqual((hub.loads, deleted), (['/folder'], []))

    def test_items_without_a_recycle_bin_are_deleted_only_when_confirmed(self):
        surface, hub, deleted = self.run_trash([app.Gtk.ResponseType.OK, app.Gtk.ResponseType.OK], ['/folder/b'])
        self.assertEqual((hub.loads, deleted), (['/folder'], ['/folder/b']))
        surface, hub, deleted = self.run_trash([app.Gtk.ResponseType.OK, app.Gtk.ResponseType.CANCEL], ['/folder/b'])
        self.assertEqual((hub.loads, deleted), (['/folder'], []))

    def test_cancelling_the_first_question_changes_nothing(self):
        surface, hub, deleted = self.run_trash([app.Gtk.ResponseType.CANCEL], [])
        self.assertEqual((hub.loads, deleted), ([], []))

    def test_a_failure_still_refreshes_and_reports(self):
        surface, hub = Surface(), None; hub = Hub(surface)
        hub.file_task(surface, lambda: (_ for _ in ()).throw(OSError('Permission denied')))
        self.assertEqual(hub.loads, ['/folder'])
        self.assertIn({'type': 'error', 'message': 'Permission denied'}, surface.sent)


if __name__ == '__main__':
    unittest.main()
