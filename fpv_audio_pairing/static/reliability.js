// Project/review tools share the existing player and request handling.
import {renderFlightView} from './flight-view.js?v=2';
const $ = id => document.getElementById(id);
let context, lastKey = '', lastPair = '', diagnosticReport;
const state = p => p.confirmed ? 'confirmed' : p.review_state || 'candidate';
export function filteredPairs(pairs) {
  const filter=$('review-filter').value;
  return pairs.filter(p=>filter==='all' || filter==='actionable' && state(p)==='candidate' ||
    filter==='strong' && state(p)==='candidate' && p.confidence==='Strong' || state(p)===filter);
}
function download(value,name) {
  const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
export function installReliability(ctx) {
  context=ctx;
  const {action,api,post,getDoc,getSid,notice,setDoc,pause,seek}=ctx;
  async function save(path, body, method='POST') {
    pause();setDoc(await api(`/api/sessions/${getSid()}${path}`,{method,body:JSON.stringify(body)}));
  }
  action('project-open',()=>$('project-file').click());
  $('project-file').onchange=async event=>{
    const file=event.target.files[0];if(!file)return;
    try {
      if(file.size>128*1024*1024)throw new Error('Choose a project smaller than 128 MiB.');
      const doc=await api('/api/projects/open',{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
      await ctx.chooseSession(doc.id);$('project-tools').open=true;
      notice('Project opened as a new session. Relink its recordings before playback or export.');
    }catch(error){notice(error.message,true);}finally{event.target.value='';}
  };
  for(const id of ['project-save','project-bundle'])$(id).onclick=event=>{
    if(['running','queued'].includes(getDoc()?.job?.status)){event.preventDefault();notice('Wait for the current task before saving a project.',true);}
  };
  action('relink',async()=>{await post(`/api/sessions/${getSid()}/relink`,{fpv:$('relink-fpv-folder').value,stick:$('relink-stick-folder').value});await ctx.poll();});
  action('backups-load',async()=>{
    const items=await api(`/api/sessions/${getSid()}/backups`);
    $('backup-choice').innerHTML=items.map(b=>`<option value="${ctx.escape(b.name)}">${new Date(b.created*1000).toLocaleString()}</option>`).join('');
    if(!items.length)notice('No backup yet. A snapshot is saved before later changes.');
  });
  action('backup-restore',async()=>{if(!$('backup-choice').value)throw new Error('Show backups and choose one first.');await save('/restore',{name:$('backup-choice').value});notice('Backup restored. Exports and originals were preserved.');});
  action('resume',async()=>{await post(`/api/sessions/${getSid()}/resume`);await ctx.poll();});
  $('review-filter').onchange=()=>ctx.rerender();
  action('review-next',async()=>{
    const candidates=getDoc().pairs.filter(p=>!p.stale&&state(p)==='candidate').sort((a,b)=>(b.confidence==='Strong')-(a.confidence==='Strong')||(b.score||0)-(a.score||0));
    const at=candidates.findIndex(p=>p.id===ctx.getPair()?.id), next=candidates[(at+1)%candidates.length];
    if(!next)throw new Error('No candidates awaiting review. Check Review later or unmatched recordings.');
    await ctx.openPair(next.id,{scrollToPreview:true});
  });
  for(const [id,value] of [['review-later','later'],['review-reject','rejected'],['review-restore','candidate']])action(id,async()=>{
    const p=ctx.getPair();if(!p)throw new Error('Open a pair first.');
    await save(`/pairs/${p.id}/review`,{state:value},'PATCH');notice(`Pair ${value==='candidate'?'returned to review':value==='later'?'saved for later':'rejected'}.`);
  });
  action('review-middle',()=>{pause();seek(ctx.getPair().overlap_duration/2);});
  action('review-end',()=>{pause();seek(Math.max(0,ctx.getPair().overlap_duration-5));});
  action('checkpoint-fill',()=>{$('checkpoint-fpv').value=ctx.fpv.currentTime.toFixed(3);$('checkpoint-stick').value=ctx.stick.currentTime.toFixed(3);});
  action('checkpoint-add',async()=>{
    const p=ctx.getPair();if(!p)throw new Error('Open a pair first.');
    if(!$('checkpoint-fpv').value||!$('checkpoint-stick').value)throw new Error('Enter source event times independently.');
    await save(`/pairs/${p.id}/checkpoints`,{fpv_time:Number($('checkpoint-fpv').value),stick_time:Number($('checkpoint-stick').value),note:$('checkpoint-note').value});
  });
  for(const [id,match] of [['reference-match',true],['reference-nonmatch',false]])action(id,async()=>{
    const p=ctx.getPair();if(!p)throw new Error('Open a pair first.');
    await save(`/pairs/${p.id}/reference`,{match,expected_offset:$('reference-offset').value===''?null:Number($('reference-offset').value),known_identity:$('reference-known').checked,tolerance:Number($('reference-tolerance').value),note:$('reference-note').value});
    notice('Known-answer label saved. Run reference validation to measure the matcher.');
  });
  action('validate-references',async()=>{await post(`/api/sessions/${getSid()}/validate`,{boundary:Number($('validation-boundary').value)});$('validation-section').open=true;await ctx.poll();});
  action('validation-download',()=>{if(!getDoc()?.benchmark)throw new Error('Run reference validation first.');download(getDoc().benchmark,'flight-sync-validation.json');});
  action('diagnostics-run',async()=>{diagnosticReport=await api(`/api/diagnostics${getSid()?`?sid=${getSid()}`:''}`);$('diagnostics-results').textContent=JSON.stringify(diagnosticReport,null,2);});
  action('diagnostics-download',async()=>{diagnosticReport=await api(`/api/diagnostics${getSid()?`?sid=${getSid()}`:''}`);download(diagnosticReport,'flight-sync-support.json');});
}
export function renderReliability(doc) {
  if(!context)return;
  const {escape,api,getPair,setDoc,fmt,notice}=context, sid=context.getSid(), p=getPair();
  const active=['running','queued'].includes(doc.job?.status)&&!doc.recovery_required;
  $('resume').hidden=active || !doc.job?.resume || !['interrupted','failed','cancelled'].includes(doc.job?.status);
  for(const id of ['relink','backup-restore','validate-references','review-reject','review-later','review-restore','checkpoint-add','reference-match','reference-nonmatch','review-next'])$(id).disabled=active || !!doc.recovery_required;
  $('backup-restore').disabled=active;
  $('project-tools').hidden=false;
  for(const [id,bundle] of [['project-save',false],['project-bundle',true]]){$(id).hidden=false;$(id).href=`/api/sessions/${sid}/project${bundle?'?bundle=true':''}`;}
  const missing=doc.videos.filter(r=>r.missing).length;
  $('recovery-banner').hidden=!doc.recovery_required && !missing;
  $('recovery-open').hidden=!doc.recovery_required && !missing;
  $('recovery-banner').textContent=doc.recovery_required?'The current session JSON is unreadable. Show backups and restore one before continuing.':`${missing} recordings need relinking. Open Relink recordings below.`;
  const counts=doc.review_summary||{};
  $('review-summary').textContent=context.isExpert()?`${counts.confirmed||0} FPV parts confirmed · ${counts.awaiting||0} awaiting review · ${counts.later||0} for later · ${counts.unmatched||0} unmatched · ${counts.unsearched||0} unsearched · ${counts.missing||0} unavailable`:`${counts.confirmed||0} confirmed · ${counts.awaiting||0} awaiting review · ${counts.unmatched||0} unmatched${counts.later?` · ${counts.later} for later`:''}${counts.missing?` · ${counts.missing} unavailable`:''}`;
  renderFlightView(doc);
  if(p){
    if(lastPair!==`${sid}:${p.id}`){
      const reference=(doc.references||[]).find(r=>r.id===p.id);
      lastPair=`${sid}:${p.id}`;$('reference-offset').value=reference?.expected_offset==null?'':reference.expected_offset.toFixed(3);$('independent-check').checked=p.verification==='independent';
      $('reference-note').value=reference?.note||'';
      $('reference-known').checked=false;
      $('checkpoint-fpv').value='';$('checkpoint-stick').value='';$('checkpoint-note').value='';
    }
    const check=p.sync_check || {};
    $('sync-check').textContent=`${check.message||''}${check.drift_seconds!=null?` Estimated change across overlap: ${check.drift_seconds.toFixed(3)}s.`:''}`;
    $('sync-check').className=['drift','offset_mismatch'].includes(check.status)?'hint error':'hint';
    const points=(p.sync_points||[]).map(item=>`<div class="checkpoint-row">FPV ${fmt(item.fpv_time)} / StickCam ${fmt(item.stick_time)} · offset ${(item.stick_time-item.fpv_time).toFixed(3)}s · ${escape(item.note)} <button data-remove-point="${item.id}" class="quiet">Remove</button></div>`).join('');
    if($('sync-points').dataset.key!==points){$('sync-points').dataset.key=points;$('sync-points').innerHTML=points;
      $('sync-points').querySelectorAll('[data-remove-point]').forEach(b=>b.onclick=async()=>{try{setDoc(await api(`/api/sessions/${sid}/pairs/${p.id}/checkpoints/${b.dataset.removePoint}`,{method:'DELETE'}));}catch(e){notice(e.message,true);}});}
  }
  const key=JSON.stringify([sid,doc.flights,doc.references,doc.benchmark,doc.videos.map(r=>[r.id,r.no_counterpart,r.match_checked,r.match_outcome]),doc.pairs.map(p=>[p.id,state(p)]),doc.relink_report]);
  if(lastKey===key)return;lastKey=key;
  $('relink-report').textContent=(doc.relink_report||[]).map(r=>`${r.name}: ${r.status}`).join('\n');
  const unresolved=doc.videos.filter(r=>r.kind==='fpv'&&!doc.pairs.some(p=>p.fpv===r.id&&p.confirmed&&!p.stale));
  $('unmatched-list').innerHTML=unresolved.map(r=>`<div class="unmatched-row"><span><strong>${escape(r.name)}</strong><small>${escape(r.no_counterpart?'Marked no counterpart':r.match_outcome?.reason||'Not yet searched')}${r.match_outcome?.boundary?` · ${r.match_outcome.boundary}s sampled per end`:''}</small></span><button data-unmatched="${r.id}" data-value="${!r.no_counterpart}">${r.no_counterpart?'Allow searches again':'Mark no counterpart'}</button></div>`).join('')||'<p class="hint">All FPV recordings have a confirmed pair.</p>';
  $('unmatched-list').querySelectorAll('[data-unmatched]').forEach(b=>b.onclick=async()=>{try{setDoc(await api(`/api/sessions/${sid}/videos/${b.dataset.unmatched}/counterpart`,{method:'PATCH',body:JSON.stringify({value:b.dataset.value==='true'})}));}catch(e){notice(e.message,true);}});
  $('reference-list').innerHTML=(doc.references||[]).map(r=>`<div class="reference-row"><span>${escape(doc.videos.find(v=>v.id===r.fpv)?.name)} / ${escape(doc.videos.find(v=>v.id===r.stick)?.name)}<small>Known ${r.match?`match · ${r.expected_offset==null?'timing not measured':`offset ${r.expected_offset.toFixed(3)}s`}`:'non-match'}</small></span><button data-remove-reference="${r.id}">Remove label</button></div>`).join('')||'<p class="hint">No known-answer labels yet.</p>';
  $('reference-list').querySelectorAll('[data-remove-reference]').forEach(b=>b.onclick=async()=>{try{setDoc(await api(`/api/sessions/${sid}/references/${b.dataset.removeReference}`,{method:'DELETE'}));}catch(e){notice(e.message,true);}});
  const report=doc.benchmark;
  $('validation-results').innerHTML=report?`<h4>Saved run: ${new Date(report.created*1000).toLocaleString()}</h4><p>${report.boundary}s sampled per end · ${report.timing_references||0} independently measured timing references</p><p>Correct matches: ${report.counts.true_positive} · false positives: ${report.counts.false_positive} · missed/wrong-offset matches: ${report.counts.false_negative} · correct non-matches: ${report.counts.true_negative} · skipped: ${report.counts.skipped}</p><p>Precision ${report.precision==null?'not measured':(100*report.precision).toFixed(1)+'%'} · recall ${report.recall==null?'not measured':(100*report.recall).toFixed(1)+'%'} on this collection.</p><p class="hint">${escape(report.note)} Re-run after changing labels or sources.</p>${report.rows.map(r=>`<p>${escape(r.fpv_name)} / ${escape(r.stick_name)}: <strong>${escape(r.status.replaceAll('_',' '))}</strong>${r.offset_error!=null?` · timing error ${r.offset_error.toFixed(3)}s`:''}${r.reason||r.reasons?.length?` · ${escape(r.reason||r.reasons.join('; '))}`:''}</p>`).join('')}`:'';
}
