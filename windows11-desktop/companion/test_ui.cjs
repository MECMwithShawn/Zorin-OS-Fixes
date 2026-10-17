const {chromium} = require(process.env.PLAYWRIGHT_PATH || 'playwright');
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_EXECUTABLE||undefined});
 const page=await browser.newPage({viewport:{width:832,height:864}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const fixture=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
 for(const a of fixture.apps){a.categories=a.name==='Brave'?['Network']:['Utility'];}
 for(const a of fixture.apps)a.icon='data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="%2360cdff"/></svg>';
 await page.addInitScript(data=>{
  window.testMessages=[];window.fixture=data;
  window.webkit={messageHandlers:{desktop:{postMessage(raw){
   const m=JSON.parse(raw);window.testMessages.push(m);
   if(m.action==='ready')setTimeout(()=>window.receive({type:'state',data}),0);
   if(m.action==='pin'){data.pins=data.pins.filter(i=>i!==m.id);if(m.value)data.pins.push(m.id);window.receive({type:'state',data:{...data}});}
   if(m.action==='reorder'){data.pins=data.pins.filter(i=>i!==m.id);data.pins.splice(data.pins.indexOf(m.target),0,m.id);window.receive({type:'state',data:{...data}});}
  }}}};
 },fixture);
 await page.goto('file://'+path.join(__dirname,'dist/index.html'));
 await page.waitForSelector('.pins .app-tile');
 assert.equal(await page.locator('.pins .app-tile').count(),18);
 assert.equal(await page.locator('.pins').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length),8);
 await page.getByRole('button',{name:'Open Internet apps',exact:true}).click();
 assert.equal(await page.locator('.app-list .app-row').count(),1);
 assert.equal(await page.locator('.app-list .app-launch').innerText(),'Brave');
 await page.getByRole('button',{name:'Back',exact:true}).click();
 await page.getByLabel('App view',{exact:true}).selectOption('Grid');
 assert.equal(await page.locator('.all-app-grid .app-tile').count(),fixture.apps.length);
 await page.getByLabel('App view',{exact:true}).selectOption('List');
 assert.equal(await page.locator('.all-app-list .app-launch').count(),fixture.apps.length);
 await page.getByLabel('App view',{exact:true}).selectOption('Category');

 await page.locator('.pins .app-tile').first().click({button:'right'});
 await page.getByRole('button',{name:'Unpin from Start',exact:true}).click();
 assert.equal(await page.locator('.pins .app-tile').count(),17);
 await page.getByRole('button',{name:'All apps',exact:true}).click();
 await page.getByRole('button',{name:'Pin Brave',exact:true}).click();
 await page.getByRole('button',{name:'Back',exact:true}).click();
 assert.equal(await page.locator('.pins .app-tile').count(),18);
 const before=await page.evaluate(()=>window.fixture.pins.slice());
 await page.locator('.pins .app-tile').nth(2).dragTo(page.locator('.pins .app-tile').nth(0));
 assert.equal(await page.evaluate(()=>window.fixture.pins[0]),before[2]);
 await page.getByRole('textbox',{name:'Search apps'}).fill('calculator');
 assert.equal(await page.locator('.app-list .app-row').count(),1);
 await page.getByRole('textbox',{name:'Search apps'}).press('Enter');
 assert((await page.evaluate(()=>window.testMessages)).some(m=>m.action==='launch'&&m.id==='org.gnome.Calculator.desktop'));
 await page.getByRole('button',{name:'Clear search'}).click();
 await page.locator('.pins .app-tile').first().click({button:'right'});
 await page.getByRole('button',{name:'Add to desktop group…',exact:true}).click();
 await page.locator('.group-choices button').first().click();
 assert((await page.evaluate(()=>window.testMessages)).some(m=>m.action==='add-app'&&m.group==='everyday'));
 await page.getByRole('button',{name:'Desktop groups',exact:true}).first().click();
 await page.getByRole('textbox',{name:'New group name'}).fill('Projects');
 await page.getByRole('button',{name:'Create',exact:true}).click();
 assert((await page.evaluate(()=>window.testMessages)).some(m=>m.action==='new-group'&&m.title==='Projects'));
 await page.getByRole('button',{name:'Show a folder on the desktop',exact:true}).click();
 assert((await page.evaluate(()=>window.testMessages)).some(m=>m.action==='new-group'&&m.folder));
 await page.getByRole('button',{name:'Power options'}).click();
 assert.equal(await page.getByRole('button',{name:'Sign out / power…',exact:true}).count(),1);
 await page.evaluate(()=>window.receive({type:'state',data:{mode:'group',group:window.fixture.groups[0],peeking:false}}));
 await page.setViewportSize({width:380,height:280});
 await page.getByRole('button',{name:'Collapse group'}).click();
 assert((await page.evaluate(()=>window.testMessages)).some(m=>m.action==='collapse'&&m.group==='everyday'));
 const title=await page.locator('.group-titlebar strong').boundingBox();
 await page.mouse.move(title.x+10,title.y+10);await page.mouse.down();await page.mouse.up();
 const grip=await page.getByRole('button',{name:'Resize group'}).boundingBox();
 await page.mouse.move(grip.x+4,grip.y+4);await page.mouse.down();await page.mouse.up();
 assert((await page.evaluate(()=>window.testMessages)).some(m=>m.action==='move'));
 assert((await page.evaluate(()=>window.testMessages)).some(m=>m.action==='resize'));
 assert.deepEqual(errors,[]);
 console.log('UI passed: pinned grid, pin/unpin, drag reorder, search, launch command, app groups, folder groups, power menu, collapse, move/resize controls.');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
