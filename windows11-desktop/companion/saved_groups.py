"""Portable Snap Group recipes: installed desktop IDs and normalized rectangles.

No XIDs, process command lines, window titles or document contents are persisted.
Launching always resolves a currently installed desktop entry through Gio.
"""
import copy
import json
import math
import os
from pathlib import Path
import re
import shlex
import tempfile
import time
import uuid
import gi
gi.require_version("Gdk","3.0")
from gi.repository import Gio, Gdk, GLib


def validate(data):
    if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('groups'),list) or len(data['groups'])>40:
        raise ValueError('Unsupported saved groups file; the original has been preserved.')
    ids=set()
    for group in data['groups']:
        if not isinstance(group,dict) or not re.fullmatch('[a-f0-9]{32}',str(group.get('id',''))) or group['id'] in ids:raise ValueError('Invalid saved group identity.')
        ids.add(group['id'])
        if not isinstance(group.get('name'),str) or not 1<=len(group['name'])<=80:raise ValueError('Invalid group name.')
        if not isinstance(group.get('desktop',''),str) or len(group.get('desktop',''))>80:raise ValueError('Invalid desktop identity.')
        members=group.get('members')
        if not isinstance(members,list) or not 2<=len(members)<=6:raise ValueError('A saved group needs two to six windows.')
        for member in members:
            if not isinstance(member,dict):raise ValueError('Invalid saved app.')
            app=member.get('app','');wmclass=member.get('class','');rect=member.get('rect')
            if not isinstance(app,str) or not app.endswith('.desktop') or len(app)>240 or any(c in app for c in ('/','\\','\x00','\n')):raise ValueError('Invalid application ID.')
            if not isinstance(wmclass,str) or not wmclass or len(wmclass)>200:raise ValueError('Invalid window class.')
            if not isinstance(rect,list) or len(rect)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in rect):raise ValueError('Invalid saved geometry.')
            x,y,w,h=rect
            if not (0<=x<1 and 0<=y<1 and 0<w<=1 and 0<h<=1 and x+w<=1.001 and y+h<=1.001):raise ValueError('Layout must fit one display.')
    return data


