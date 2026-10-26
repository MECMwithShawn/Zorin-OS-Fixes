const {chromium} = require(process.env.PLAYWRIGHT_PATH || 'playwright');
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_EXECUTABLE||undefined});
 const page=await browser.newPage({viewport:{width:832,height:864}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const sampleApps=Array.from({length:20},(_,i)=>({id:i===0?'brave-browser.desktop':i===1?'org.gnome.Calculator.desktop':`test-${i}.desktop`,name:i===0?'Brave':i===1?'Calculator':`App ${i}`,description:'Test application'}));
 const fixture=process.argv[2]?JSON.parse(fs.readFileSync(process.argv[2],'utf8')):{mode:'start',user:'Test User',apps:sampleApps,pins:sampleApps.slice(0,18).map(a=>a.id),recent:[],places:[],groupsVisible:true,groups:[{id:'everyday',title:'Everyday',items:[],collapsed:false}]};
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
 const sessionCount=()=>page.evaluate(()=>window.testMessages.filter(m=>m.action==='session-action').length);
 const count=await sessionCount();
 await page.getByRole('button',{name:'Account options'}).click();
 assert.deepEqual(await page.getByRole('menu',{name:'Account menu'}).getByRole('menuitem').allTextContents(),['Account settings','Lock','Switch user','Sign out']);
 await page.getByRole('button',{name:'Power options'}).click();
 assert.equal(await page.getByRole('menu',{name:'Account menu'}).count(),0);
 assert.deepEqual(await page.getByRole('menu',{name:'Power menu'}).getByRole('menuitem').allTextContents(),['Sleep','Shut down','Restart']);
 await page.keyboard.press('End');assert.equal(await page.evaluate(()=>document.activeElement.textContent),'Restart');
 await page.keyboard.press('Escape');assert.equal(await page.getByRole('menu').count(),0);
 assert.equal(await sessionCount(),count,'Opening or dismissing a menu must not request a session action');
 assert.equal(await page.getByRole('button',{name:'Power options'}).evaluate(e=>e===document.activeElement),true);
 for(const [menu,label,command] of [['Account','Lock','lock'],['Account','Switch user','switch-user'],['Account','Sign out','sign-out'],['Power','Sleep','sleep'],['Power','Shut down','shutdown'],['Power','Restart','restart']]){
  await page.getByRole('button',{name:menu+' options'}).click();
  await page.getByRole('menuitem',{name:label,exact:true}).click();
  assert.deepEqual(await page.evaluate(()=>window.testMessages.filter(m=>m.action==='session-action').at(-1)),{action:'session-action',command});
  assert.equal(await page.getByRole('menu').count(),0);
 }
 await page.getByRole('button',{name:'Account options'}).click();
 await page.getByRole('menuitem',{name:'Account settings'}).click();
 assert.deepEqual(await page.evaluate(()=>window.testMessages.at(-1)),{action:'settings',page:'accounts'});
 await page.evaluate(()=>window.receive({type:'state',data:{mode:'group',group:window.fixture.groups[0],peeking:false}}));
 await page.setViewportSize({width:380,height:280});
 await page.getByRole('button',{name:'Roll up fence'}).click();
 assert((await page.evaluate(()=>window.testMessages)).some(m=>m.action==='collapse'&&m.group==='everyday'));
 const title=await page.locator('.fence-titlebar strong').boundingBox();
 await page.mouse.move(title.x+10,title.y+10);await page.mouse.down();await page.mouse.up();
 const grip=await page.getByRole('button',{name:'Resize fence'}).boundingBox();
 await page.mouse.move(grip.x+4,grip.y+4);await page.mouse.down();await page.mouse.up();
 assert((await page.evaluate(()=>window.testMessages)).some(m=>m.action==='move'));
 assert((await page.evaluate(()=>window.testMessages)).some(m=>m.action==='resize'));
 assert.deepEqual(errors,[]);
 console.log('UI passed: pinned grid, pin/unpin, drag reorder, search, launch command, app groups, folder groups, power menu, collapse, move/resize controls.');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
