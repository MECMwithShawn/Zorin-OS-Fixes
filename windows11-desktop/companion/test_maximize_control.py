"""Regression coverage for safe native caption hit testing."""

from types import SimpleNamespace
import unittest

from maximize_control import resolve_control, valid


API = SimpleNamespace(
    Role=SimpleNamespace(FRAME='frame', PANEL='panel', PUSH_BUTTON='button',
                         GROUPING='grouping', TOOL_BAR='tool bar'),
    CoordType=SimpleNamespace(WINDOW='window'),
    StateType=SimpleNamespace(VISIBLE='visible', SHOWING='showing', ENABLED='enabled', SENSITIVE='sensitive'),
)


class Accessible:
    def __init__(self, role='', *children, name='', rect=None, attributes=None,
                 pid=0, enabled=True, description='', actions=()):
        self.role, self.children, self.name, self.rect = role, children, name, rect
        self.attributes, self.pid, self.enabled = attributes or {}, pid, enabled
        self.description, self.actions = description, actions

    def get_child_count(self):
        return len(self.children)

    def get_child_at_index(self, index):
        return self.children[index]

    def get_role(self):
        return self.role

    def get_name(self):
        return self.name

    def get_description(self):
        return self.description

    def get_action_iface(self):
        return self

    def get_n_actions(self):
        return len(self.actions)

    def get_action_name(self, index):
        return self.actions[index]

    def get_process_id(self):
        return self.pid

    def get_component_iface(self):
        return self

    def get_extents(self, coordinate):
        assert coordinate == 'window'
        return SimpleNamespace(**dict(zip(('x', 'y', 'width', 'height'), self.rect))) if self.rect else None

    def get_attributes(self):
        return self.attributes

    def get_state_set(self):
        return SimpleNamespace(contains=lambda state: self.enabled or state not in ('enabled', 'sensitive'))


class MaximizeControlTests(unittest.TestCase):
    def setUp(self):
        self.request = dict(pid=1234, title='A window', width=900, height=640, x=810, y=25)
        self.rect = (805, 10, 32, 40)
        self.maximize = Accessible('button', name='A localized label', rect=self.rect,
                                   attributes={'class': 'FrameCaptionButton', 'id': 'view_2'})
        self.frame = self.window(self.maximize)

    def window(self, *controls, name='A window', rect=(0, 0, 900, 640)):
        return Accessible('frame', Accessible('panel', Accessible('panel', *controls)),
                          name=name, rect=rect)

    def resolve(self, *frames, **override):
        return resolve_control(Accessible('', Accessible('', *frames, pid=1234)),
                               API, self.request | override)

    def test_chromium_view_id_ignores_localized_label_and_uses_exact_bounds(self):
        self.assertTrue(valid(self.request))
        self.assertEqual(self.resolve(self.frame), self.rect)
        self.assertIsNone(self.resolve(self.frame, x=837))
        self.maximize.attributes['id'] = 'view_3'
        self.assertEqual(self.resolve(self.frame), self.rect)

    def test_rejects_ambiguous_or_stale_window(self):
        self.assertIsNone(self.resolve(self.frame, self.frame))
        self.assertIsNone(self.resolve(self.frame, pid=5678))
        self.assertIsNone(self.resolve(self.frame, width=870))
        self.assertIsNone(self.resolve(self.frame, title='Another title'))

    def test_skips_web_content_and_hidden_or_unrelated_controls(self):
        self.assertIsNone(self.resolve(self.window(Accessible('document-web', self.maximize))))
        self.maximize.attributes['hidden'] = 'true'
        self.assertIsNone(self.resolve(self.frame))
        self.maximize.attributes.pop('hidden')
        self.maximize.enabled = False
        self.assertIsNone(self.resolve(self.frame))
        self.maximize.enabled = True
        self.maximize.attributes['id'] = 'view_4'
        self.assertIsNone(self.resolve(self.frame))

    @staticmethod
    def gtk_frame(*nodes, actions=('window.toggle-maximized',)):
        return Accessible('frame', *nodes, name='A window', rect=(0, 0, 900, 640),
                          attributes={'toolkit': 'GTK'}, actions=actions)

    def gtk_group(self, *, disabled=False):
        attrs = {'toolkit': 'GTK'}
        maximize = Accessible('button', name='Maximize', description='Maximize the window',
                              rect=self.rect, attributes=attrs, enabled=not disabled)
        close = Accessible('button', name='Close', description='Close the window',
                           rect=(841, 10, 32, 40), attributes=attrs)
        return Accessible('panel', maximize, close, rect=(804, 9, 72, 42), attributes=attrs)

    def test_gtk4_window_action_and_native_caption_group(self):
        group = self.gtk_group()
        header = Accessible('tool bar', group, rect=(0, 0, 900, 45))
        # Nautilus has a deep native widget tree around its titlebar.
        for _ in range(13):
            header = Accessible('panel', header, rect=(0, 0, 900, 52))
        frame = self.gtk_frame(header)
        self.assertEqual(self.resolve(frame, kind='gtk4'), self.rect)
        self.assertEqual(self.resolve(frame, kind='gtk4', y=49), self.rect)
        self.assertIsNone(self.resolve(frame, kind='gtk4', y=50))
        self.assertIsNone(self.resolve(frame, kind='gtk4', x=845))
        self.assertIsNone(self.resolve(self.gtk_frame(header, actions=()), kind='gtk4'))
        self.assertIsNone(self.resolve(self.gtk_frame(self.gtk_group(disabled=True)), kind='gtk4'))

    def test_gtk4_rejects_caption_lookalikes_and_nested_document(self):
        group = self.gtk_group()
        no_peer = Accessible('panel', group.children[0], rect=group.rect,
                             attributes=group.attributes)
        self.assertIsNone(self.resolve(self.gtk_frame(no_peer), kind='gtk4'))
        page = Accessible('document-web', group, rect=(0, 0, 900, 640))
        self.assertIsNone(self.resolve(self.gtk_frame(page), kind='gtk4'))


if __name__ == '__main__':
    unittest.main()
