import errno
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import file_transfer as ft


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'source';self.dest=self.root/'dest'
        self.source.mkdir();self.dest.mkdir()

    def job(self,names,cut=False,decide=lambda data:'keep-both'):
        events=[]
        def notify(data):
            events.append(data)
            if data['state'] in ('conflict','error'):
                answer=decide(data)
                if answer=='cancel':job.cancel()
                else:job.respond(data['problem']['id'],answer)
        job=ft.Transfer([self.source/n for n in names],self.dest,cut,notify)
        job.run();self.assertFalse(job.active);self.assertFalse(list(self.dest.rglob('.zorin11-transfer-*')))
        return job,events

    def test_keep_both_replace_and_skip_do_not_change_unselected_files(self):
        for choice in ('keep-both','replace','skip'):
            (self.source/'item.txt').write_text('new');(self.dest/'item.txt').write_text('old')
            job,_=self.job(['item.txt'],decide=lambda _,c=choice:c)
            self.assertEqual(job.state,'completed')
            self.assertEqual((self.dest/'item.txt').read_text(),'new' if choice=='replace' else 'old')
            self.assertEqual((self.source/'item.txt').read_text(),'new')
        self.assertEqual((self.dest/'item - Copy.txt').read_text(),'new')

    def test_move_merge_keeps_skipped_sources_and_unrelated_destination_files(self):
        (self.source/'folder').mkdir();(self.dest/'folder').mkdir()
        (self.source/'folder/a').write_text('A');(self.source/'folder/b').write_text('B')
        (self.dest/'folder/b').write_text('old');(self.dest/'folder/unrelated').write_text('keep')
        job,_=self.job(['folder'],True,lambda d:'merge' if d['problem']['source']['kind']=='folder' else 'skip')
        self.assertEqual(job.state,'completed');self.assertFalse((self.source/'folder/a').exists())
        self.assertTrue((self.source/'folder/b').exists());self.assertEqual((self.dest/'folder/b').read_text(),'old')
        self.assertEqual((self.dest/'folder/unrelated').read_text(),'keep')

    def test_cancel_mid_file_removes_staging_and_keeps_move_source(self):
        path=self.source/'large';path.write_bytes(b'x'*(5*1024*1024))
        job=ft.Transfer([path],self.dest,True)
        original=job.checkpoint
        def checkpoint():
            if job.done_bytes>=1024*1024:job.cancel()
            original()
        job.checkpoint=checkpoint;job.run()
        self.assertEqual(job.state,'cancelled');self.assertTrue(path.exists())
        self.assertEqual(list(self.dest.iterdir()),[]);self.assertEqual(job.done_bytes,0)

    def test_cancel_conflict_does_not_replace_existing_file(self):
        (self.source/'a').write_text('new');(self.dest/'a').write_text('keep')
        job,_=self.job(['a'],True,lambda _:'cancel')
        self.assertEqual(job.state,'cancelled');self.assertEqual((self.dest/'a').read_text(),'keep')
        self.assertTrue((self.source/'a').exists())

    def test_no_replace_option_for_same_file_or_file_folder_mismatch(self):
        (self.source/'a').write_text('new');(self.dest/'a').mkdir()
        job,events=self.job(['a'])
        self.assertNotIn('replace',next(d['problem']['choices'] for d in events if d['state']=='conflict'))
        self.assertTrue((self.dest/'a').is_dir());self.assertEqual((self.dest/'a - Copy').read_text(),'new')
        job=ft.Transfer([self.source/'a'],self.source,True);job.run()
        self.assertEqual(job.skipped,1);self.assertTrue((self.source/'a').exists())

    def test_atomic_publication_rechecks_a_late_collision(self):
        (self.source/'a').write_text('new');original=ft.publish_new;first=[True]
        def race(source,target):
            if first[0]:first[0]=False;target.write_text('arrived during copy')
            return original(source,target)
        with patch.object(ft,'publish_new',side_effect=race):job,events=self.job(['a'])
        self.assertEqual(job.state,'completed');self.assertEqual((self.dest/'a').read_text(),'arrived during copy')
        self.assertEqual((self.dest/'a - Copy').read_text(),'new')

    def test_changed_destination_requires_new_decision(self):
        (self.source/'a').write_text('new');(self.dest/'a').write_text('old');questions=[]
        def decide(data):
            questions.append(data['problem']['id'])
            if len(questions)==1:(self.dest/'a').write_text('changed while deciding')
            return 'replace' if len(questions)==1 else 'skip'
        job,_=self.job(['a'],decide=decide)
        self.assertEqual(len(questions),2);self.assertEqual((self.dest/'a').read_text(),'changed while deciding')

    def test_error_retry_and_skip_preserve_source(self):
        (self.source/'a').write_text('new');original=ft.publish_new;calls=[0]
        def fail_once(source,target):
            calls[0]+=1
            if calls[0]==1:raise PermissionError('Test destination is read-only')
            original(source,target)
        with patch.object(ft,'publish_new',side_effect=fail_once):job,_=self.job(['a'],True,lambda _:'retry')
        self.assertEqual(job.state,'completed');self.assertEqual(job.done_bytes,3)
        self.assertFalse((self.source/'a').exists())
        (self.source/'b').write_text('keep')
        with patch.object(ft,'publish_new',side_effect=OSError(errno.ENOSPC,'Disk full')):job,_=self.job(['b'],True,lambda _:'skip')
        self.assertEqual(job.skipped,1);self.assertTrue((self.source/'b').exists());self.assertFalse((self.dest/'b').exists())

    def test_symlinks_are_copied_without_following_and_self_copy_is_rejected(self):
        (self.source/'a').symlink_to('/etc/passwd')
        job,_=self.job(['a']);self.assertEqual(os.readlink(self.dest/'a'),'/etc/passwd')
        job=ft.Transfer([self.source],self.source);job.run();self.assertEqual(job.state,'failed')
        os.mkfifo(self.source/'pipe');job=ft.Transfer([self.source/'pipe'],self.dest);job.run()
        self.assertEqual(job.state,'failed')

    def test_pause_resume_and_apply_to_remaining_conflicts(self):
        for name in ('a','b'):(self.source/name).write_text('new');(self.dest/name).write_text('old')
        questions=[];job=ft.Transfer([self.source/'a',self.source/'b'],self.dest)
        def notify(data):
            if data['state']=='conflict':
                questions.append(data['problem']['id']);job.respond(data['problem']['id'],'skip',True)
        job.notify=notify;job.pause(True);job.start()
        self.assertEqual(job.done_bytes,0);job.pause(False);job.thread.join(5)
        self.assertFalse(job.thread.is_alive());self.assertEqual(len(questions),1);self.assertEqual(job.skipped,2)

    def test_source_changes_and_metadata_failure_do_not_publish_partial_content(self):
        source=self.source/'a';source.write_text('original');copystat=ft.shutil.copystat
        def changed(src,dst,**kwargs):
            source.write_text('changed while copying');return copystat(src,dst,**kwargs)
        with patch.object(ft.shutil,'copystat',side_effect=changed):job,_=self.job(['a'],True,lambda _:'skip')
        self.assertEqual(source.read_text(),'changed while copying');self.assertFalse((self.dest/'a').exists())
        self.assertEqual(job.done_bytes,0)
        with patch.object(ft.shutil,'copystat',side_effect=PermissionError('Metadata unavailable')):
            job,_=self.job(['a'],True,lambda _:'skip')
        self.assertEqual(job.done_bytes,0);self.assertFalse((self.dest/'a').exists())

    def test_changed_destination_parent_is_not_followed(self):
        source=self.source/'a';source.write_text('new')
        outside=self.root/'outside';outside.mkdir();(self.dest/'linked').symlink_to(outside,target_is_directory=True)
        job=ft.Transfer([source],self.dest)
        with self.assertRaises(ValueError):job.copy_file(source,self.dest/'linked/a',None,'new')
        self.assertEqual(list(outside.iterdir()),[])


if __name__=='__main__':unittest.main()
