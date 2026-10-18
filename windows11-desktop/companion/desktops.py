"""Desktop management over Xfwm workspaces or Compiz's horizontal viewports.

Only IDs and values survive an event-loop turn: removed libwnck objects must
never be retained by UI callbacks. Closing a desktop moves clients first and
waits for acknowledgement before reducing the count. It never closes an app.
"""
import os
import subprocess
import time
import uuid
from gi.repository import Wnck, GLib
from windowing import WindowRef


class Desktops:
    def __init__(self, multitasking):
        self.m=multitasking;self.windows=multitasking.windows
        self.screen=self.windows.screen;self.busy=False;self.stopped=False;self.pending_names=None

    @property
    def compiz(self):return 'compiz' in (self.screen.get_window_manager_name() or '').lower()

    @property
    def backend(self):return 'compiz' if self.compiz else 'xfwm4'

    def identities(self,count):
        identities=self.m.preferences.setdefault('desktop_ids',{}).setdefault(self.backend,[])
        if len(identities)!=count:
            identities[:]=identities[:count]+[uuid.uuid4().hex for _ in range(max(0,count-len(identities)))]
            self.m.save()
        return identities[:]

    def dimensions(self):
        self.screen.force_update();ws=self.screen.get_active_workspace()
        sw,sh=self.screen.get_width(),self.screen.get_height()
        return sw,sh,max(1,ws.get_width()//sw),max(1,ws.get_height()//sh)

    def items(self):
        self.screen.force_update();active=self.screen.get_active_workspace()
        if not active:return []
        names=self.m.preferences.get('desktop_names',{}).get('compiz' if self.compiz else 'xfwm4',[])
        if self.compiz:
            sw,sh,nx,ny=self.dimensions();current=active.get_viewport_x()//sw+nx*(active.get_viewport_y()//sh)
            identities=self.identities(nx*ny)
            return [dict(id=i,uid=identities[i],name=names[i] if i<len(names) else f'Desktop {i+1}',current=i==current) for i in range(nx*ny)]
        native=[w.get_name() or '' for w in self.screen.get_workspaces()]
        if native==self.pending_names:self.pending_names=None
        result=[];identities=self.identities(len(native))
        for ws in self.screen.get_workspaces():
            i=ws.get_number();name=ws.get_name() or ''
            if self.pending_names and i<len(self.pending_names):name=self.pending_names[i]
            elif not name or name.startswith('Workspace '):name=names[i] if i<len(names) else f'Desktop {i+1}'
            result.append(dict(id=i,uid=identities[i],name=name,current=i==active.get_number()))
        return result

    def current(self):return next((d['id'] for d in self.items() if d['current']),0)

    def shared(self,w):return w.is_pinned() or (self.compiz and w.is_sticky())

    def desktop_for(self,w):
        if self.shared(w):return None
        ws=w.get_workspace()
        if not ws:return None
        if not self.compiz:return ws.get_number()
        sw,sh,nx,ny=self.dimensions();x,y,width,height=w.get_geometry()
        col=max(0,min(nx-1,int((x+ws.get_viewport_x()+width/2)//sw)))
        row=max(0,min(ny-1,int((y+ws.get_viewport_y()+height/2)//sh)))
        return col+row*nx

    def on(self,w,index):return self.desktop_for(w) in (None,index)

    def switch(self,index):
        if index not in [d['id'] for d in self.items()]:raise ValueError('That desktop no longer exists.')
        if self.compiz:
            sw,sh,nx,_=self.dimensions();self.screen.move_viewport(index%nx*sw,index//nx*sh)
        else:self.screen.get_workspace(index).activate(self.windows.timestamp())

    def move(self,xid,index):
        if index not in [d['id'] for d in self.items()]:raise ValueError('That desktop no longer exists.')
        w=WindowRef(self.windows,xid)
        if self.shared(w):raise ValueError('This window is visible on every desktop.')
        old=self.desktop_for(w)
        if old==index:return
        if self.compiz:
            sw,sh,nx,_=self.dimensions();x,y,width,height=w.get_geometry()
            w.set_geometry(Wnck.WindowGravity.STATIC,Wnck.WindowMoveResizeMask.X|Wnck.WindowMoveResizeMask.Y,
                           x+(index%nx-old%nx)*sw,y+(index//nx-old//nx)*sh,width,height)
        else:w.move_to_workspace(self.screen.get_workspace(index))

    def remember_names(self,names,identities=None):
        if identities is not None:self.m.preferences.setdefault('desktop_ids',{})[self.backend]=identities[:]
        self.m.preferences.setdefault('desktop_names',{})['compiz' if self.compiz else 'xfwm4']=names
        self.m.save()
        if not self.compiz:
            self.pending_names=names[:]
            for i,name in enumerate(names):
                ws=self.screen.get_workspace(i)
                if ws:ws.change_name(name)

    def changed(self):
        backgrounds=getattr(self.m,'backgrounds',None)
        if backgrounds:backgrounds.request()

    def rename(self,index,name):
        if self.busy:raise ValueError('Wait for the desktop change to finish.')
        name=' '.join(name.split())[:40]
        if not name:raise ValueError('Enter a desktop name.')
        items=self.items()
        if not 0<=index<len(items):raise ValueError('That desktop no longer exists.')
        names=[d['name'] for d in items];names[index]=name;self.remember_names(names)

    def wait(self,condition,success,failure):
        deadline=time.monotonic()+8
        def poll():
            if self.stopped:return False
            try:
                self.screen.force_update()
                if condition():success();return False
                if time.monotonic()<deadline:return True
                failure('The window manager did not finish the desktop change. Your apps remain open.')
            except Exception as error:failure(str(error))
            return False
        GLib.timeout_add(60,poll)

    def count(self,value,success,failure):
        def requested(*_):self.wait(lambda:len(self.items())==value,success,failure)
        if self.compiz:
            # Write to the same private profile used by effects.py. ccp reloads
            # it live; do not restart Compiz or touch its wobble settings.
            env=dict(os.environ,XDG_CONFIG_HOME=str(self.m.config/'compiz'),GSETTINGS_BACKEND='keyfile',GTK_CSD='0')
            code="import compizconfig; c=compizconfig.Context(); c.Plugins['core'].Screen['hsize'].Value=int(__import__('sys').argv[1]); c.Write()"
            def task():subprocess.run(['/usr/bin/python3','-c',code,str(value)],env=env,capture_output=True,timeout=6,check=True)
            self.m.hub.background(task,requested,lambda e:failure(str(e)))
        else:self.screen.change_workspace_count(value);requested()

    def begin(self,done):
        if self.busy:done('A desktop change is already in progress.',None);return False
        if self.compiz and self.dimensions()[3]!=1:
            done('Creating, closing and reordering desktops use a single row. Set vertical size to 1 in Compiz first; switching and moving windows still work.',None);return False
        self.busy=True;return True

    def create(self,done,move_xid=None):
        if not self.begin(done):return
        items=self.items();index=len(items);names=[d['name'] for d in items];identities=[d['uid'] for d in items]+[uuid.uuid4().hex]
        def fail(error):self.busy=False;done(error,None)
        if index>=32:fail('You can use up to 32 desktops.');return
        number=1
        while f'Desktop {number}' in names:number+=1
        names.append(f'Desktop {number}')
        def finish():
            self.remember_names(names,identities);self.busy=False;self.changed()
            if move_xid:
                try:self.move(move_xid,index)
                except ValueError as error:done(str(error),index);return
            done(None,index)
        self.count(index+1,finish,fail)

    def remove(self,index,done):
        if not self.begin(done):return
        items=self.items();n=len(items);current=self.current()
        def fail(error):self.busy=False;done(error,None)
        if n<=1:fail('Keep at least one desktop.');return
        if not 0<=index<n:fail('That desktop no longer exists.');return
        def destination(old):return max(0,index-1) if old==index else old-1 if old>index else old
        target=destination(current);names=[d['name'] for d in items];names.pop(index)
        identities=[d['uid'] for d in items];identities.pop(index)
        # Include utility/transient windows omitted from Task View, excluding
        # desktop/panel surfaces and windows explicitly present everywhere.
        refs=[WindowRef(self.windows,w.get_xid()) for w in self.screen.get_windows()
              if w.get_window_type() not in (Wnck.WindowType.DESKTOP,Wnck.WindowType.DOCK)]
        pending=[]
        try:
            for w in refs:
                old=self.desktop_for(w)
                if old is not None and destination(old)!=old:
                    pending.append((w.get_xid(),destination(old)));self.move(w.get_xid(),destination(old))
        except ValueError as error:fail(str(error));return
        def moved():
            live={w.get_xid() for w in self.screen.get_windows()}
            return all(xid not in live or self.desktop_for(WindowRef(self.windows,xid))==dest for xid,dest in pending)
        def finish():
            self.remember_names(names,identities);self.busy=False;self.changed();done(None,target)
        def shrink():
            if len(self.items())!=n:
                fail('The desktop layout changed in another tool. Your apps remain open; try again.');return
            self.switch(target)
            self.wait(lambda:self.current()==target,lambda:self.count(n-1,finish,fail),fail)
        self.wait(moved,shrink,fail)

    def reorder(self,source,target,done):
        if not self.begin(done):return
        items=self.items();n=len(items);current=self.current()
        def fail(error):self.busy=False;self.changed();done(error,None)
        if not 0<=source<n or not 0<=target<n:fail('That desktop no longer exists.');return
        if source==target:self.busy=False;done(None,target);return
        order=list(range(n));order.insert(target,order.pop(source))
        destination={old:new for new,old in enumerate(order)}
        # Snapshot all memberships before moving a client. Transient dialogs
        # can follow their parent, so do not derive a second move from a new
        # position partway through the permutation.
        plan=[]
        initial_viewport=(self.screen.get_active_workspace().get_viewport_x(),self.screen.get_active_workspace().get_viewport_y())
        refs=[WindowRef(self.windows,w.get_xid()) for w in self.screen.get_windows()
              if w.get_window_type() not in (Wnck.WindowType.DESKTOP,Wnck.WindowType.DOCK)]
        for w in refs:
            old=self.desktop_for(w)
            if old is not None and destination[old]!=old:
                plan.append((w.get_xid(),old,destination[old],tuple(w.get_geometry())))
        def relocate(mapping):
            live={w.get_xid() for w in self.screen.get_windows()}
            sw,sh,nx,_=self.dimensions()
            viewport=(self.screen.get_active_workspace().get_viewport_x(),self.screen.get_active_workspace().get_viewport_y())
            for xid,old,new,rect in plan:
                if xid not in live:continue
                w=WindowRef(self.windows,xid);dest=new if mapping else old
                if self.compiz:
                    x,y,width,height=rect
                    w.set_geometry(Wnck.WindowGravity.STATIC,Wnck.WindowMoveResizeMask.X|Wnck.WindowMoveResizeMask.Y,
                        x+(dest%nx-old%nx)*sw+initial_viewport[0]-viewport[0],
                        y+(dest//nx-old//nx)*sh+initial_viewport[1]-viewport[1],width,height)
                else:w.move_to_workspace(self.screen.get_workspace(dest))
        def moved():
            if len(self.items())!=n:raise ValueError('The desktop layout changed in another tool. Your apps remain open.')
            live={w.get_xid() for w in self.screen.get_windows()}
            return all(x not in live or self.desktop_for(WindowRef(self.windows,x))==new for x,_,new,_ in plan)
        def rollback(error):
            # No desktop is removed. If a WM refuses a move, keep labels in
            # their old order and put surviving clients back where they began.
            try:relocate(False)
            except Exception:error+=' Some windows could not be returned to their original desktop.'
            fail(error)
        def finish():
            self.remember_names([items[i]['name'] for i in order],[items[i]['uid'] for i in order])
            self.switch(destination[current])
            def activated():self.busy=False;self.changed();done(None,target)
            self.wait(lambda:self.current()==destination[current],activated,fail)
        try:relocate(True)
        except Exception as error:rollback(str(error));return
        self.wait(moved,finish,rollback)
