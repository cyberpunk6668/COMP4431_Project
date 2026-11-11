'use strict';
// Some Windows development shells omit the system PowerShell directory from
// PATH. electron-builder uses npm's configured script shell while collecting
// production dependencies, so resolve the standard system shell explicitly.
const fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process');
const environment={...process.env};
if(process.platform==='win32'){
  const ps=path.join(process.env.SystemRoot||'C:\\Windows','System32','WindowsPowerShell','v1.0');
  if(fs.existsSync(path.join(ps,'powershell.exe')))environment.PATH=ps+path.delimiter+(environment.PATH||environment.Path||'');
}
const result=spawnSync(process.execPath,[require.resolve('electron-builder/out/cli/cli.js'),'--win','portable','--x64'],{cwd:__dirname,env:environment,stdio:'inherit'});
if(result.error)throw result.error;
process.exitCode=result.status??1;