class Recipes:
    def __init__(self,path):
        self.path=Path(path);self.error='';self.revision=0
        try:
            if self.path.exists() and self.path.stat().st_size>256000:raise ValueError('Saved groups file is too large.')
            self.data=validate(json.loads(self.path.read_text())) if self.path.exists() else {'version':1,'groups':[]}
        except (OSError,ValueError) as error:self.data={'version':1,'groups':[]};self.error=str(error)

    @property
    def groups(self):return self.data['groups']

    def write(self,data):
        if self.error:raise ValueError(self.error)
        validate(data);self.path.parent.mkdir(parents=True,exist_ok=True)
        fd,temp=tempfile.mkstemp(prefix='.snap-groups-',dir=self.path.parent)
        try:
            with os.fdopen(fd,'w') as stream:
                json.dump(data,stream,indent=2,ensure_ascii=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
            os.replace(temp,self.path)
        finally:
            if os.path.exists(temp):os.unlink(temp)
        self.data=data;self.revision+=1

    def put(self,members,desktop='',ident=None,name=None):
        data=copy.deepcopy(self.data)
        old=next((g for g in data['groups'] if g['id']==ident),None)
        if not old:old=next((g for g in data['groups'] if g['members']==members and g.get('desktop','')==desktop),None)
        if old:ident=old['id'];name=name or old['name'];data['groups'].remove(old)
        elif len(data['groups'])>=40:raise ValueError('Saved groups is full. Remove a group before saving another.')
        ident=ident or uuid.uuid4().hex
        data['groups'].insert(0,dict(id=ident,name=(name or 'Snap group').strip()[:80] or 'Snap group',desktop=desktop,members=members))
        self.write(data);return ident

    def rename(self,ident,name):
        data=copy.deepcopy(self.data);group=next((g for g in data['groups'] if g['id']==ident),None)
        if not group:raise ValueError('That saved group no longer exists.')
        group['name']=name.strip()[:80]
        if not group['name']:raise ValueError('Enter a group name.')
        self.write(data)

    def remove(self,ident):
        data=copy.deepcopy(self.data);data['groups']=[g for g in data['groups'] if g['id']!=ident];self.write(data)


def catalog():
    return {a.get_id():a for a in Gio.AppInfo.get_all() if isinstance(a,Gio.DesktopAppInfo) and a.should_show()}


def normalize(value):return re.sub('[^a-z0-9]','',(value or '').casefold())


def application_id(w):
    """GNOME's desktop identity is stronger than shared toolkit window classes."""
    try:return w.get_application_id() or ''
    except AttributeError:return ''  # libwnck/X11 has no equivalent method.


def matches_member(w,member):
    ident=application_id(w)
    if ident:return ident==member['app']
    return normalize(w.get_class_group_name())==normalize(member['class'])


def identify(w,apps):
    ident=application_id(w)
    if ident in apps:return ident
    cls=normalize(w.get_class_group_name());instance=normalize(w.get_class_instance_name().split(' (',1)[0])
    candidates=[]
    for ident,app in apps.items():
        wm=normalize(app.get_startup_wm_class());stem=normalize(ident.removesuffix('.desktop'))
        try:exe=normalize(Path(shlex.split(app.get_executable() or '')[0]).name)
        except (ValueError,IndexError):exe=''
        score=100 if wm and wm in (cls,instance) else 80 if exe and exe in (cls,instance) else 60 if stem in (cls,instance) else 0
        if score:candidates.append((score,ident))
    if not candidates:return None
    best=max(s for s,_ in candidates);ids=sorted(i for s,i in candidates if s==best)
    # These companion launchers share a host process with other surfaces.
    for preferred in ('zorin11-explorer.desktop','zorin11-settings.desktop','zorin11-terminal.desktop'):
        if preferred in ids:return preferred
    commands={apps[i].get_commandline() for i in ids}
    return ids[0] if len(ids)==1 or len(commands)==1 else None


class SavedGroups:
    def __init__(self,m):
        self.m=m;self.store=Recipes(m.config/'snap-groups.json');self.operation=None;self.last_error=self.store.error

    def close(self):self.cancel()

    def capture(self,group,ident=None,overrides=None,name=None):
        apps=catalog();members=[]
        for xid,rect in group:
            w=self.m.windows.get(xid)
            if not w:raise ValueError('A member window has closed.')
            app=(overrides or {}).get(xid) or identify(w,apps)
            if app not in apps:raise ValueError('Choose a launchable app for '+w.get_name()+'.')
            members.append(dict(app=app,**{'class':w.get_class_group_name()},rect=rect))
        left=min(r['rect'][0] for r in members);top=min(r['rect'][1] for r in members)
        right=max(r['rect'][0]+r['rect'][2] for r in members);bottom=max(r['rect'][1]+r['rect'][3] for r in members)
        area=Gdk.Display.get_default().get_monitor_at_point((left+right)//2,(top+bottom)//2).get_workarea()
        if left<area.x-4 or top<area.y-4 or right>area.x+area.width+4 or bottom>area.y+area.height+4:
            raise ValueError('Save a layout on one display; it will scale to the destination screen.')
        for member in members:
            x,y,w,h=member['rect'];x=max(0,x-area.x);y=max(0,y-area.y)
            member['rect']=[round(x/area.width,6),round(y/area.height,6),round(min(w,area.width-x)/area.width,6),round(min(h,area.height-y)/area.height,6)]
        desktop=self.m.snap_groups.desktop(group)
        uid=next((d['uid'] for d in self.m.desktops.items() if d['id']==desktop),'')
        title=name or (None if ident else ' + '.join(dict.fromkeys(apps[r['app']].get_display_name() for r in members)))
        group.saved_id=self.store.put(members,uid,ident,title);self.last_error='';return group.saved_id

    def automatic(self,group,ident=None):
        try:self.capture(group,ident)
        except (OSError,ValueError) as error:self.last_error=str(error)

    def cancel(self):
        operation=self.operation;self.operation=None
        if operation and operation.get('timer'):GLib.source_remove(operation['timer'])
        # Launched applications stay open; cancellation only stops matching and
        # placement. Never terminate an app the user might already be editing.

    def restore(self,ident,notify):
        if self.operation or self.m.desktops.busy:raise ValueError('Wait for the current restore to finish.')
        recipe=next((g for g in self.store.groups if g['id']==ident),None)
        if not recipe:raise ValueError('That saved group no longer exists.')
        recipe=copy.deepcopy(recipe);apps=catalog()
        missing=[r['app'] for r in recipe['members'] if r['app'] not in apps]
        if missing:raise ValueError('Install these apps first: '+', '.join(dict.fromkeys(missing)))
        items=self.m.desktops.items();target=next((d['id'] for d in items if d['uid']==recipe.get('desktop')),self.m.desktops.current())
        area=self.m.area(self.m.windows.active());ax,ay,aw,ah=area
        rects=[(ax+round(r['rect'][0]*aw),ay+round(r['rect'][1]*ah),max(1,round(r['rect'][2]*aw)),max(1,round(r['rect'][3]*ah))) for r in recipe['members']]
        op={'recipe':recipe,'apps':apps,'target':target,'rects':rects,'assigned':{},'launched':set(),'deadline':time.monotonic()+30,'timer':0,'notify':notify,'phase':'matching','started':False}
        self.operation=op
        if self.m.desktops.current()!=target:self.m.desktops.switch(target)
        notify('Opening apps…',False)
        def poll():
            if self.operation is not op:return False
            try:
                if self.m.desktops.current()!=target:
                    if op['started']:raise ValueError('Desktop changed. Restore stopped; apps already opened stay open.')
                    if time.monotonic()>op['deadline']:raise ValueError('The target desktop did not become available.')
                    return True
                op['started']=True
                if op['phase']=='placing':return self.finish_placement(op)
                live=self.m.windows.windows();used=set(op['assigned'].values())
                # Reuse each matching window once, preferring this desktop and
                # MRU order. A matching window on another desktop is left there.
                for index,member in enumerate(recipe['members']):
                    if index in op['assigned']:
                        if not self.m.windows.get(op['assigned'][index]):raise ValueError('A matched window closed. You can retry the saved group.')
                        continue
                    matches=[w for w in live if w.get_xid() not in used and self.m.desktops.on(w,target)
                             and matches_member(w,member)]
                    if matches:
                        xid=matches[0].get_xid();op['assigned'][index]=xid;used.add(xid);continue
                    if index not in op['launched']:
                        # Launch one missing window at a time for each app. This
                        # avoids repeated launches while an app is still starting.
                        waiting=any(recipe['members'][i]['app']==member['app'] and i not in op['assigned'] for i in op['launched'])
                        if waiting:continue
                        if any(not self.m.desktops.on(w,target) and matches_member(w,member) for w in live):
                            raise ValueError(apps[member['app']].get_display_name()+' is open on another desktop. Move the desired window here, then retry.')
                        context=Gdk.Display.get_default().get_app_launch_context();context.set_timestamp(self.m.windows.timestamp())
                        if not apps[member['app']].launch([],context):raise ValueError('Could not open '+apps[member['app']].get_display_name()+'.')
                        op['launched'].add(index)
                if len(op['assigned'])==len(recipe['members']):
                    windows=[self.m.windows.get(op['assigned'][i]) for i in range(len(recipe['members']))]
                    for w,rect in zip(windows,rects):
                        if any(a>b for a,b in zip(self.m.windows.minimum(w),rect[2:])):raise ValueError('An app needs more space than this layout allows on this screen.')
                        if w.is_minimized():w.unminimize(self.m.windows.timestamp())
                    if not all(self.m.windows.can_snap(w) and not w.is_minimized() for w in windows):
                        if time.monotonic()>op['deadline']:raise ValueError('An app did not become resizable in time.')
                        return True
                    op['phase']='placing';op['deadline']=time.monotonic()+4
                    placements=[(op['assigned'][i],rect) for i,rect in enumerate(rects)]
                    op['placements']=placements
                    for xid,rect in placements:self.m.windows.place(xid,rect)
                    notify('Restoring layout…',False);return True
                if time.monotonic()>op['deadline']:
                    names=[apps[r['app']].get_display_name() for i,r in enumerate(recipe['members']) if i not in op['assigned']]
                    raise ValueError('Still waiting for '+', '.join(names)+'. Open the needed windows, then retry. Some apps use a single window.')
                return True
            except (ValueError,RuntimeError,GLib.Error) as error:
                self.operation=None;op['timer']=0;notify(str(error),True);return False
        op['timer']=GLib.timeout_add(150,poll)

    def finish_placement(self,op):
        settled=True
        for xid,rect in op['placements']:
            w=self.m.windows.get(xid)
            if not w:raise ValueError('A window closed while the layout was being restored.')
            if any(abs(a-b)>12 for a,b in zip(w.get_geometry(),rect)):settled=False
        if not settled and time.monotonic()<op['deadline']:return True
        if not settled:raise ValueError('An app or window manager constrained the layout. Your apps remain open; the saved layout is unchanged.')
        # Build fresh session tokens only from the newly matched live XIDs.
        self.m.snap_groups.remember(op['placements'],persist=False)
        group=next((g for g in self.m.groups if list(g)==op['placements']),None)
        if not group:raise ValueError('Apps restored, but the live group could not be registered. Retry the saved group.')
        group.saved_id=op['recipe']['id']
        self.operation=None;op['timer']=0;op['notify']('Layout restored.',True)
        return False
