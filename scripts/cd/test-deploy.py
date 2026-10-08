#!/usr/bin/env python3
"""Exercise real deploy orchestration against fake transports, without touching AWS."""
import hashlib
import fcntl
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('deploy.sh').resolve()
SHA = 'a' * 40


class DeployTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        binaries = self.root / 'bin'
        binaries.mkdir()
        self.log = self.root / 'calls'
        self.env = {**os.environ, 'PATH': str(binaries) + ':' + os.environ['PATH'],
                    'LYNK_RELEASE_ROOT': str(self.root / 'state'), 'FIXTURE': str(self.root),
                    'FAIL_MODE': ''}
        fake = '''#!/usr/bin/env python3
import os,sys,pathlib,json,shutil
name=pathlib.Path(sys.argv[0]).name
root=pathlib.Path(os.environ['FIXTURE'])
args=sys.argv[1:]
with open(root/'calls','a') as f: f.write(name+' '+' '.join(args)+'\\n')
if name=='aws': shutil.copy(root/pathlib.Path(args[2]).name,args[3])
if name=='df': print('Avail\\n2097152')
if name=='helm':
 if args[0]=='history': print(json.dumps([{'revision':7,'status':'deployed'}]))
 if args[0]=='upgrade' and os.environ['FAIL_MODE']=='migration': sys.exit(1)
if name=='k3s' and os.environ['FAIL_MODE']=='image': sys.exit(1)
'''
        for name in ['aws','df','helm','k3s','systemctl','kubectl']:
            p = binaries / name
            p.write_text(fake)
            p.chmod(0o755)
        self.bundle()

    def tearDown(self):
        self.tmp.cleanup()

    def bundle(self, traversal=False):
        smoke = '''import os,pathlib
p=pathlib.Path(os.environ['FIXTURE'])/'smoke-count'
n=int(p.read_text()) if p.exists() else 0
p.write_text(str(n+1))
raise SystemExit(1 if os.environ['FAIL_MODE']=='smoke' and n==0 else 0)
'''
        images = {s+'Service': {'image':{'repository':'ghcr.io/ngqkhai/lynk-'+s+'-service','digest':'sha256:'+'b'*64}} for s in ['url','redirect','auth']}
        files = {'release.json':json.dumps({'version':1,'commit':SHA,'images':images}),
                 'smoke.py':smoke, 'values-aws.yaml':'{}', 'images.json':'{}', 'chart/Chart.yaml':'apiVersion: v2'}
        if traversal:
            files['../escape'] = 'bad'
        archive = self.root / 'release.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            for name, text in files.items():
                data=text.encode()
                item=tarfile.TarInfo(name)
                item.size=len(data)
                tar.addfile(item,io.BytesIO(data))
        (self.root / 'release.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  release.tar.gz\n')

    def run_deploy(self, mode=''):
        self.env['FAIL_MODE']=mode
        return subprocess.run(['bash',str(SCRIPT),'deploy',SHA,'0'],env=self.env,capture_output=True,text=True)

    def test_success_records_release(self):
        result=self.run_deploy()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue((self.root/'state/success.jsonl').exists())

    def test_image_failure_does_not_replace_pods(self):
        self.assertNotEqual(self.run_deploy('image').returncode,0)
        self.assertNotIn('helm upgrade',self.log.read_text())
        self.assertNotIn('helm rollback',self.log.read_text())

    def test_migration_failure_restores_previous_and_fails(self):
        self.assertNotEqual(self.run_deploy('migration').returncode,0)
        self.assertIn('helm rollback lynk-services 7',self.log.read_text())
        self.assertFalse((self.root/'state/success.jsonl').exists())

    def test_smoke_failure_rolls_back_and_checks_again(self):
        self.assertNotEqual(self.run_deploy('smoke').returncode,0)
        self.assertIn('helm rollback lynk-services 7',self.log.read_text())
        self.assertEqual((self.root/'smoke-count').read_text(),'2')

    def test_path_traversal_rejected_before_helm(self):
        self.bundle(traversal=True)
        self.assertNotEqual(self.run_deploy().returncode,0)
        self.assertNotIn('helm ',self.log.read_text())

    def test_concurrent_deploy_is_rejected_before_transport(self):
        state=self.root/'state'
        state.mkdir()
        with open(state/'deploy.lock','w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.env['LYNK_LOCK_WAIT_SECONDS']='0'
            self.assertNotEqual(self.run_deploy().returncode,0)
        self.assertFalse(self.log.exists())

    def test_unknown_manual_rollback_revision_is_rejected(self):
        state=self.root/'state'
        state.mkdir()
        (state/'success.jsonl').write_text(json.dumps({'commit':SHA,'revision':7})+'\n')
        result=subprocess.run(['bash',str(SCRIPT),'rollback',SHA,'99'],env=self.env,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('helm rollback',self.log.read_text())


if __name__=='__main__':
    unittest.main()
