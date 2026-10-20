import React from 'react';
import './audio-presets.css';
import {AudioSpectrum} from './audio-spectrum.jsx';

export function AudioPresets({data,busy,onChange,compact=false}){
 const audio=data.audioEffects;
 const choices=audio?.presets||[];
 const selected=choices.find(p=>p.id===audio?.preset);
 return <section className={'audio-presets'+(compact?' compact':'')} aria-label="Audio enhancements">
  <label className="audio-preset-picker"><span>Audio enhancements<small>Choose an EQ preset for playback</small></span>
   <select aria-label="Audio preset" value={audio?.preset||'off'} disabled={busy||!audio?.available} onChange={e=>onChange(e.target.value)}>
    {choices.length?choices.map(p=><option key={p.id} value={p.id}>{p.name}</option>):<option value="off">Off</option>}
   </select>
  </label>
  {!audio?.available?<p>Audio presets require PipeWire playback.</p>:<>
   <AudioSpectrum/>
   <p>{selected?.detail}</p>
   {audio.preset!=='off'&&<p className={audio.error?'audio-preset-error':'audio-preset-status'} role="status">{audio.error|| (audio.active?'Active on your current output':'Starting audio processing…')}</p>}
   {!compact&&audio.preset!=='off'&&<><dl className="audio-preset-bands">{(audio.frequencies||[]).map((hz,i)=><div key={hz}><dt>{hz>=1000?hz/1000+'k':hz} Hz</dt><dd>{selected?.gains[i]>0?'+':''}{selected?.gains[i]??0} dB</dd></div>)}</dl><p className="audio-preset-note">Preset headroom reduces clipping. Playback volume may be lower; your microphone is unaffected.</p></>}
  </>}
 </section>;
}
