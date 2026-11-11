"""Verify the local desktop build and launcher refusal paths; no model/broker calls."""
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import threading

ROOT=Path(__file__).resolve().parents[1]


def main():
    package=json.loads((ROOT/'desktop/package.json').read_text(encoding='utf-8'))
    lock=json.loads((ROOT/'desktop/package-lock.json').read_text(encoding='utf-8'))
    assert package['devDependencies']=={'electron':'45.3.0','electron-builder':'26.18.0'}
    assert lock['packages']['node_modules/electron']['version']=='45.3.0'
    assert lock['packages']['node_modules/electron-builder']['version']=='26.18.0'
    node=shutil.which('node');assert node
    tests=subprocess.run([node,'--test','desktop/tests/geometry.test.cjs'],cwd=ROOT,capture_output=True,text=True,timeout=20)
    assert tests.returncode==0,tests.stderr
    script="""const a=require('./desktop/node_modules/@electron/asar');const p='desktop/artifacts/win-unpacked/resources/app.asar';const files=a.listPackage(p);const main=a.extractFile(p,'main.cjs').toString();if(!main.includes('pet:roaming')||!main.includes('slice(0,64)'))throw Error('stale host');if(files.some(f=>/\\.env|sqlite|node_modules/.test(f)))throw Error('private/runtime content in host');console.log(JSON.stringify(files));"""
    archive=subprocess.run([node,'-e',script],cwd=ROOT,capture_output=True,text=True,timeout=20)
    assert archive.returncode==0,archive.stderr
    class Other(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"application":"controlled-other-service"}')
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Other)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        shell=shutil.which('pwsh') or shutil.which('powershell');assert shell
        refused=subprocess.run([shell,'-NoProfile','-File',str(ROOT/'start-desktop.ps1'),'-Port',str(server.server_port)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)
        assert refused.returncode!=0 and 'not a FinPilot service' in refused.stderr
    finally:server.shutdown();server.server_close();thread.join(timeout=2)
    executable=ROOT/'desktop/artifacts/FinPilotPet-15.0.0-win-x64-portable.exe';assert executable.stat().st_size>1000000
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'status':'passed','scope':'Build/ASAR/lockfile/Node contracts and a controlled launcher wrong-service refusal; not native visual acceptance.',
            'electron':'45.3.0','electron_builder':'26.18.0','host_contract_tests':4,'wrong_service_refused':True,
            'asar_files':json.loads(archive.stdout),'portable':{'path':executable.relative_to(ROOT).as_posix(),'bytes':executable.stat().st_size,'sha256':hashlib.sha256(executable.read_bytes()).hexdigest()},
            'python_backend_bundled':False,'requires_existing_finpilot_python_environment':True,
            'screen_capture_capability_added':False,'real_model_calls':0,'broker_requests':0,'native_visual_validation':'separate parent-owned report',
            'build_history':['Initial dependency collection failed because system PowerShell was absent from PATH.','build.cjs supplies the standard system PowerShell directory for the packager; subsequent portable builds succeeded.'],
            'limitations':['Unsigned portable application; no code-signing identity configured.','Uses current local Windows environment; does not certify all Windows versions or a machine without Python.']}
    (ROOT/'reports/desktop_build_v15.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'host_contract_tests':4,'portable':report['portable'],'wrong_service_refused':True}))


if __name__=='__main__':main()
