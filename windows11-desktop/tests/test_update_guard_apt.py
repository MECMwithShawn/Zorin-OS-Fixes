"""Real APT hook ordering on private package state with a non-installing dpkg."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class AptHookTests(unittest.TestCase):
    def test_backup_precedes_dpkg_and_failure_prevents_installation(self):
        with tempfile.TemporaryDirectory(prefix='axentra-apt-fixture-') as directory:
            root = Path(directory)
            (root/'pkg/DEBIAN').mkdir(parents=True)
            (root/'pkg/DEBIAN/control').write_text(
                'Package: axentra-desktop-hook-fixture\nVersion: 1.0\nArchitecture: all\n'
                'Maintainer: Test <test@example.invalid>\nDescription: Disposable hook fixture\n')
            subprocess.run(['dpkg-deb','--build',str(root/'pkg'),str(root/'fixture.deb')],
                           check=True,capture_output=True)
            for path in ('parts','state/lists/partial','cache/archives/partial','log'):
                (root/path).mkdir(parents=True)
            for path in ('state/status','sources.list','empty.conf'):
                (root/path).write_text('')
            trace=root/'trace'
            architecture=subprocess.check_output(['dpkg','--print-architecture'],text=True).strip()
            fake=root/'dpkg'
            fake.write_text('#!/usr/bin/python3\nimport sys\nfrom pathlib import Path\n'
                'if "--print-architecture" in sys.argv:print('+repr(architecture)+')\n'
                'elif "--print-foreign-architectures" not in sys.argv:\n'
                ' with Path('+repr(str(trace))+').open("a") as f:f.write("dpkg "+repr(sys.argv[1:])+"\\n")\n')
            fake.chmod(0o755)
            for name in ('before','after'):
                path=root/name
                path.write_text('#!/bin/sh\necho '+name+' >> '+str(trace)+'\n')
                path.chmod(0o755)
            config=root/'apt.conf'
            config.write_text(f'''
Dir::Etc::parts "{root}/parts";
Dir::Etc::main "{root}/empty.conf";
Dir::Etc::sourcelist "{root}/sources.list";
Dir::Etc::sourceparts "{root}/parts";
Dir::State "{root}/state";
Dir::State::status "{root}/state/status";
Dir::Cache "{root}/cache";
Dir::Log "{root}/log";
Dir::Bin::dpkg "{fake}";
Debug::NoLocking "true";
DPkg::Pre-Invoke {{ "{root}/before"; }};
DPkg::Post-Invoke {{ "{root}/after"; }};
''')
            command=['apt-get','-y','install',str(root/'fixture.deb')]
            env=dict(os.environ,APT_CONFIG=str(config))
            result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            lines=trace.read_text().splitlines()
            self.assertEqual(lines[0],'before')
            self.assertEqual(lines[-1],'after')
            self.assertTrue(any('--unpack' in line for line in lines[1:-1]))
            self.assertEqual((root/'state/status').read_text(),'')
            trace.unlink()
            (root/'before').write_text('#!/bin/sh\necho backup-failed >> '+str(trace)+'\nexit 1\n')
            result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=20)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(trace.read_text(),'backup-failed\n')
            self.assertEqual((root/'state/status').read_text(),'')


if __name__ == '__main__':
    unittest.main()
