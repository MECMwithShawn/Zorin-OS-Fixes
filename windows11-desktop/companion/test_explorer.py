from pathlib import Path
import tempfile
import unittest
import explorer

class ExplorerTests(unittest.TestCase):
    def test_system_drive_first_and_letters_survive_reconnect(self):
        with tempfile.TemporaryDirectory() as directory:
            registry=Path(directory)/'letters.json'
            def rows():
                return [dict(path='/media/usb',name='AXENTRA_OS',driveId='uuid:usb',removable=True),
                        dict(path='/',name='System'),dict(path='/media/os',name='OS',driveId='uuid:os')]
            drives=explorer.label_drives(rows(),registry)
            self.assertEqual([d['name'] for d in drives],['Local Disk (C:)','OS (D:)','AXENTRA_OS (E:)'])
            self.assertEqual([d['path'] for d in drives],['/','/media/os','/media/usb'])
            self.assertEqual(explorer.label_drives([rows()[0]],registry)[0]['driveLetter'],'E')
            reconnect=rows();reconnect[0]['path']='/media/renamed'
            self.assertEqual([d['driveLetter'] for d in explorer.label_drives(reconnect[::-1],registry)],['C','D','E'])

    def test_drive_letter_registry_rejects_reserved_and_duplicate_letters(self):
        with tempfile.TemporaryDirectory() as directory:
            registry=Path(directory)/'letters.json'
            registry.write_text('{"uuid:usb":"C","uuid:os":"D","old":"D"}')
            result=explorer.label_drives([dict(path='/',name='System'),
                dict(path='/media/usb',name='USB',driveId='uuid:usb')],registry)
            self.assertEqual([d['driveLetter'] for d in result],['C','E'])

    def test_listing_and_hidden_files(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            (p/'Folder').mkdir();(p/'note.txt').write_text('hello');(p/'.hidden').touch()
            data=explorer.listing(directory)
            self.assertEqual([x['name'] for x in data['entries']],['Folder','note.txt'])
            self.assertEqual(data['entries'][1]['size'],5)
            self.assertEqual(len(explorer.listing(directory,True)['entries']),3)

    def test_copy_move_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);a=p/'source';b=p/'target';a.mkdir();b.mkdir()
            source=a/'note.txt';source.write_text('source');(b/'note.txt').write_text('existing')
            result=explorer.paste([str(source)],str(b))
            self.assertEqual(Path(result[0]).name,'note - Copy.txt')
            self.assertEqual((b/'note.txt').read_text(),'existing')
            self.assertEqual(source.read_text(),'source')
            c=p/'moved';c.mkdir()
            result=explorer.paste([str(source)],str(c),True)
            self.assertFalse(source.exists());self.assertEqual(Path(result[0]).read_text(),'source')

    def test_create_rename_and_conflicts(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            explorer.create_folder(directory,'new')
            explorer.rename(str(p/'new'),'renamed')
            self.assertTrue((p/'renamed').is_dir())
            (p/'occupied').write_text('keep')
            with self.assertRaises(FileExistsError):explorer.rename(str(p/'renamed'),'occupied')
            self.assertEqual((p/'occupied').read_text(),'keep')
            for invalid in ('','..','../outside','name/child'):
                with self.assertRaises(ValueError):explorer.create_folder(directory,invalid)

    def test_recursive_copy_and_self_copy_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);src=p/'source';src.mkdir();(src/'nested').mkdir();(src/'nested/file').write_text('content')
            target=p/'target';target.mkdir()
            explorer.paste([str(src)],str(target))
            self.assertEqual((target/'source/nested/file').read_text(),'content')
            with self.assertRaises(ValueError):explorer.paste([str(src)],str(src/'nested'))

    def test_virtual_locations_are_real_paths(self):
        entries=explorer.listing('::home')['entries']+explorer.listing('::computer')['entries']
        self.assertTrue(all(Path(e['path']).exists() for e in entries))
        self.assertTrue(any(e['path']=='/' for e in entries))

if __name__=='__main__':unittest.main()
