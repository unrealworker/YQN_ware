const fs=require('fs'),path=require('path'),os=require('os'),vm=require('vm'),assert=require('assert'),{spawnSync}=require('child_process');
const Zip=require('./src/store-zip.js'),Model=require('./src/model.cjs');
const context={SaasModel:Model,module:{exports:{}},Uint8Array,Int16Array,Date};vm.runInNewContext(fs.readFileSync(path.join(__dirname,'src/plugin.js'),'utf8'),context);const Migration=context.module.exports;
(async()=>{
 assert.equal(Zip.crc32(new TextEncoder().encode('123456789')),0xcbf43926,'standard CRC32 vector');
 const png=new Uint8Array(Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6WJkAAAAASUVORK5CYII=','base64'));
 const report={completed:true,boards:Array.from({length:54},(_,i)=>({number:53-i,id:'frame'+(53-i),name:'画板 / '+(53-i)}))},messages=[];let calls=0;
 const fake={getNodeByIdAsync:async id=>({exportAsync:async settings=>{assert.equal(settings.format,'PNG');assert.equal(settings.constraint.type,'SCALE');assert.equal(settings.constraint.value,.5);calls++;return png;}})};
 const summary=await Migration.exportVisuals(fake,report,m=>messages.push(m));assert.equal(calls,54);assert.equal(summary.exported,54);assert.equal(messages[0].number,0);assert.equal(messages[53].number,53);assert(!messages[0].name.includes(' / '));
 await assert.rejects(()=>Migration.exportVisuals(fake,{completed:false,boards:[]},()=>{}),/54/);
 await assert.rejects(()=>Migration.exportVisuals({getNodeByIdAsync:async()=>null},report,()=>{}),/画板缺失/);
 const zip=Zip.build([{name:'boards/00-中文画板.png',data:png},{name:'SaasNew-acceptance.json',data:JSON.stringify({boards:54,completed:true})}],new Date(2026,9,27));
 assert.equal(new DataView(zip.buffer).getUint32(0,true),0x04034b50);const end=new DataView(zip.buffer,zip.length-22);assert.equal(end.getUint32(0,true),0x06054b50);assert.equal(end.getUint16(10,true),2);
 const temp=path.join(os.tmpdir(),'SaasNew-zip-verification-'+process.pid+'.zip');fs.writeFileSync(temp,zip);
 try{const literal=temp.replace(/'/g,"''");const check=spawnSync('powershell.exe',['-NoProfile','-NonInteractive','-Command','-'],{input:"Add-Type -AssemblyName System.IO.Compression.FileSystem\n$z=[System.IO.Compression.ZipFile]::OpenRead('"+literal+"')\ntry { if($z.Entries.Count -ne 2){throw 'Count'}; foreach($e in $z.Entries){$s=$e.Open();try{$r=[System.IO.StreamReader]::new($s);if($e.FullName.EndsWith('.json')){$j=$r.ReadToEnd()|ConvertFrom-Json;if($j.boards -ne 54){throw 'Content'}}else{$m=[System.IO.MemoryStream]::new();$s.CopyTo($m);if($m.Length -lt 50){throw 'PNG'}}}finally{$s.Dispose()}} } finally {$z.Dispose()}\n",encoding:'utf8'});assert.equal(check.status,0,check.stderr);}finally{fs.unlinkSync(temp);}
 const template=fs.readFileSync(path.join(__dirname,'src/ui.template.html'),'utf8').replace('/*__PAYLOAD__*/','{}').replace('/*__ZIP__*/',fs.readFileSync(path.join(__dirname,'src/store-zip.js'),'utf8'));const script=template.match(/<script>([\s\S]*?)<\/script>/)[1];new vm.Script(script);
 const result={passed:true,testType:'export controller + independent ZIP-reader verification, not actual Figma rendering',checks:{scaleHalfPNG:true,all54Boards:true,sortedBoardNumbers:true,incompleteImportRejected:true,missingFrameRejected:true,crc32StandardVector:true,utf8ZipNames:true,dotNetZipReader:true,uiSyntax:true},downloadPolicy:'export starts only on button click; ZIP download requires a second click; no network permissions added'};
 fs.writeFileSync(path.join(__dirname,'visual-verification.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
