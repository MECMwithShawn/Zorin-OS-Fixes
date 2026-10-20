import React,{useEffect,useState} from 'react';
const send=enabled=>window.webkit.messageHandlers.desktop.postMessage(JSON.stringify({action:'audio-spectrum',enabled}));
export function AudioSpectrum(){
 const [meter,setMeter]=useState({levels:Array(16).fill(0),available:false});
 useEffect(()=>{
  const receive=e=>{if(e.detail.type==='audio-spectrum')setMeter(e.detail);};
  window.addEventListener('desktop-message',receive);
  const subscribe=()=>send(!document.hidden);
  subscribe();const timer=setInterval(subscribe,2000);
  document.addEventListener('visibilitychange',subscribe);
  return()=>{clearInterval(timer);document.removeEventListener('visibilitychange',subscribe);window.removeEventListener('desktop-message',receive);send(false);};
 },[]);
 return <div className="audio-spectrum" aria-label="Live playback spectrum">
  <div className="audio-spectrum-bars" aria-hidden="true">{Array.from({length:16},(_,i)=><span key={i}><i style={{transform:`scaleY(${Math.max(.015,Math.min(1,Number(meter.levels?.[i])||0))})`}}/></span>)}</div>
  <div className="audio-spectrum-caption"><span>Bass</span><span>{meter.available?'Live playback':'Waiting for output'}</span><span>Treble</span></div>
 </div>;
}
