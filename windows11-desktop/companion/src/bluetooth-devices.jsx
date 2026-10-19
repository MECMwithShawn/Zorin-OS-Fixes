import React from 'react';
import {Glyph} from './explorer.jsx';
import './bluetooth-devices.css';
function DeviceIcon({name}){
 const kind=name?.includes('audio')?'headset':name?.includes('keyboard')?'keyboard':name?.includes('mouse')?'mouse':null;
 const paths={headset:<><path d="M4 13v-2a8 8 0 0 1 16 0v2M4 12H2v7h5v-7Zm16 0h2v7h-5v-7Z"/></>,keyboard:<><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M5 9h2m2 0h2m2 0h2m2 0h2M5 12h2m2 0h2m2 0h2m2 0h2M7 16h10"/></>,mouse:<><rect x="6" y="2" width="12" height="20" rx="6"/><path d="M12 2v8M6 10h12"/></>};
 return kind?<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[kind]}</svg>:<Glyph name="bluetooth" size={24}/>;
}
export function BluetoothDevices({devices=[],enabled,busy,onConnect}){
 if(!devices.length)return <p className="bluetooth-empty">{enabled?'No paired devices yet. Add a device in Bluetooth settings.':'Turn on Bluetooth to connect your paired devices.'}</p>;
 return <div className="bluetooth-devices">{[true,false].map(connected=>{
  const group=devices.filter(d=>d.connected===connected);
  return !!group.length&&<section key={String(connected)}><h3>{connected?'Connected':'Paired devices'}</h3>{group.map(device=><div className="bluetooth-device" key={device.id}>
   <DeviceIcon name={device.icon}/><span><strong>{device.name}</strong><small>{device.connected?'Connected':device.blocked?'Blocked in Bluetooth settings':enabled?'Not connected':'Bluetooth is off'}{device.battery!=null?' · '+device.battery+'% battery':''}</small></span>
   <button className="setting-button" aria-label={(device.connected?'Disconnect ':'Connect ')+device.name} disabled={busy||(!device.connected&&(!enabled||!device.available))} onClick={()=>onConnect(device.id,!device.connected)}>{device.connected?'Disconnect':'Connect'}</button>
  </div>)}</section>;
 })}</div>;
}
