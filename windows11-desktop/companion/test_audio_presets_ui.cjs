const {chromium}=require(process.env.PLAYWRIGHT_PATH||'playwright');
const assert=require('assert/strict'),path=require('path'),fs=require('fs');
const fixture=JSON.parse(require('child_process').execFileSync('/usr/bin/python3',['-c',
 'import json,audio_effects as a;print(json.dumps(dict(presets=a.PRESETS,frequencies=a.FREQUENCIES)))'],{cwd:__dirname,encoding:'utf8'}));
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_EXECUTABLE});
 try{
  const page=await browser.newPage({viewport:{width:1120,height:760}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(fixture=>{
   window.messages=[];
   window.fixture={mode:'settings',volume:40,muted:false,output:'speakers',outputs:[{id:'speakers',name:'Speakers'}],facts:{tools:{}},
    audioEffects:{...fixture,preset:'off',available:true,active:false,error:''}};
   window.webkit={messageHandlers:{desktop:{postMessage(raw){
    const m=JSON.parse(raw);window.messages.push(m);
    if(m.action==='ready')setTimeout(()=>window.receive({type:'state',data:structuredClone(window.fixture)}),0);
    if(['settings-set','quick-set'].includes(m.action)&&m.name==='audioPreset'){
     window.fixture.audioEffects={...window.fixture.audioEffects,preset:m.value,active:m.value!=='off'};
     window.receive({type:'state',data:structuredClone(window.fixture)});
    }
   }}}};
  },fixture);
  await page.goto('file://'+path.join(__dirname,'dist/index.html'));
  await page.waitForSelector('.settings-shell');
  await page.evaluate(()=>window.receive({type:'show',page:'sound'}));
  const select=page.getByRole('combobox',{name:'Audio preset'});
  assert.equal(await select.locator('option').count(),8);
  for(const p of fixture.presets){
   await select.selectOption(p.id);
   await page.waitForFunction(id=>document.querySelector('[aria-label="Audio preset"]').value===id && document.querySelectorAll('.audio-preset-bands dd').length===(id==='off'?0:6),p.id);
   if(p.id!=='off')assert.equal(await page.locator('.audio-preset-bands dd').count(),6);
  }
  assert.equal(await page.getByRole('slider',{name:'Volume',exact:true}).inputValue(),'40');
  if(process.env.ZORIN11_TEST_OUTPUT){
   fs.mkdirSync(process.env.ZORIN11_TEST_OUTPUT,{recursive:true});
   await page.screenshot({path:path.join(process.env.ZORIN11_TEST_OUTPUT,'audio-settings.png')});
  }
  await page.evaluate(()=>{window.fixture.busy=true;window.receive({type:'state',data:structuredClone(window.fixture)});});
  await page.waitForFunction(()=>document.querySelector('[aria-label="Audio preset"]').disabled);
  assert(await select.isDisabled());
  await page.evaluate(()=>{window.fixture.busy=false;window.fixture.mode='quick';window.receive({type:'state',data:structuredClone(window.fixture)});});
  await page.setViewportSize({width:368,height:490});
  await page.getByRole('button',{name:'Select sound output'}).click();
  await select.selectOption('voice');
  assert(await page.evaluate(()=>window.messages.some(m=>m.action==='quick-set'&&m.name==='audioPreset'&&m.value==='voice')));
  assert(await page.getByRole('radio',{name:'Speakers'}).isVisible());
  await page.evaluate(()=>{window.fixture.audioEffects.error='Output disconnected';window.receive({type:'state',data:structuredClone(window.fixture)});});
  assert.equal(await page.locator('.audio-preset-error').innerText(),'Output disconnected');
  await page.evaluate(()=>{window.fixture.audioEffects.available=false;window.receive({type:'state',data:structuredClone(window.fixture)});});
  await page.waitForFunction(()=>document.querySelector('[aria-label="Audio preset"]').disabled);
  assert(await select.isDisabled());
  assert.deepEqual(errors,[]);
  console.log('PASS Settings/Quick Settings presets, all choices, status/error, disabled state and unchanged volume');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
