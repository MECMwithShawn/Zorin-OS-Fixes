const {chromium}=require(process.env.PLAYWRIGHT_PATH||'playwright');
const assert=require('assert/strict');const path=require('path');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_EXECUTABLE});
 const page=await browser.newPage({viewport:{width:1120,height:760}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{
  window.messages=[];
  window.fileFixture={mode:'explorer',path:'/test',title:'test',places:[{name:'Documents',path:'/test/Documents',symbol:'document'}],clouds:[{name:'OneDrive - Personal',path:'/test/OneDrive',icon:'axentra-onedrive'}],entries:[{path:'/test/folder',name:'folder',folder:true,symbol:'folder',date:'10/17/2026',type:'File folder'},{path:'/test/notes.txt',name:'notes.txt',folder:false,symbol:'document',size:100,date:'10/17/2026',type:'TXT file'}]};
  window.webkit={messageHandlers:{desktop:{postMessage(raw){const m=JSON.parse(raw);window.messages.push(m);if(m.action==='ready')setTimeout(()=>window.receive({type:'state',data:window.fileFixture}),0);if(m.action==='file-navigate'){window.fileFixture={...window.fileFixture,path:m.path,title:m.path.split('/').pop()};window.receive({type:'state',data:window.fileFixture});}}}}};
 });
 await page.goto('file://'+path.join(__dirname,'dist/index.html'));await page.waitForSelector('.file-item');
 await page.getByRole('option',{name:/^folder/}).dblclick();
 assert.equal(await page.evaluate(()=>window.messages.filter(m=>m.action==='file-navigate').at(-1).path),'/test/folder');
 await page.getByRole('button',{name:'Back',exact:true}).click();
 assert.equal(await page.evaluate(()=>window.messages.filter(m=>m.action==='file-navigate').at(-1).path),'/test');
 await page.getByRole('option',{name:/notes.txt/}).click();await page.getByRole('button',{name:'Copy',exact:true}).click();
 assert.deepEqual(await page.evaluate(()=>window.messages.find(m=>m.action==='file-copy').paths),['/test/notes.txt']);
 await page.getByRole('button',{name:'Details pane',exact:true}).click();
 assert.equal(await page.getByRole('complementary',{name:'Item details'}).getByRole('heading').innerText(),'notes.txt');
 await page.getByRole('button',{name:'Details pane',exact:true}).click();
 await page.getByRole('button',{name:'Rename',exact:true}).click();await page.getByRole('textbox',{name:'Name',exact:true}).fill('renamed.txt');await page.getByRole('button',{name:'Save',exact:true}).click();
 assert.equal(await page.evaluate(()=>window.messages.find(m=>m.action==='file-rename').name),'renamed.txt');
 await page.getByRole('button',{name:'New',exact:true}).click();await page.getByRole('textbox',{name:'Name',exact:true}).fill('New folder');await page.getByRole('button',{name:'Save',exact:true}).click();
 assert(await page.evaluate(()=>window.messages.some(m=>m.action==='file-new-folder')));
 await page.getByRole('textbox',{name:'Search this folder'}).fill('notes');assert.equal(await page.getByRole('option').count(),1);
 await page.getByRole('button',{name:'Network',exact:true}).click();
 assert(await page.evaluate(()=>window.messages.some(m=>m.action==='file-network')));
 await page.getByRole('button',{name:'Recycle Bin',exact:true}).click();
 assert(await page.evaluate(()=>window.messages.some(m=>m.action==='file-trash-view')));
 assert.deepEqual((await page.locator('.explorer-sidebar button').allInnerTexts()).slice(0,3),['Home','OneDrive - Personal','Documents']);
 await page.getByRole('button',{name:'OneDrive - Personal',exact:true}).click();
 assert.equal(await page.evaluate(()=>window.messages.filter(m=>m.action==='file-navigate').at(-1).path),'/test/OneDrive');
 assert(await page.getByRole('button',{name:'OneDrive - Personal',exact:true}).evaluate(e=>e.classList.contains('selected')));
 await page.getByRole('button',{name:'Back',exact:true}).click();
 await page.getByRole('button',{name:'New tab',exact:true}).click();assert.equal(await page.locator('.explorer-tab').count(),2);
 await page.getByRole('button',{name:'Large icons',exact:true}).click();assert(await page.locator('.explorer-files').evaluate(e=>e.classList.contains('icons')));
 await page.evaluate(()=>window.receive({type:'state',data:{...window.fileFixture,path:'::computer',title:'This PC',entries:[
  {path:'/media/usb',name:'AXENTRA_OS (E:)',driveLetter:'E',folder:true,symbol:'drive',total:30,free:20},
  {path:'/media/os',name:'OS (D:)',driveLetter:'D',folder:true,symbol:'drive',total:5000,free:2000},
  {path:'/',name:'Local Disk (C:)',driveLetter:'C',folder:true,symbol:'drive',total:4000,free:3000}
 ]}}));
 assert.deepEqual(await page.locator('.file-item').evaluateAll(items=>items.map(e=>e.title)),['Local Disk (C:)','OS (D:)','AXENTRA_OS (E:)']);
 await page.getByRole('button',{name:'Sort',exact:true}).click();await page.getByRole('button',{name:'Size',exact:true}).click();
 assert.equal(await page.locator('.file-item').first().getAttribute('title'),'Local Disk (C:)');
 await page.getByRole('option',{name:/Local Disk/}).click({button:'right'});
 const context=page.getByRole('menu',{name:'Explorer menu'});
 if(process.env.ZORIN11_TEST_PREVIEWS){require('fs').mkdirSync(process.env.ZORIN11_TEST_PREVIEWS,{recursive:true});await page.screenshot({path:path.join(process.env.ZORIN11_TEST_PREVIEWS,'drive-menu.png')});}
 assert(await context.getByRole('menuitem',{name:'Rename',exact:true}).isEnabled());
 assert.equal(await context.getByRole('menuitem',{name:'Paste',exact:true}).count(),0);
 await context.getByRole('menuitem',{name:'Properties',exact:true}).click();
 const properties=page.getByRole('dialog',{name:'Properties',exact:true});
 assert((await properties.innerText()).includes('Capacity'));
 assert((await properties.innerText()).includes('Free space'));
 if(process.env.ZORIN11_TEST_PREVIEWS)await page.screenshot({path:path.join(process.env.ZORIN11_TEST_PREVIEWS,'drive-properties.png')});
 await properties.getByRole('button',{name:'OK',exact:true}).click();
 await page.getByRole('option',{name:/Local Disk/}).click({button:'right'});
 await context.getByRole('menuitem',{name:'Rename',exact:true}).click();
 await page.getByRole('textbox',{name:'Name',exact:true}).fill('Zorin System');
 await page.getByRole('button',{name:'Save',exact:true}).click();
 assert.deepEqual(await page.evaluate(()=>window.messages.filter(m=>m.action==='file-rename-drive').at(-1)),{action:'file-rename-drive',name:'Zorin System',path:'/'});
 await page.getByRole('option',{name:/Local Disk/}).click({button:'right'});
 await context.getByRole('menuitem',{name:'Copy as path',exact:true}).click();
 assert.deepEqual(await page.evaluate(()=>window.messages.filter(m=>m.action==='file-copy-path').at(-1).paths),['/']);
 await page.getByRole('region',{name:'Files',exact:true}).click({button:'right',position:{x:600,y:450}});
 assert.equal(await context.getByRole('menuitem',{name:'Rename',exact:true}).count(),0);
 await page.keyboard.press('Escape');
 await page.getByRole('option',{name:/Local Disk/}).dblclick();
 assert.equal(await page.evaluate(()=>window.messages.filter(m=>m.action==='file-navigate').at(-1).path),'/');
 await page.evaluate(()=>window.receive({type:'state',data:{mode:'quick',wifi:true,networkType:'wifi',network:'Test network',bluetooth:true,dnd:false,volume:40,muted:false,sink:'Speakers'}}));
 await page.setViewportSize({width:368,height:430});await page.getByRole('button',{name:'Mute',exact:true}).click();
 assert(await page.evaluate(()=>window.messages.some(m=>m.action==='quick-set'&&m.name==='muted'&&m.value)));
 await page.getByRole('slider',{name:'Volume',exact:true}).fill('55');await page.getByRole('slider',{name:'Volume',exact:true}).dispatchEvent('keyup',{key:'ArrowRight'});
 assert.equal(await page.evaluate(()=>window.messages.filter(m=>m.action==='quick-set'&&m.name==='volume').at(-1).value),55);
 await page.getByRole('button',{name:'Do not disturb',exact:true}).click();assert(await page.evaluate(()=>window.messages.some(m=>m.action==='quick-set'&&m.name==='dnd'&&m.value)));
 assert.deepEqual(errors,[]);console.log('Explorer and Quick Settings UI passed.');await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
