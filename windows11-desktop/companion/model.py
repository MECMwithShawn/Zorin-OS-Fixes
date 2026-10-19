"""Persistence and ordering for the local desktop companion."""
import copy
import json
import os
from pathlib import Path
import tempfile
import uuid


def initial_state(app_ids, home):
    preferred = ['brave-browser.desktop', 'firefox.desktop', 'org.mozilla.firefox.desktop',
        'zorin11-explorer.desktop', 'zorin11-computer.desktop', 'org.gnome.Software.desktop',
        'zorin11-settings.desktop' if 'zorin11-settings.desktop' in app_ids else 'xfce-settings-manager.desktop', 'libreoffice-writer.desktop',
        'libreoffice-calc.desktop', 'org.gnome.TextEditor.desktop',
        'org.gnome.Calculator.desktop', 'org.gnome.Evince.desktop',
        'xfce4-screenshooter.desktop', 'org.gnome.Rhythmbox3.desktop',
        'org.xfce.ristretto.desktop', 'zorin11-terminal.desktop', 'zorin11-powershell.desktop',
        'zorin11-effects.desktop']
    pins = [i for i in preferred if i in app_ids]
    return {'version': 1, 'pins': pins, 'recent': [], 'groups_visible': True,
        'groups': [
            {'id': 'everyday', 'title': 'Everyday', 'x': 36, 'y': 72,
             'width': 380, 'height': 280, 'collapsed': False, 'folder': None,
             'items': [{'kind': 'app', 'id': i} for i in pins[:6]]},
            {'id': 'folders', 'title': 'Quick folders', 'x': 440, 'y': 72,
             'width': 380, 'height': 280, 'collapsed': False, 'folder': None,
             'items': [{'kind': 'path', 'path': str(p)} for p in
                       [home, home/'Documents', home/'Downloads', home/'Pictures'] if p.exists()]}
        ]}


class Store:
    def __init__(self, path, app_ids, home):
        self.path = Path(path)
        self.app_ids = set(app_ids)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
            if self.state.get('version') != 1 or not isinstance(self.state.get('groups'), list):
                raise ValueError('Unsupported desktop layout file; the original has been preserved.')
        else:
            self.state = initial_state(app_ids, home)
            self.save()
        self.state.setdefault('start_folders',{})

    def save(self):
        content = json.dumps(self.state, ensure_ascii=False, indent=2) + '\n'
        fd, temp = tempfile.mkstemp(prefix='.layout-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def pin(self, app_id, pinned):
        self._check_apps([app_id])
        self._detach_start_app(app_id)
        pins = self.state['pins']
        if pinned and app_id not in pins:
            pins.append(app_id)
        if not pinned and app_id in pins:
            pins.remove(app_id)
        self.save()

    def _check_apps(self, apps):
        if not isinstance(apps,list) or not apps or any(not isinstance(a,str) or a not in self.app_ids for a in apps):
            raise ValueError('Choose installed applications for this folder.')

    def _detach_start_app(self, app_id):
        for ident,folder in list(self.state['start_folders'].items()):
            folder['apps']=[a for a in folder['apps'] if a!=app_id]
            if not folder['apps']:
                del self.state['start_folders'][ident]
                self.state['pins']=[p for p in self.state['pins'] if p!=ident]

    @staticmethod
    def _folder_name(name):
        if not isinstance(name,str) or not name.strip() or len(name.strip())>60 or any(ord(c)<32 for c in name):
            raise ValueError('Enter a folder name of 1–60 characters.')
        return name.strip()

    def start_folder(self, ident):
        if ident not in self.state['start_folders']:raise ValueError('This Start folder no longer exists.')
        return self.state['start_folders'][ident]

    def create_start_folder(self, apps, name='Folder'):
        self._check_apps(apps)
        apps=list(dict.fromkeys(apps));name=self._folder_name(name)
        if len(apps)<2:raise ValueError('Choose two different apps to create a folder.')
        for app in apps:self._detach_start_app(app)
        before=self.state['pins']
        target=before.index(apps[0]) if apps[0] in before else len(before)
        index=sum(p not in apps for p in before[:target])
        self.state['pins']=[p for p in self.state['pins'] if p not in apps]
        ident='folder:'+uuid.uuid4().hex[:12]
        self.state['start_folders'][ident]={'name':name,'apps':apps}
        self.state['pins'].insert(min(index,len(self.state['pins'])),ident)
        self.save();return ident

    def rename_start_folder(self, ident, name):
        folder=self.start_folder(ident);name=self._folder_name(name)
        folder['name']=name;self.save()

    def move_to_start_folder(self, app_id, ident):
        self._check_apps([app_id]);folder=self.start_folder(ident)
        if app_id in folder['apps']:return
        self._detach_start_app(app_id)
        self.state['pins']=[p for p in self.state['pins'] if p!=app_id]
        folder['apps'].append(app_id);self.save()

    def reorder_start_folder(self, ident, app_id, target_id):
        apps=self.start_folder(ident)['apps']
        if app_id in apps and target_id in apps and app_id!=target_id:
            apps.remove(app_id);apps.insert(apps.index(target_id),app_id);self.save()

    def remove_start_folder(self, ident):
        folder=self.start_folder(ident)
        index=self.state['pins'].index(ident)
        self.state['pins'][index:index+1]=folder['apps']
        del self.state['start_folders'][ident];self.save()

    def reorder(self, app_id, target_id):
        pins = self.state['pins']
        if app_id not in pins or target_id not in pins or app_id == target_id:
            return
        pins.remove(app_id)
        pins.insert(pins.index(target_id), app_id)
        self.save()

    def used(self, app_id):
        self.state['recent'] = [app_id] + [i for i in self.state['recent'] if i != app_id][:5]
        self.save()

    def group(self, group_id):
        return next(g for g in self.state['groups'] if g['id'] == group_id)

    def add_group(self, title, folder=None):
        group_id = uuid.uuid4().hex[:12]
        offset = len(self.state['groups']) * 32
        self.state['groups'].append({'id': group_id, 'title': (title.strip() or 'New group')[:60],
            'x': 60 + offset, 'y': 100 + offset, 'width': 380, 'height': 280,
            'collapsed': False, 'folder': folder, 'items': []})
        self.state['groups_visible'] = True
        self.save()
        return group_id

    def add_item(self, group_id, item):
        group = self.group(group_id)
        if group['folder']:
            raise ValueError('Folder groups mirror their folder. Add shortcuts to a regular group.')
        if item not in group['items']:
            group['items'].append(copy.deepcopy(item))
            self.save()
