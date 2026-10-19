"""Cancellable local transfers with explicit conflict decisions and staged files."""
import ctypes
import errno
import os
from pathlib import Path
import shutil
import stat
import tempfile
import threading
import time
import uuid


class Cancelled(Exception):pass


def signature(path):
    try:
        s=os.lstat(path)
        return (s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns)
    except FileNotFoundError:return None


def describe(path):
    info=os.lstat(path)
    return dict(path=str(path),name=path.name,size=info.st_size,modified=info.st_mtime,
                kind='folder' if stat.S_ISDIR(info.st_mode) else 'link' if stat.S_ISLNK(info.st_mode) else 'file')


def publish_new(source,target):
    """Linux renameat2 provides atomic no-clobber publication, including on USB."""
    libc=ctypes.CDLL(None,use_errno=True)
    result=libc.renameat2(-100,os.fsencode(source),-100,os.fsencode(target),1)
    if result:
        code=ctypes.get_errno()
        raise OSError(code,os.strerror(code),str(target))


class Transfer:
    def __init__(self,sources,destination,cut=False,notify=lambda data:None):
        self.id=uuid.uuid4().hex
        self.sources=[]
        for source in map(lambda p:Path(p).absolute(),sources):
            if source not in self.sources:self.sources.append(source)
        # A selected parent already includes its selected descendants.
        self.sources=[p for p in self.sources if not any(q!=p and q in p.parents for q in self.sources)]
        self.destination=Path(destination).resolve()
        self.cut=cut;self.notify=notify;self.condition=threading.Condition()
        self.cancelled=False;self.paused=False;self.answer=None;self.pending=None;self.policies={}
        self.done_bytes=0;self.total_bytes=0;self.done_items=0;self.total_items=0
        self.completed=0;self.skipped=0;self.current='';self.state='preparing';self.problem=None
        self.started=time.monotonic();self.last_emit=0;self.thread=None;self.warnings=[]

    @property
    def active(self):return self.state not in ('completed','cancelled','failed')

    def snapshot(self):
        return dict(id=self.id,state=self.state,cut=self.cut,current=self.current,destination=str(self.destination),
                    doneBytes=self.done_bytes,totalBytes=self.total_bytes,doneItems=self.done_items,totalItems=self.total_items,
                    completed=self.completed,skipped=self.skipped,paused=self.paused,problem=self.problem,
                    elapsed=max(.1,time.monotonic()-self.started),warnings=self.warnings[-10:],active=self.active)

    def emit(self,force=False):
        if force or time.monotonic()-self.last_emit>.1:
            self.last_emit=time.monotonic();self.notify(self.snapshot())

    def checkpoint(self):
        with self.condition:
            while self.paused and not self.cancelled:self.condition.wait()
            if self.cancelled:raise Cancelled()

    def cancel(self):
        with self.condition:self.cancelled=True;self.condition.notify_all()

    def pause(self,value):
        with self.condition:
            self.paused=bool(value);self.condition.notify_all()
        self.emit(True)

    def respond(self,ident,choice,apply_all=False):
        with self.condition:
            if self.answer is not None or not self.pending or ident!=self.pending['id'] or choice not in self.pending['choices']:
                raise ValueError('This transfer question is no longer active.')
            self.answer=(choice,bool(apply_all));self.condition.notify_all()

    def ask(self,problem):
        with self.condition:
            problem=dict(problem,id=uuid.uuid4().hex)
            self.pending=self.problem=problem;self.answer=None;self.state=problem['type'];self.emit(True)
            while self.answer is None and not self.cancelled:self.condition.wait()
            if self.cancelled:raise Cancelled()
            answer=self.answer;self.pending=self.problem=None;self.answer=None;self.state='running'
            self.emit(True);return answer

    def measure(self,path):
        self.checkpoint();info=path.lstat();items=1;size=0
        if stat.S_ISDIR(info.st_mode):
            with os.scandir(path) as entries:
                for entry in entries:
                    n,b=self.measure(Path(entry.path));items+=n;size+=b
        elif stat.S_ISREG(info.st_mode):size=info.st_size
        elif not stat.S_ISLNK(info.st_mode):raise ValueError('Special files cannot be copied: '+str(path))
        self.current=str(path);self.emit()
        return items,size

    def check_target(self,target):
        parent=target.parent
        if parent!=self.destination and self.destination not in parent.parents:
            raise ValueError('The destination is outside this transfer folder.')
        if parent.resolve()!=parent:
            raise ValueError('A destination folder became a link. Check the destination before retrying.')

    def target(self,source,target):
        """Resolve collisions again if the destination changes while deciding."""
        while True:
            self.checkpoint();self.check_target(target);existing=signature(target)
            if existing is None:return target,None,'new'
            info=source.lstat();folder=stat.S_ISDIR(info.st_mode)
            same=os.path.samefile(source,target) if target.exists() else False
            if same and self.cut:return target,existing,'skip'
            merge=folder and stat.S_ISDIR(existing[2]) and not same
            replace=not folder and not stat.S_ISDIR(existing[2]) and not same
            choices=['skip','keep-both']+(['merge'] if merge else ['replace'] if replace else [])
            policy='folder' if folder else 'file'
            choice=self.policies.get(policy)
            if choice not in choices:
                choice,apply_all=self.ask(dict(type='conflict',source=describe(source),target=describe(target),choices=choices))
                if apply_all:self.policies[policy]=choice
            if signature(target)!=existing:continue
            if choice=='keep-both':
                stem,suffix=(source.name,'') if folder else (source.stem,source.suffix)
                for index in range(1,10000):
                    tail=' - Copy' if index==1 else f' - Copy ({index})'
                    candidate=target.parent/(stem+tail+suffix)
                    if not os.path.lexists(candidate):return candidate,None,'new'
                raise ValueError('Too many copies with the same name in this folder.')
            return target,existing,choice

    def copy_file(self,source,target,expected,choice):
        previous=self.done_bytes
        try:self._copy_file(source,target,expected,choice)
        except BaseException:self.done_bytes=previous;raise

    def _copy_file(self,source,target,expected,choice):
        self.check_target(target)
        before=signature(source);copied=0
        with tempfile.TemporaryDirectory(prefix='.zorin11-transfer-',dir=target.parent) as temporary:
            staged=Path(temporary)/'item'
            if stat.S_ISLNK(before[2]):os.symlink(os.readlink(source),staged)
            elif stat.S_ISREG(before[2]):
                fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
                with os.fdopen(fd,'rb') as reader,staged.open('xb') as writer:
                    opened=os.fstat(reader.fileno())
                    if (opened.st_dev,opened.st_ino,opened.st_mode,opened.st_size,opened.st_mtime_ns)!=before:
                        raise ValueError('The source changed. Retry to copy its new version.')
                    try:
                        while True:
                            self.checkpoint();chunk=reader.read(1024*1024)
                            if not chunk:break
                            writer.write(chunk);copied+=len(chunk);self.done_bytes+=len(chunk);self.emit()
                        writer.flush();os.fsync(writer.fileno())
                    except BaseException:
                        self.done_bytes-=copied;raise
                shutil.copystat(source,staged,follow_symlinks=False)
            else:raise ValueError('Special files cannot be copied: '+str(source))
            try:
                if signature(source)!=before:raise ValueError('The source changed during copying. Retry to copy its new version.')
                while True:
                    self.checkpoint();self.check_target(target)
                    if signature(target)!=expected:
                        target,expected,choice=self.target(source,target)
                    if choice=='skip':self.skipped+=1;self.done_bytes-=copied;return
                    if choice=='replace':os.replace(staged,target)
                    else:
                        try:publish_new(staged,target)
                        except FileExistsError:
                            target,expected,choice=self.target(source,target);continue
                    break
            except BaseException:
                self.done_bytes-=copied;raise
        self.completed+=1
        if self.cut:
            if signature(source)==before:
                try:source.unlink()
                except OSError as error:self.warnings.append('Copied but could not remove source: '+str(error))
            else:self.warnings.append('Copied but kept changed source: '+str(source))

    def copy_item(self,source,target):
        self.checkpoint();self.current=str(source);self.emit()
        target,expected,choice=self.target(source,target)
        if choice=='skip':self.skipped+=1;self.done_items+=1;return
        if source.is_dir() and not source.is_symlink():
            if choice!='merge':
                try:target.mkdir()
                except FileExistsError:return self.copy_item(source,target)
            # Never traverse a destination link presented as a directory.
            if target.is_symlink():raise ValueError('The destination folder became a link. Retry after checking it.')
            with os.scandir(source) as entries:
                children=[Path(e.path) for e in entries]
            for child in children:self.copy_with_recovery(child,target/child.name)
            if choice!='merge':
                try:shutil.copystat(source,target,follow_symlinks=False)
                except OSError as error:self.warnings.append('Folder metadata could not be preserved: '+str(error))
            if self.cut:
                try:source.rmdir()
                except OSError as error:
                    if error.errno not in (errno.ENOTEMPTY,errno.EEXIST):raise
            self.completed+=1
        else:self.copy_file(source,target,expected,choice)
        self.done_items+=1;self.emit()

    def copy_with_recovery(self,source,target):
        while True:
            try:self.copy_item(source,target);return
            except Cancelled:raise
            except (OSError,ValueError) as error:
                choice,_=self.ask(dict(type='error',message=str(error),source={'path':str(source),'name':source.name},
                                       target={'path':str(target),'name':target.name},choices=['retry','skip']))
                if choice=='skip':self.skipped+=1;self.done_items+=1;return

    def run(self):
        try:
            if not self.destination.is_dir():raise ValueError('Choose an available destination folder.')
            if not self.sources:raise ValueError('Copy files before pasting.')
            for source in self.sources:
                real=source.resolve()
                if source.is_dir() and (real==self.destination or real in self.destination.parents):
                    raise ValueError('A folder cannot be pasted inside itself.')
                n,b=self.measure(source);self.total_items+=n;self.total_bytes+=b
            self.state='running';self.started=time.monotonic();self.emit(True)
            for source in self.sources:self.copy_with_recovery(source,self.destination/source.name)
            self.state='completed'
        except Cancelled:self.state='cancelled'
        except Exception as error:self.state='failed';self.problem={'message':str(error)}
        finally:self.paused=False;self.pending=None;self.emit(True)

    def start(self):
        self.thread=threading.Thread(target=self.run,name='explorer-transfer',daemon=True)
        self.thread.start()
