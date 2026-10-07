import {loadFastPreview, releaseAllPreviews} from './preview-player.js';

const $ = id => document.getElementById(id);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = value => { const s = Math.max(0, Number(value) || 0); return `${Math.floor(s/60)}:${(s%60).toFixed(2).padStart(5,'0')}`; };
const duration = value => value == null ? 'Scanning…' : `${Math.floor(value/60)}m ${Math.round(value%60)}s`;
let sid = localStorage.getItem('audio-pairing-session'), doc, pairId, selected = new Set(), renderKey = '', sessionKey = '', exportKey = '';
let token = 0, playing = false, loading = false, traces = {}, browsing = '', pollBusy = false;
const fpv = $('fpv-player'), stick = $('stick-player');
let noticeTimer;
function notice(text, error = false) {
  clearTimeout(noticeTimer); $('notice').textContent = text; $('notice').className = `visible ${error ? 'error' : ''}`;
  noticeTimer = setTimeout(() => $('notice').className = '', error ? 15000 : 7000);
}
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: {'Content-Type':'application/json', ...options.headers}});
  if (!response.ok) { let message = `Request failed (${response.status})`; try { message = (await response.json()).detail || message; } catch {} throw new Error(typeof message === 'string' ? message : JSON.stringify(message)); }
  return response.json();
}
const post = (path, body = {}) => api(path, {method:'POST', body:JSON.stringify(body)});
function action(id, callback) { $(id).addEventListener('click', () => Promise.resolve().then(callback).catch(e => notice(e.message,true))); }
function currentPair() { return doc?.pairs.find(p => p.id === pairId); }
function record(id) { return doc?.videos.find(r => r.id === id); }
function pause() { playing = false; fpv.pause(); stick.pause(); }
function clearReview() { token++; pause(); releaseAllPreviews(); for (const v of [fpv,stick]) { v.removeAttribute('src'); v.load(); } pairId = null; traces={}; $('review').hidden=true; }
async function chooseSession(id) {
  clearReview(); sid=id; selected.clear(); renderKey=''; sessionKey=''; localStorage.setItem('audio-pairing-session',id);
  doc=await api(`/api/sessions/${id}`); $('rename-name').value=doc.name;
  $('modified-kind').value=doc.modified_kind || 'end'; $('filenames').checked=doc.use_filenames !== false;
  render(); await refreshSessions();
}
async function refreshSessions() {
  const sessions=await api('/api/sessions'), key=JSON.stringify(sessions.map(s => [s.id,s.name,s.videos,s.confirmed,s.job?.status]));
  if (key === sessionKey) return; sessionKey=key;
  $('sessions').innerHTML=sessions.length ? sessions.map(s => `<button class="session-card ${sid===s.id?'active':''}" data-session="${s.id}"><strong>${escape(s.name)}</strong><small>${s.videos} recordings · ${s.confirmed} confirmed pairs</small><small>${new Date(s.created*1000).toLocaleString()}</small></button>`).join('') : '<div class="empty">Create a session to start matching.</div>';
  $('sessions').querySelectorAll('[data-session]').forEach(b => b.onclick=() => chooseSession(b.dataset.session).catch(e=>notice(e.message,true)));
}
function tick(value, title) { return `<td class="${value==null?'pending':value?'yes':'no'}" title="${escape(title)}">${value==null?'—':value?'✓':'✕'}</td>`; }
function list(kind) {
  return doc.videos.filter(r=>r.kind===kind).map(r => {
    const m=r.metadata, status=r.audio_status, ready=status==='ready';
    return `<div class="video-card"><label class="video-name"><input type="checkbox" data-video="${r.id}" ${selected.has(r.id)?'checked':''}><span class="name">${escape(r.name)}</span></label><div class="video-meta">${duration(m?.duration)}${m?` · ${m.width}×${m.height} · ${m.fps.toFixed(2)}fps`:''}${r.audio_seconds!=null?` · ${r.audio_reused?'Cache reused':'Audio prepared'} in ${r.audio_seconds}s`:''}</div><table class="indicators"><thead><tr><th>Audio track</th><th>Fingerprints</th><th>Filename time</th></tr></thead><tbody><tr>${tick(m?.has_audio,m?.has_audio?'Audio stream present':'No audio stream')}${tick(ready?true:['unusable','no_audio'].includes(status)?false:null,status==='unusable'?'Audio has too little usable variation':ready?'Saved in this session':'Prepared when matching runs')}${tick(r.filename_time!=null,'Camera clock reading parsed from filename')}</tr></tbody></table>${r.error?`<div class="hint error">${escape(r.error)}</div>`:''}</div>`;
  }).join('') || '<div class="empty">No recordings found in this folder.</div>';
}
function selectionLabel() { $('selection-count').textContent=`${selected.size} selected`; }
function render() {
  if (!doc) return;
  $('workspace').hidden=false; $('sources-section').hidden=true; $('session-controls').hidden=false;
  const job=doc.job || {}, active=['queued','running'].includes(job.status);
  const jobHost=job.title==='Finding matching flights' ? $('match-progress') : $('job-location');
  if ($('job').parentElement!==jobHost) jobHost.append($('job'));
  $('job').hidden=!job.status; $('job-title').textContent=`${job.title || 'Task'} · ${job.status || ''}`;
  $('job-percent').textContent=`${job.percent || 0}%`; $('job-progress').value=job.percent || 0;
  $('job-message').textContent=job.message || ''; $('job-timing').textContent=`Elapsed ${duration(job.elapsed)}${job.eta!=null&&active?` · Estimated remaining ${duration(job.eta)}`:''}`;
  $('cancel').hidden=!active; ['find','rescan','delete','confirm','unconfirm','apply-offset','manual-add','export','filenames','modified-kind'].forEach(id=>$(id).disabled=active);
  const key=JSON.stringify([doc.videos,doc.pairs,doc.clocks,doc.clock_warnings,doc.match_summary,doc.match_errors]);
  if (key === renderKey) return; renderKey=key;
  const existing=new Set(doc.videos.map(r=>r.id)); selected=new Set([...selected].filter(id=>existing.has(id)));
  $('video-count').textContent=`${doc.videos.filter(r=>r.kind==='fpv').length} FPV · ${doc.videos.filter(r=>r.kind==='stick').length} StickCam`;
  $('fpv-list').innerHTML=list('fpv'); $('stick-list').innerHTML=list('stick');
  document.querySelectorAll('[data-video]').forEach(input=>input.onchange=()=>{input.checked?selected.add(input.dataset.video):selected.delete(input.dataset.video); document.querySelector('input[name="scope"][value="selected"]').checked=true; selectionLabel();}); selectionLabel();
  for (const kind of ['fpv','stick']) { const select=$(`manual-${kind}`), previous=select.value; select.innerHTML=doc.videos.filter(r=>r.kind===kind&&r.metadata).map(r=>`<option value="${r.id}">${escape(r.name)}</option>`).join(''); if(previous)select.value=previous; }
  $('clock-info').innerHTML=(doc.clocks||[]).map(m=>`<p><strong>${m.method==='modified'?'Modified-date':'Filename'} clock:</strong> ${m.delta>=0?'+':''}${m.delta.toFixed(2)}s · ${m.independent_flights} confirmed flight${m.independent_flights!==1?'s':''} · ${m.consistent?(m.tentative?'tentative, one flight':'consistent'):'conflicting'}<br>${m.anchors.map(a=>`Modified date difference: ${a.modified_difference>=0?'+':''}${a.modified_difference.toFixed(2)}s`).join('<br>')}</p>`).join('') || '<p>No camera clock learned yet. Confirm a reviewed pair to suggest other files.</p>';
  $('clock-info').innerHTML+=(doc.clock_warnings||[]).map(w=>`<p class="error">${escape(w)}</p>`).join('');
  const ms=doc.match_summary; $('match-summary').textContent=ms?`Compared ${ms.fpv} FPV clips against ${ms.stick} StickCam clips (${ms.comparisons} comparisons). ${ms.candidates} audio candidates. Scores measure evidence strength, not a match probability.`:'';
  $('match-errors').innerHTML=(doc.match_errors||[]).map(e=>`<p class="hint error">${escape(e)}</p>`).join('');
  const rank=p=>p.confirmed?0:p.confidence==='Strong'?1:p.method==='timestamp'?3:2;
  const pairs=[...doc.pairs].sort((a,b)=>rank(a)-rank(b)||(b.score||0)-(a.score||0));
  $('pair-count').textContent=`${pairs.length} candidates · ${pairs.filter(p=>p.confirmed&&!p.stale).length} confirmed`;
  $('pairs-list').innerHTML=pairs.length?`<table class="pair-table"><thead><tr><th>Recordings</th><th>Evidence</th><th>Common footage</th><th></th></tr></thead><tbody>${pairs.map(p=>{const e=p.evidence?.sections;return `<tr data-pair-row="${p.id}" class="${p.id===pairId?'active':''}"><td class="names"><strong>${escape(record(p.fpv)?.name || 'Missing FPV file')}</strong><br>${escape(record(p.stick)?.name || 'Missing StickCam file')}</td><td><span class="badge ${p.confirmed?'confirmed':p.method==='timestamp'?'timestamp':p.confidence.toLowerCase()}">${p.stale?'Source changed':p.confirmed?'Confirmed':escape(p.confidence)}</span>${p.score!=null?`<br><small>Evidence ${Math.round(p.score*100)}/100</small>`:''}${e?`<br><small>${e.correlated_sections}/${e.usable_sections} agreeing sections</small>`:''}${p.method==='timestamp'?`<br><small>${p.clock_method} dates · review required</small>`:''}</td><td>${duration(p.overlap_duration)}<br><small>FPV ${fmt(p.fpv_start)}<br>StickCam ${fmt(p.radio_start)}</small></td><td><button data-pair="${p.id}" ${p.stale?'disabled':''}>Review</button></td></tr>`;}).join('')}</tbody></table>`:'<div class="empty">Run audio matching to find candidate pairs, or choose a known pair manually below.</div>';
  document.querySelectorAll('[data-pair]').forEach(b=>b.onclick=()=>openPair(b.dataset.pair,{scrollToPreview:true}).catch(e=>notice(e.message,true)));
  if (pairId && !currentPair()) clearReview(); else if(pairId)updateReview();
  renderExports(doc.exports||[], 'exports');
}
function renderExports(records, target) {
  $(target).innerHTML=records.length?records.map(e=>`<div class="export-row"><span><strong>${escape(e.session_name)}</strong><br><small>${e.pairs} pair${e.pairs!==1?'s':''} · ${e.profile.toUpperCase()} · ${e.fps}fps · ${new Date(e.created*1000).toLocaleString()}</small></span><a href="/api/exports/${e.session}/${e.id}/download">Download ZIP</a></div>`).join(''):'<p class="hint">No completed exports yet.</p>';
}
async function refreshExports() { const all=await api('/api/exports'), key=JSON.stringify(all);if(key!==exportKey){exportKey=key;renderExports(all,'saved-exports');} }
function updateReview() {
  const p=currentPair(); if(!p)return;
  $('review-name').textContent=record(p.fpv)?.name+' + '+record(p.stick)?.name;
  $('fpv-title').textContent='FPV · '+record(p.fpv)?.name; $('stick-title').textContent='StickCam · '+record(p.stick)?.name;
  $('review-details').textContent=`${p.confirmed?'Confirmed alignment':p.confidence} · common footage ${duration(p.overlap_duration)} · FPV ${fmt(p.fpv_start)}–${fmt(p.fpv_start+p.overlap_duration)} · StickCam ${fmt(p.radio_start)}–${fmt(p.radio_start+p.overlap_duration)}`;
  $('offset').value=p.offset.toFixed(3); $('seek').max=p.overlap_duration;
  $('unconfirm').hidden=!p.confirmed; $('confirm').textContent=p.confirmed?'Confirmed · refresh suggestions':'Confirm this pair & suggest others';
}
async function loadVideo(v, r, start, generation) {
  const current=()=>generation===token;
  const base=`/api/sessions/${sid}/videos/${r.id}`;
  const notify=(text,error)=>{if(current()){$('preview-status').textContent=text;if(error)notice(text,true);}};
  if($('preview-mode').value==='auto' && ['h264','vp8','vp9','av1'].includes(r.metadata.codec)) {
    try { await new Promise((resolve,reject)=>{
      const timeout=setTimeout(()=>finish(new Error('Original video did not load')),12000);
      function finish(error){clearTimeout(timeout);v.removeEventListener('loadeddata',ready);v.removeEventListener('error',failed);error?reject(error):resolve();}
      function ready(){if(current()){v.currentTime=start;}finish();} function failed(){finish(new Error('Original codec is not supported'));}
      v.addEventListener('loadeddata',ready,{once:true});v.addEventListener('error',failed,{once:true});v.src=base+'/original';v.load();
    }); if(current())notify('Playing originals · no preview conversion needed.'); return;
    } catch { if(!current())return; }
  }
  await loadFastPreview(v,base+'/preview',current,notify,start);
}
async function openPair(id, {scrollToPreview=false} = {}) {
  pause(); releaseAllPreviews(); const generation=++token; pairId=id; const p=currentPair();if(!p)throw new Error('Pair no longer available');
  loading=true; $('review').hidden=false; $('play').disabled=true; $('preview-status').textContent='Loading both video previews…'; updateReview();
  if (scrollToPreview) {
    $('pairs-section').open=true;
    requestAnimationFrame(()=>{
      if (generation!==token) return;
      $('review').scrollIntoView({block:'start',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
    });
  }
  document.querySelectorAll('[data-pair-row]').forEach(row=>row.classList.toggle('active',row.dataset.pairRow===id));
  $('seek').value=0; $('trim-start').value=0; $('trim-end').value='';
  traces={}; const fs=record(p.fpv),ss=record(p.stick);
  const tracePromise=Promise.all([api(`/api/sessions/${sid}/videos/${fs.id}/audio`),api(`/api/sessions/${sid}/videos/${ss.id}/audio`)]).then(([f,s])=>{if(generation===token){traces={fpv:f,stick:s};drawCharts();}}).catch(e=>{if(generation===token)notice(`Audio trends unavailable: ${e.message}`,true);});
  try {
    const loaded=await Promise.allSettled([loadVideo(fpv,fs,p.fpv_start,generation),loadVideo(stick,ss,p.radio_start,generation)]);
    if(generation!==token)return;
    const failed=loaded.find(r=>r.status==='rejected');if(failed)throw failed.reason;
    $('play').disabled=false; audioChoice(); seek(0);
  } finally {if(generation===token)loading=false;await tracePromise;}
}
function seek(at) {
  const p=currentPair();if(!p)return;
  at=Math.max(0,Math.min(Number(at)||0,p.overlap_duration-.04));
  if(fpv.readyState>=1)fpv.currentTime=p.fpv_start+at;if(stick.readyState>=1)stick.currentTime=p.radio_start+at;
  $('seek').value=at;drawCharts(at);
}
function audioChoice() {fpv.muted=$('listen').value!=='fpv';stick.muted=$('listen').value!=='stick';}
async function play() {if(loading||!currentPair())return;playing=true;audioChoice();if(Number($('seek').value)>=currentPair().overlap_duration-.15)seek(0);try{await Promise.all([fpv.play(),stick.play()]);}catch(e){pause();notice(e.message,true);}}
function draw(canvas,trace,p,isStick,at) {
  const width=Math.max(400,canvas.clientWidth),height=110;canvas.width=width;const ctx=canvas.getContext('2d');ctx.clearRect(0,0,width,height);
  if(!p)return; const start=isStick?p.radio_start:p.fpv_start, span=p.overlap_duration;
  ctx.fillStyle='#54cb7d33';for(const w of p.evidence?.sections?.windows||[]){if(!w.matched)continue;const begin=w.start-p.radio_start,end=w.end-p.radio_start;ctx.fillRect(Math.max(0,begin/span*width),0,Math.max(0,(Math.min(span,end)-Math.max(0,begin))/span*width),height);}
  ctx.strokeStyle=isStick?'#ef7669':'#49a7f2';ctx.lineWidth=1.4;ctx.beginPath();let previous=null;
  for(let i=0;i<(trace?.time?.length||0);i++){const t=trace.time[i]-start;if(t<0||t>span){previous=null;continue;}const x=t/span*width,y=height/2-(trace.energy[i]||0)*height/12; if(previous!=null && trace.segments[i]===trace.segments[i-1] && trace.time[i]-trace.time[i-1]<.3)ctx.lineTo(x,y);else ctx.moveTo(x,y);previous=i;}ctx.stroke();
  ctx.strokeStyle='#f5f6fa';ctx.lineWidth=1;const x=at/span*width;ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,height);ctx.stroke();
  if(!trace?.time?.length){ctx.fillStyle='#abb3c5';ctx.font='12px system-ui';ctx.fillText('No saved audio fingerprint for this recording',12,24);}
}
function drawCharts(at=Number($('seek').value)||0){const p=currentPair();draw($('fpv-chart'),traces.fpv,p,false,at);draw($('stick-chart'),traces.stick,p,true,at);}
setInterval(()=>{
  const p=currentPair();if(!p||loading)return;
  let at=Math.max(0,fpv.currentTime-p.fpv_start);
  if(playing){
    if(at>=p.overlap_duration-.05){pause();at=p.overlap_duration;}
    else if(fpv.readyState<3||stick.readyState<3||fpv.seeking||stick.seeking){fpv.pause();stick.pause();}
    else{if(Math.abs(stick.currentTime-(p.radio_start+at))>.12){stick.pause();stick.currentTime=p.radio_start+at;}else{if(fpv.paused)fpv.play().catch(e=>{pause();notice(e.message,true);});if(stick.paused)stick.play().catch(e=>{pause();notice(e.message,true);});}}
  }
  $('seek').value=at;$('common-time').textContent=`Common ${fmt(at)} / ${fmt(p.overlap_duration)}`;
  $('fpv-time').textContent=`Source ${fmt(fpv.currentTime)}`;$('stick-time').textContent=`Source ${fmt(stick.currentTime)}`;drawCharts(at);
},150);
async function alignment(confirm=false, offset=Number($('offset').value)) {
  const p=currentPair();if(!p)throw new Error('Open a pair first');pause();
  if(confirm && Math.abs(p.offset-offset)>.00001)throw new Error('Apply the new offset and preview the alignment before confirming it.');
  const was=p.offset;doc=await post(`/api/sessions/${sid}/pairs`,{fpv:p.fpv,stick:p.stick,offset,confirmed:confirm});renderKey='';render();
  if(Math.abs(was-offset)>.00001)seek(0);
  notice(confirm?'Pair confirmed. Related timestamp suggestions are now available.':'Alignment saved; confirm it after reviewing.');
}
async function browse(path) {
  $('folder-error').textContent='';
  try {
    const info=await api(`/api/browse?path=${encodeURIComponent(path||'')}`);$('browse-path').value=info.path;
    $('browse-up').onclick=()=>browse(info.parent);
    $('folder-count').textContent=`${info.entries.filter(p=>p.folder).length} folders · ${info.entries.filter(p=>!p.folder).length} video files`;
    $('browse-shortcuts').innerHTML=info.shortcuts.map(p=>`<button data-shortcut="${escape(p)}" class="quiet">${escape(p)}</button>`).join('');
    $('browse-shortcuts').querySelectorAll('button').forEach(b=>b.onclick=()=>browse(b.dataset.shortcut));
    $('folder-entries').innerHTML=info.entries.map(p=>p.folder?`<button data-folder="${escape(p.path)}">📁 ${escape(p.name)}</button>`:`<div class="file">▸ ${escape(p.name)}</div>`).join('')||'<p class="hint" style="padding:12px">This folder is empty.</p>';
    $('folder-entries').querySelectorAll('[data-folder]').forEach(b=>b.onclick=()=>browse(b.dataset.folder));
    $('folder-use').disabled=false;
  }catch(e){$('folder-error').textContent=e.message;$('folder-use').disabled=true;}
}
document.querySelectorAll('[data-browse]').forEach(b=>b.onclick=()=>{browsing=b.dataset.browse;$('folder-title').textContent=`Choose ${browsing==='fpv'?'FPV video':'StickCam video'} source folder`;$('folder-dialog').showModal();browse($(`${browsing}-folder`).value||(browsing==='stick'?$('fpv-folder').value:''));});
action('folder-close',()=>$('folder-dialog').close());action('folder-use',()=>{$(`${browsing}-folder`).value=$('browse-path').value;$('folder-dialog').close();});action('browse-go',()=>browse($('browse-path').value));$('browse-path').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();browse(e.target.value);}};
action('new-session',()=>{clearReview();sid=null;doc=null;localStorage.removeItem('audio-pairing-session');$('workspace').hidden=true;$('session-controls').hidden=true;$('sources-section').hidden=false;$('sources-section').open=true;$('session-name').focus();sessionKey='';refreshSessions();});
$('create-form').onsubmit=async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{const s=await post('/api/sessions',{name:$('session-name').value,fpv:$('fpv-folder').value,stick:$('stick-folder').value,recursive:$('recursive').checked});await chooseSession(s.id);}catch(e){notice(e.message,true);}finally{b.disabled=false;}};
action('rename',async()=>{doc=await api(`/api/sessions/${sid}`,{method:'PATCH',body:JSON.stringify({name:$('rename-name').value})});await refreshSessions();});
action('rescan',async()=>{await post(`/api/sessions/${sid}/scan`);await poll();});
action('cancel',async()=>{const r=await post(`/api/sessions/${sid}/cancel`);notice(r.message);});
action('delete',async()=>{await api(`/api/sessions/${sid}`,{method:'DELETE'});$('new-session').click();notice('Session data removed. Original recordings and exports are kept.');sessionKey='';await refreshSessions();await refreshExports();});
action('clear-selection',()=>{selected.clear();document.querySelectorAll('[data-video]').forEach(i=>i.checked=false);selectionLabel();});
action('find',async()=>{if(!sid)return;const scope=document.querySelector('input[name="scope"]:checked').value;if(scope==='selected'&&!selected.size)throw new Error('Select at least one recording in the video lists.');await post(`/api/sessions/${sid}/match`,{selected:scope==='selected'?[...selected]:[],fraction:Number($('fraction').value),boundary:Number($('boundary').value),use_filenames:$('filenames').checked,modified_kind:$('modified-kind').value,min_overlap:2});await poll();});
async function saveClockSettings(){if(!sid)return;try{doc=await api(`/api/sessions/${sid}/clocks`,{method:'PATCH',body:JSON.stringify({use_filenames:$('filenames').checked,modified_kind:$('modified-kind').value})});renderKey='';render();}catch(e){notice(e.message,true);}}
$('filenames').onchange=saveClockSettings;$('modified-kind').onchange=saveClockSettings;
action('manual-add',async()=>{const f=$('manual-fpv').value,s=$('manual-stick').value;if(!f||!s)throw new Error('Wait for scanning, then choose one video of each type');doc=await post(`/api/sessions/${sid}/pairs`,{fpv:f,stick:s,offset:Number($('manual-offset').value),confirmed:false});renderKey='';render();await openPair(doc.pairs.find(p=>p.fpv===f&&p.stick===s).id);});
action('play',play);action('pause',pause);$('seek').oninput=e=>{pause();seek(e.target.value);};$('listen').onchange=audioChoice;$('speed').onchange=()=>{fpv.playbackRate=stick.playbackRate=Number($('speed').value);};$('preview-mode').onchange=()=>pairId&&openPair(pairId).catch(e=>notice(e.message,true));
action('apply-offset',()=>alignment(false));action('confirm',()=>alignment(true));action('unconfirm',()=>alignment(false));
document.querySelectorAll('[data-nudge]').forEach(b=>b.onclick=()=>{$('offset').value=(Number($('offset').value)+Number(b.dataset.nudge)).toFixed(3);alignment(false).catch(e=>notice(e.message,true));});
$('show-audio').onchange=e=>{$('audio-charts').hidden=!e.target.checked;if(e.target.checked)drawCharts();};window.addEventListener('resize',()=>drawCharts());
action('export',async()=>{const all=$('export-scope').value==='all',p=currentPair();const pairs=all?doc.pairs.filter(p=>p.confirmed&&!p.stale).map(p=>p.id):(p?.confirmed&&!p.stale?[p.id]:[]);if(!pairs.length)throw new Error('Confirm the current pair, or select all confirmed pairs.');await post(`/api/sessions/${sid}/export`,{pairs,fps:Number($('export-fps').value),profile:$('export-profile').value,trim_start:Number($('trim-start').value),trim_end:$('trim-end').value===''?null:Number($('trim-end').value)});await poll();});
async function poll(){if(pollBusy)return;pollBusy=true;try{if(sid){const old=doc?.job?.status;doc=await api(`/api/sessions/${sid}`);render();if(['running','queued'].includes(old)&&doc.job?.status==='failed')notice(doc.job.message,true);}await refreshSessions();await refreshExports();}catch(e){if(!doc)notice(e.message,true);}finally{pollBusy=false;}}
async function boot(){try{const sys=await api('/api/system');if(!sys.ffmpeg||!sys.ffprobe)notice('Install FFmpeg and ffprobe on this machine to read and export recordings.',true);if(sid){try{await chooseSession(sid);}catch{sid=null;localStorage.removeItem('audio-pairing-session');}}await poll();}catch(e){notice(`Could not connect to the app: ${e.message}`,true);}setInterval(poll,2000);}
boot();
