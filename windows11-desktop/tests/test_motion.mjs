import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const code = await readFile(new URL('../gnome-motion-extension/model.js', import.meta.url), 'utf8');
const {PRESETS, normalize, layers, pauseReason} = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
assert.equal(normalize({preset:'unknown',intensity:Infinity,accent:'red'}).preset,'off');
assert.equal(normalize({intensity:999,period:-1}).intensity,50);
assert.equal(normalize({period:-1}).period,8);
const config=normalize({preset:'aurora'}), state={animations:true};
assert.equal(pauseReason(config,state),'');
for (const reason of ['battery','fullscreen','locked','overview']) assert.ok(pauseReason(config,{...state,[reason]:true}));
assert.ok(pauseReason(config,{animations:false}));
assert.equal(pauseReason({...config,pauseBattery:false,pauseFullscreen:false},{...state,battery:true,fullscreen:true}),'');
for (const [preset] of PRESETS) {
    const c={...config,preset};
    assert.deepEqual(layers(c,0,48,0),[]);
    assert.deepEqual(layers(c,1920,48,NaN),[]);
    for (const time of [-10,0,2,10,19.99,1000000]) {
        const result=layers(c,1920,48,time,{x:640,width:48});
        for (const layer of result) {
            for(const key of ['x','y','rx','ry','alpha']) assert.ok(Number.isFinite(layer[key]));
            assert.ok(layer.rx>0 && layer.ry>0 && layer.alpha>=0 && layer.alpha<=1);
        }
        assert.equal(result.length>0,preset!=='off');
    }
    assert.deepEqual(layers(c,1920,48,0,{x:640,width:48}),layers(c,1920,48,c.period,{x:640,width:48}));
}
assert.deepEqual(layers({...config,preset:'halo'},1920,48,0),[]);
console.log('PASS motion geometry, cyclic timing, invalid inputs and pause policies');
