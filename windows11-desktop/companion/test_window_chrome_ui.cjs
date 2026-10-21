const {chromium}=require(process.env.PLAYWRIGHT_PATH||'playwright');
const assert=require('assert/strict'),path=require('path');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_EXECUTABLE});
 try { for(const mode of ['explorer','settings']){
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(mode=>{
   window.messages=[];window.fixture={mode,title:'Fixture',path:'/fixture',places:[],entries:[],facts:{},wallpaper:{},apps:[],user:'Fixture'};
   window.webkit={messageHandlers:{desktop:{postMessage(raw){const m=JSON.parse(raw);window.messages.push(m);if(m.action==='ready')setTimeout(()=>window.receive({type:'state',data:window.fixture}),0);}}}};
  },mode);
  await page.goto('file://'+path.join(__dirname,'dist/index.html'));
  const max=page.getByRole('button',{name:'Maximize',exact:true});await max.waitFor();
  await max.hover();assert.deepEqual(await page.evaluate(()=>messages.at(-1)),{action:'snap-hover',enter:true});
  await max.click({button:'right'});assert.deepEqual(await page.evaluate(()=>messages.slice(-2)),[{action:'snap-hover',enter:false},{action:'snap-layouts'}]);
  for(const key of ['ArrowDown','Shift+F10']){
   await max.focus();await max.press(key);
   assert.deepEqual(await page.evaluate(()=>messages.slice(-2)),[{action:'snap-hover',enter:false},{action:'snap-layouts'}]);
  }
  assert(!(await page.evaluate(()=>messages)).some(m=>m.action.endsWith('-maximize')));
  await max.press('Enter');assert.equal(await page.evaluate(()=>messages.at(-1).action),mode==='settings'?'settings-maximize':'file-maximize');
  await page.evaluate(()=>window.receive({type:'state',data:{...window.fixture,maximized:true}}));
  const restore=page.getByRole('button',{name:'Restore down',exact:true});await restore.click({button:'right'});
  assert.equal(await page.evaluate(()=>messages.at(-1).action),'snap-layouts');
  assert.deepEqual(errors,[]);await page.close();console.log('PASS',mode,'caption hover, context menu, keyboard picker and maximize/restore');
 }}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
