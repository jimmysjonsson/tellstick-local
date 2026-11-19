'use strict';
let state=null,tab='dashboard',editing=null,csrf='',busy=false,dashboardDraft=[],dashboardDraftProfile=null;
let profileName='',profilePrompted=false;
const profileStorageKey='tellstick.profile.v1';
try{const saved=localStorage.getItem(profileStorageKey);if(saved&&saved.length<=60)profileName=saved}catch{}
const $=s=>document.querySelector(s);
const h=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const on=v=>v===true||v===1||v==='1';
const names={dashboard:'Dashboard',devices:'Devices',schedules:'Schedules',events:'Events',sensors:'Sensors',activity:'Activity'};
const action=v=>({1:'On',2:'Off',16:'Dim'}[Number(v)]||'Unknown');
const collator=new Intl.Collator('sv',{numeric:true,sensitivity:'base'});
const byName=items=>[...items].sort((a,b)=>collator.compare(a.name||'',b.name||'')||String(a.id).localeCompare(String(b.id)));
const deviceName=id=>state.devices.find(d=>String(d.id)===String(id))?.name||'Unknown device';
const sensorName=id=>{let s=state.sensors.find(s=>String(s.id)===String(id));return s?.name||`${s?.protocol||'Sensor'} · ${s?.sensorId||id}`};
const openHistories=new Set(),historyRanges=new Map(),historyCache=new Map();
function dateText(seconds,full=false){if(!seconds)return '—';return new Intl.DateTimeFormat('en-GB',{timeZone:state.status.timezone,day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',...(full?{year:'numeric'}:{})}).format(new Date(seconds*1000))}
function timeText(seconds){return new Intl.DateTimeFormat('en-GB',{timeZone:state.status.timezone,hour:'2-digit',minute:'2-digit'}).format(new Date(seconds*1000))}
function toast(text){$('#toast').textContent=text;$('#toast').classList.add('show');setTimeout(()=>$('#toast').classList.remove('show'),4500)}
async function post(path,data){const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(data)});const value=await response.json();if(!response.ok)throw new Error(value.error||'Operation failed');return value}
async function refresh(){
  if(busy)return;busy=true;const requestedProfile=profileName;
  try{
    const response=await fetch('/api/state'+(requestedProfile?'?profile='+encodeURIComponent(requestedProfile):''));
    if(!response.ok)throw new Error('Controller unavailable');
    const nextState=await response.json();
    if(requestedProfile!==profileName)return;
    state=nextState;csrf=state.csrf;render();
  }catch(error){$('#service-status').textContent='Connection unavailable';$('#service-status').className='pill warn'}
  finally{busy=false}
}
function switchTab(value){tab=value;$('#search').value='';if(state)render()}
function render(){
  const s=state.status;
  $('#hardware-notice').hidden=!!s.rf_enabled;
  $('#title').textContent=names[tab];$('#subtitle').textContent=`${s.location_name} · ${s.timezone}`;
  const live=s.scheduler_heartbeat&&s.now-s.scheduler_heartbeat<10;
  const ruleError=!!s.scheduler_error||!!s.rule_errors?.length;
  $('#service-status').textContent=live?(ruleError?'Rules need review':'Service running'):'Service not responding';
  $('#service-status').className='pill'+(live&&!ruleError?'':' warn');
  $('#pause').textContent=s.scheduler_enabled?'Pause automations':'Resume automations';
  $('#receiver-status').textContent=`Receiver: ${s.receiver_status}${s.receiver_last_event?' · last frame '+timeText(s.receiver_last_event):''}`;
  $('#clock').textContent=dateText(s.now,true);$('#search').placeholder=`Search ${names[tab].toLowerCase()}…`;
  $('#profile').disabled=false;$('#profile').textContent=state.profile?'User: '+state.profile.name:'Choose user';
  $('#profile').title=state.profile?'Change user (currently '+state.profile.name+')':'Choose user';
  $('#customize').disabled=!state.profile;
  $('#customize').hidden=tab!=='dashboard';$('#add').hidden=!['devices','schedules','events'].includes(tab);
  $('#add').textContent='+ Add '+({devices:'device',schedules:'schedule',events:'event'}[tab]||'');
  document.querySelectorAll('nav button').forEach(b=>{b.classList.toggle('selected',b.dataset.tab===tab);b.setAttribute('aria-current',b.dataset.tab===tab?'page':'false')});
  if(!document.activeElement?.matches('#content select'))renderContent();
  if(!state.profile&&!profilePrompted)openProfile();
}
function filtered(items,text){const q=$('#search').value.toLocaleLowerCase();return items.filter(x=>String(text(x)).toLocaleLowerCase().includes(q))}
function deviceCard(d,editable=true){
  const label=action(d.state)+(Number(d.state)===16&&d.statevalue!=null?' · '+Math.round(Number(d.statevalue)/255*100)+'%':'');
  return `<article class="card device-card" data-device-card="${h(d.id)}"><div class="card-top"><div class="device-icon" aria-hidden="true">${d.protocol==='group'?'▦':'◈'}</div><div class="card-name"><h3>${h(d.name)}</h3>${editable?`<p class="detail">${h(d.protocol==='group'?'Group':d.protocol+' · '+(d.model||'switch'))}</p>`:''}</div>${editable?`<button class="edit-icon" data-edit="${h(d.id)}" aria-label="Edit ${h(d.name)}">⋯</button>`:''}</div><div class="device-actions"><span class="pill gray device-state">${h(label)}</span><div class="controls"><button data-command="1" data-device="${h(d.id)}" aria-label="Turn ${h(d.name)} on" ${state.status.rf_enabled?'':'disabled'}>On</button><button data-command="2" data-device="${h(d.id)}" aria-label="Turn ${h(d.name)} off" ${state.status.rf_enabled?'':'disabled'}>Off</button>${Number(d.methods)&16?`<button data-command="16" data-device="${h(d.id)}" aria-label="Dim ${h(d.name)}" ${state.status.rf_enabled?'':'disabled'}>Dim…</button>`:''}</div></div></article>`;
}
function sensorCard(s,withHistory=false){
  const data=Object.fromEntries((s.data||[]).map(x=>[x.name,x.value]));
  const live=s.state_source==='local RF'&&state.status.now-s.lastUpdated<900;
  const expanded=openHistories.has(String(s.id));
  return `<article class="card sensor-card ${withHistory&&expanded?'expanded':''}" data-sensor-card="${h(s.id)}"><div class="card-top"><div class="device-icon" aria-hidden="true">⌁</div><div class="card-name"><h3>${h(sensorName(s.id))}</h3><p class="detail">${h(s.protocol)} · sensor ${h(s.sensorId)}</p></div><span class="pill ${live?'':'gray'}">${live?'Live':'Stale'}</span></div><div class="sensor-readings"><div><span class="reading-label">Temperature</span><div class="reading">${h(data.temp??'—')}<small>°C</small></div></div><div><span class="reading-label">Humidity</span><div class="reading">${h(data.humidity??'—')}<small>%</small></div></div></div><div class="sensor-bottom"><p class="detail">Updated ${h(dateText(s.lastUpdated))}</p>${withHistory?`<button class="secondary" data-history="${h(s.id)}" aria-expanded="${expanded}">${expanded?'Hide':'Show'} history</button>`:`<button class="secondary" data-view-sensor="${h(s.id)}">History</button>`}</div>${withHistory&&expanded?historyPanel(s):''}</article>`;
}
function chart(history,field,title,unit){
  const points=history.points.filter(p=>p[field]!==null&&Number.isFinite(p[field]));
  if(!points.length)return `<section class="history-chart"><h4>${title}</h4><p class="history-empty">No ${title.toLowerCase()} readings in this period.</p></section>`;
  let lo=Math.min(...points.map(p=>p[field])),hi=Math.max(...points.map(p=>p[field]));
  const pad=Math.max((hi-lo)*.12,field==='temp'?.5:1);lo-=pad;hi+=pad;
  if(field==='humidity'){lo=Math.max(0,lo);hi=Math.min(100,hi)}
  const start=history.from,end=history.until;
  const x=t=>52+(t-start)/(end-start)*570,y=v=>18+(hi-v)/(hi-lo)*150;
  let previous=null;
  const path=points.map(p=>{const move=!previous||p.time-previous.time>Math.max(900,history.interval*3);previous=p;return `${move?'M':'L'}${x(p.time).toFixed(2)},${y(p[field]).toFixed(2)}`}).join(' ');
  const ticks=[lo,(lo+hi)/2,hi].map(v=>`<line x1="52" x2="622" y1="${y(v)}" y2="${y(v)}" class="chart-grid"/><text x="44" y="${y(v)+4}" text-anchor="end">${v.toFixed(1)}</text>`).join('');
  const dates=[start,(start+end)/2,end].map((t,i)=>`<text x="${x(t)}" y="191" text-anchor="${i===0?'start':i===2?'end':'middle'}">${h(history.hours===24?timeText(t):new Intl.DateTimeFormat('en-GB',{timeZone:state.status.timezone,day:'2-digit',month:'short'}).format(new Date(t*1000)))}</text>`).join('');
  const dots=points.length<=20?points.map(p=>`<circle cx="${x(p.time)}" cy="${y(p[field])}" r="3" class="chart-dot"/>`).join(''):'';
  return `<section class="history-chart"><h4>${title} <span>${unit}</span></h4><svg viewBox="0 0 640 204" role="img" aria-label="${title} history for ${h(history.hours)} hours" data-chart-field="${field}"><title>${title} history</title><desc>${points.length} plotted readings. Range ${Math.min(...points.map(p=>p[field])).toFixed(1)} to ${Math.max(...points.map(p=>p[field])).toFixed(1)} ${unit}.</desc>${ticks}${dates}<path d="${path}" class="chart-line ${field}"/>${dots}<rect x="52" y="12" width="570" height="162" class="chart-hit"/></svg><p class="chart-value">Point to the graph to inspect a reading.</p></section>`;
}
function historyPanel(s){
  const id=String(s.id),hours=historyRanges.get(id)||24,key=id+':'+hours,entry=historyCache.get(key);
  const ranges=`<label class="history-range">Period<select data-history-range="${h(id)}">${[[24,'24 hours'],[168,'7 days'],[720,'30 days'],[2160,'90 days']].map(([n,t])=>`<option value="${n}" ${n===hours?'selected':''}>${t}</option>`).join('')}</select></label>`;
  let body='<p class="history-empty">Loading history…</p>';
  if(entry?.data){const d=entry.data;body=chart(d,'temp','Temperature','°C')+chart(d,'humidity','Humidity','%')+`<p class="field-note">${d.interval===60?'Latest reading per minute':d.interval/60+'-minute averages'} · Saved locally for 90 days · ${h(state.status.timezone)}</p>`}
  if(entry?.error)body=`<p class="form-error">${h(entry.error)}</p>`;
  if(!entry||(!entry.loading&&Date.now()-entry.loaded>60000))queueMicrotask(()=>loadHistory(id,hours));
  return `<div class="sensor-history">${ranges}${body}</div>`;
}
async function loadHistory(id,hours){
  const key=id+':'+hours,old=historyCache.get(key);
  if(old?.loading||(old&&Date.now()-old.loaded<60000))return;
  const entry={...old,loading:true};historyCache.set(key,entry);
  try{const response=await fetch('/api/sensors/'+encodeURIComponent(id)+'/history?hours='+hours);const data=await response.json();if(!response.ok)throw new Error(data.error||'Unable to load history');entry.data=data;entry.error=null}
  catch(error){entry.error=error.message}
  finally{entry.loading=false;entry.loaded=Date.now();if(tab==='sensors'&&openHistories.has(id))renderContent()}
}
function bindCharts(content){
  content.querySelectorAll('[data-chart-field]').forEach(svg=>{
    const card=svg.closest('[data-sensor-card]'),id=card.dataset.sensorCard,hours=historyRanges.get(id)||24;
    const data=historyCache.get(id+':'+hours)?.data,field=svg.dataset.chartField;if(!data)return;
    const inspect=event=>{
      const matrix=svg.getScreenCTM();if(!matrix)return;
      const point=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse());
      const t=data.from+Math.max(0,Math.min(1,(point.x-52)/570))*(data.until-data.from);
      const points=data.points.filter(p=>p[field]!==null&&Number.isFinite(p[field]));
      const nearest=points.reduce((best,p)=>!best||Math.abs(p.time-t)<Math.abs(best.time-t)?p:best,null);
      if(nearest)svg.parentElement.querySelector('.chart-value').textContent=dateText(nearest.time)+' · '+nearest[field].toFixed(1)+(field==='temp'?' °C':' %');
    };
    svg.addEventListener('pointermove',inspect);svg.addEventListener('pointerdown',inspect);
  });
}
function renderContent(){
  let items=state[tab]||[];const content=$('#content');
  const sameTab=content.dataset.tab===tab;
  const pageScroll={left:window.scrollX,top:window.scrollY};
  const contentScroll={left:content.scrollLeft,top:content.scrollTop};
  const listScroll=new Map([...content.querySelectorAll('[data-scroll-key]')].map(element=>
    [element.dataset.scrollKey,{left:element.scrollLeft,top:element.scrollTop}]));
  if(tab==='dashboard'){
    items=filtered(state.profile?state.dashboard:[],item=>item.kind==='devices'?deviceName(item.id):sensorName(item.id));
    content.innerHTML=items.length?'<div class="cards dashboard-cards">'+items.map(item=>{const record=state[item.kind].find(r=>String(r.id)===item.id);return record?(item.kind==='devices'?deviceCard(record,false):sensorCard(record)):''}).join('')+'</div>':`<div class="empty">${$('#search').value?'No matching dashboard items.':'Make this dashboard yours. Choose devices and sensors, then arrange them in your own order.'}<p><button class="primary" data-customize>Choose items</button></p></div>`;
    if(!state.profile)content.innerHTML='<div class="empty">Choose your name to open your personal Dashboard.<p><button class="primary" data-choose-profile>Choose user</button></p></div>';
  }
  else if(tab==='devices'){
    items=byName(filtered(items,d=>d.name+' '+d.protocol+' '+d.model));
    content.innerHTML='<div class="cards device-cards">'+items.map(d=>deviceCard(d)).join('')+'</div>';
  }
  else if(tab==='sensors'){
    items=filtered(byName(items),s=>sensorName(s.id));
    content.innerHTML='<div class="cards sensor-cards">'+items.map(s=>sensorCard(s,true)).join('')+'</div>';
  }
  else if(tab==='schedules'){
    items=filtered(items,s=>deviceName(s.deviceId)+' '+s.type+' '+action(s.method));
    items.sort((a,b)=>(a.localNextRun||Infinity)-(b.localNextRun||Infinity));
    const next=state.schedules.filter(s=>s.localNextRun).sort((a,b)=>a.localNextRun-b.localNextRun)[0];
    content.innerHTML=`<div class="schedule-next"><span>Next scheduled action</span><strong>${next?h(deviceName(next.deviceId)+' · '+action(next.method)+' · '+dateText(next.localNextRun)):'No active schedules'}</strong></div>`+'<div class="panel" data-scroll-key="schedules-table"><table><thead><tr><th>Active</th><th>Device / action</th><th>When</th><th>Days</th><th>Next run</th><th></th></tr></thead><tbody>'+items.map(s=>`<tr><td><button class="toggle ${on(s.active)?'on':''}" data-toggle="${h(s.id)}" aria-label="${on(s.active)?'Disable':'Enable'} schedule"></button></td><td><strong>${h(deviceName(s.deviceId))}</strong><small>${h(action(s.method))}${Number(s.method)===16?' · '+Math.round(Number(s.methodValue)/255*100)+'%':''}</small></td><td>${h(s.type==='time'?String(s.hour).padStart(2,'0')+':'+String(s.minute).padStart(2,'0'):s.type)}${s.type!=='time'&&Number(s.offset)?' '+h(s.offset)+' min':''}<small>${Number(s.randomInterval)?'Up to '+h(s.randomInterval)+' min random delay':'Exact time'}</small></td><td>${h(daysText(s.weekdays))}</td><td>${h(dateText(s.localNextRun))}</td><td><button data-edit="${h(s.id)}">Edit</button></td></tr>`).join('')+'</tbody></table></div>';
  }
  else if(tab==='events'){
    items=filtered(items,e=>e.description||e.name||'Event');content.innerHTML='<div class="cards">'+items.map(e=>`<article class="card event-card"><div class="card-top"><h3>${h(e.description||e.name||'Event')}</h3><span class="pill ${on(e.active)?'':'gray'}">${on(e.active)?'Active':'Disabled'}</span><button class="edit-icon" data-edit="${h(e.id)}" aria-label="Edit event">⋯</button></div><div class="event-flow"><div class="flow-box">${h(triggerText(e.trigger?.[0]))}</div><span>→</span><div class="flow-box">${h(action(e.action?.[0]?.method))} · ${h(deviceName(e.action?.[0]?.deviceId))}</div></div><p class="detail">${e.validation_error?h(e.validation_error):'Minimum repeat interval '+h(e.minRepeatInterval)+' seconds'}</p></article>`).join('')+'</div>';
  }
  else if(tab==='activity'){
    items=filtered(state.actions,a=>deviceName(a.device)+' '+a.source+' '+a.status);content.innerHTML='<div class="panel" data-scroll-key="activity-table"><table><thead><tr><th>Time</th><th>Device / action</th><th>Source</th><th>Result</th></tr></thead><tbody>'+items.map(a=>`<tr><td>${h(dateText(a.updated))}</td><td><strong>${h(deviceName(a.device))}</strong><small>${h(action(a.method))}</small></td><td>${h(a.source==='manual'?'Manual':a.source.startsWith('schedule:')?'Schedule':'Event')}</td><td><strong class="status-${h(a.status)}">${h(a.status)}</strong><small>${h(a.message)}</small></td></tr>`).join('')+'</tbody></table></div><h3>Recent radio frames</h3><p class="muted">Recent radio observations from the local receiver.</p><div class="cards">'+state.observations.slice(0,6).map(o=>`<article class="card"><h3>${h(o.data.protocol||'Unknown protocol')}</h3><p class="detail">${h(dateText(o.received))} · ${h(o.kind)}</p><p class="data-preview">${h(Object.keys(o.data).join(' · '))}</p></article>`).join('')+'</div>';
  }
  if(!items.length&&!['activity','dashboard','schedules'].includes(tab))content.innerHTML='<div class="empty">No '+h(names[tab].toLowerCase())+' found. '+(['devices','events'].includes(tab)?'Add one to get started.':'Waiting for readings.')+'</div>';
  content.querySelectorAll('[data-choose-profile]').forEach(b=>b.onclick=openProfile);
  content.querySelectorAll('[data-customize]').forEach(b=>b.onclick=customizeDashboard);
  content.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>edit(items.find(x=>String(x.id)===b.dataset.edit)));
  content.querySelectorAll('[data-command]').forEach(b=>b.onclick=async()=>{
    let value=0;
    if(b.dataset.command==='16'){const requested=prompt('Brightness (0–100%)','100');if(requested===null)return;const n=Number(requested);if(!Number.isFinite(n)||n<0||n>100){toast('Enter a brightness from 0 to 100');return}value=Math.round(n*255/100)}
    try{await post('/api/command',{deviceId:b.dataset.device,method:Number(b.dataset.command),value});toast('Command queued; see Activity for the result')}catch(error){toast(error.message)}
  });
  content.querySelectorAll('[data-toggle]').forEach(b=>b.onclick=async()=>{const item=state.schedules.find(x=>String(x.id)===b.dataset.toggle);try{await post('/api/items/schedules',{...item,active:on(item.active)?0:1});await refresh()}catch(e){toast(e.message)}});
  content.querySelectorAll('[data-history]').forEach(b=>b.onclick=()=>{const id=b.dataset.history;if(openHistories.has(id))openHistories.delete(id);else openHistories.add(id);renderContent()});
  content.querySelectorAll('[data-view-sensor]').forEach(b=>b.onclick=()=>{openHistories.add(b.dataset.viewSensor);switchTab('sensors')});
  content.querySelectorAll('[data-history-range]').forEach(s=>s.onchange=()=>{historyRanges.set(s.dataset.historyRange,Number(s.value));renderContent()});
  bindCharts(content);
  content.dataset.tab=tab;
  if(sameTab){
    for(const element of content.querySelectorAll('[data-scroll-key]')){
      const saved=listScroll.get(element.dataset.scrollKey);
      if(saved){element.scrollLeft=saved.left;element.scrollTop=saved.top}
    }
    content.scrollLeft=contentScroll.left;content.scrollTop=contentScroll.top;
    // Restore after replacement/layout, and avoid interrupting an ongoing scroll
    // when the browser has already kept the page at the correct position.
    if(window.scrollX!==pageScroll.left||window.scrollY!==pageScroll.top)
      window.scrollTo({left:pageScroll.left,top:pageScroll.top,behavior:'instant'});
  }
}
function itemName(item){return item.kind==='devices'?deviceName(item.id):sensorName(item.id)}
function openProfile(){
  if(!state)return;profilePrompted=true;
  $('#profile-name').value=state.profile?.name||profileName;
  $('#profile-names').innerHTML=(state.profiles||[]).map(p=>`<option value="${h(p.name)}"></option>`).join('');
  $('#profile-error').textContent='';$('#profile-editor').showModal();$('#profile-name').select();
}
$('#profile').onclick=openProfile;
$('#close-profile').onclick=$('#cancel-profile').onclick=()=>$('#profile-editor').close();
$('#profile-form').onsubmit=async event=>{
  event.preventDefault();$('#save-profile').disabled=true;
  try{
    const chosen=await post('/api/profile',{name:$('#profile-name').value});
    profileName=chosen.profile.name;
    try{localStorage.setItem(profileStorageKey,profileName)}catch{}
    state.profile=chosen.profile;state.dashboard=chosen.items;
    if(!state.profiles.some(p=>p.name===profileName))state.profiles.push(chosen.profile);
    $('#profile-editor').close();switchTab('dashboard');await refresh();
  }catch(error){$('#profile-error').textContent=error.message}
  finally{$('#save-profile').disabled=false}
};
function customizeDashboard(){
  if(!state.profile){openProfile();return}
  dashboardDraftProfile=state.profile.name;dashboardDraft=structuredClone(state.dashboard||[]);
  $('#dashboard-search').value='';$('#dashboard-error').textContent='';
  $('#dashboard-editor-note').textContent='Choose devices and sensors, then arrange them in your preferred order. Saved for '+dashboardDraftProfile+' on all devices.';
  renderDashboardEditor();$('#dashboard-editor').showModal();
}
function renderDashboardEditor(){
  const active=document.activeElement,optionsTop=$('#dashboard-options').scrollTop,orderTop=$('#dashboard-order').scrollTop,optionsLeft=$('#dashboard-options').scrollLeft,orderLeft=$('#dashboard-order').scrollLeft;
  const focus=active?.matches('[data-pick-id]')?{kind:active.dataset.pickKind,id:active.dataset.pickId}:null;
  const q=$('#dashboard-search').value.toLocaleLowerCase();
  const available=['devices','sensors'].flatMap(kind=>byName(state[kind]).map(record=>({kind,id:String(record.id)})));
  $('#dashboard-options').innerHTML=available.filter(item=>itemName(item).toLocaleLowerCase().includes(q)).map(item=>`<label class="dashboard-option"><input type="checkbox" data-pick-kind="${item.kind}" data-pick-id="${h(item.id)}" ${dashboardDraft.some(x=>x.kind===item.kind&&x.id===item.id)?'checked':''}><span>${h(itemName(item))}<small>${item.kind==='devices'?'Device':'Sensor'}</small></span></label>`).join('')||'<p class="muted">No matching items.</p>';
  $('#dashboard-order').innerHTML=dashboardDraft.map((item,index)=>`<div class="order-item"><span><strong>${h(itemName(item))}</strong><small>${item.kind==='devices'?'Device':'Sensor'}</small></span><div><button type="button" class="order-button" data-move="${index}" data-step="-1" aria-label="Move ${h(itemName(item))} up" ${index===0?'disabled':''}>↑</button><button type="button" class="order-button" data-move="${index}" data-step="1" aria-label="Move ${h(itemName(item))} down" ${index===dashboardDraft.length-1?'disabled':''}>↓</button><button type="button" class="order-button" data-remove="${index}" aria-label="Remove ${h(itemName(item))}">×</button></div></div>`).join('')||'<p class="muted">Select items to start your dashboard.</p>';
  $('#dashboard-options').scrollTop=optionsTop;$('#dashboard-order').scrollTop=orderTop;
  $('#dashboard-options').scrollLeft=optionsLeft;$('#dashboard-order').scrollLeft=orderLeft;
  if(focus)$('#dashboard-options').querySelector('[data-pick-kind="'+focus.kind+'"][data-pick-id="'+CSS.escape(focus.id)+'"]')?.focus({preventScroll:true});
}
$('#dashboard-options').onchange=event=>{const input=event.target;if(!input.matches('[data-pick-id]'))return;const item={kind:input.dataset.pickKind,id:input.dataset.pickId};if(input.checked)dashboardDraft.push(item);else dashboardDraft=dashboardDraft.filter(x=>x.kind!==item.kind||x.id!==item.id);renderDashboardEditor()};
$('#dashboard-order').onclick=event=>{const b=event.target.closest('button');if(!b)return;if(b.dataset.remove!==undefined)dashboardDraft.splice(Number(b.dataset.remove),1);else if(b.dataset.move!==undefined){const from=Number(b.dataset.move),to=from+Number(b.dataset.step);if(to>=0&&to<dashboardDraft.length)[dashboardDraft[from],dashboardDraft[to]]=[dashboardDraft[to],dashboardDraft[from]]}renderDashboardEditor()};
$('#dashboard-search').oninput=renderDashboardEditor;
$('#customize').onclick=customizeDashboard;
$('#close-dashboard').onclick=$('#cancel-dashboard').onclick=()=>$('#dashboard-editor').close();
$('#dashboard-form').onsubmit=async event=>{event.preventDefault();$('#save-dashboard').disabled=true;try{const saved=await post('/api/dashboard',{items:dashboardDraft,profile:dashboardDraftProfile});if(state.profile?.name===dashboardDraftProfile)state.dashboard=saved.items;$('#dashboard-editor').close();toast('Dashboard saved');renderContent()}catch(error){$('#dashboard-error').textContent=error.message}finally{$('#save-dashboard').disabled=false}};
function daysText(value){const days=String(value||'').split(',');return days.length===7?'Every day':days.map(x=>['','Mon','Tue','Wed','Thu','Fri','Sat','Sun'][Number(x)]).join(', ')}
function triggerText(t){if(!t)return 'No trigger';if(t.type==='time')return `${String(t.hour).padStart(2,'0')}:${String(t.minute).padStart(2,'0')}`;if(t.type==='sensor')return `${sensorName(t.sensorId)} ${t.operator||'above'} ${t.value}`;if(t.type==='device')return deviceName(t.deviceId)+' '+action(t.method);if(t.type==='blockheater')return 'Block heater · needs local rule';return t.type}
function input(label,name,value='',type='text',extra=''){return `<label>${h(label)}<input name="${h(name)}" type="${type}" value="${h(value)}" ${extra}></label>`}
function select(label,name,options,value){return `<label>${h(label)}<select name="${h(name)}">${options.map(([v,t])=>`<option value="${h(v)}" ${String(v)===String(value)?'selected':''}>${h(t)}</option>`).join('')}</select></label>`}
function deviceSelect(name,value){return select('Device or group',name,byName(state.devices).map(d=>[d.id,d.name]),value)}
function check(label,name,value){return `<label><span><input type="checkbox" name="${h(name)}" ${on(value)?'checked':''}>${h(label)}</span></label>`}
function weekdays(value){return '<p class="field-section">Days</p><div class="days">'+['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map((name,i)=>`<label><input type="checkbox" name="day" value="${i+1}" ${String(value||'1,2,3,4,5,6,7').split(',').includes(String(i+1))?'checked':''}>${name}</label>`).join('')+'</div>'}
function edit(record){editing=record?structuredClone(record):{};$('#editor-title').textContent=(record?'Edit ':'Add ')+({devices:record?.protocol==='group'?'group':'device',schedules:'schedule',events:'event'}[tab]||'record');$('#form-error').textContent='';$('#delete').hidden=!record;let form='';if(tab==='devices'){let params=Object.fromEntries((editing.parameter||[]).map(p=>[p.name,p.value]));form=input('Name','name',editing.name)+select('Protocol','protocol',[['arctech','Arctech / Nexa'],['comen','Comen / Proove'],['group','Group']],editing.protocol||'arctech')+input('Model','model',editing.model||'selflearning-switch:nexa')+'<div class="row">'+input('House code','house',params.house||'')+input('Unit code','unit',params.unit||'')+'</div>'+check('Supports dimming','dimmable',Number(editing.methods)&16?1:0)+'<p class="field-section">Group members</p><label>Select members<select name="members" multiple size="6">'+byName(state.devices).filter(d=>d.id!==editing.id).map(d=>`<option value="${h(d.id)}" ${String(editing.devices||'').split(',').includes(String(d.id))?'selected':''}>${h(d.name)}</option>`).join('')+'</select></label><p class="field-note">RF codes are retained locally. Physical control requires transmit-capable firmware.</p>'}
if(tab==='schedules'){form=check('Schedule enabled','active',editing.active??1)+deviceSelect('deviceId',editing.deviceId)+select('Action','method',[[1,'On'],[2,'Off'],[16,'Dim']],editing.method||1)+input('Dim level (0–255)','methodValue',editing.methodValue||0,'number','min="0" max="255"')+select('Time reference','type',[['time','Time of day'],['sunrise','Sunrise'],['sunset','Sunset']],editing.type||'time')+'<div class="row">'+input('Hour','hour',editing.hour||0,'number','min="0" max="23"')+input('Minute','minute',editing.minute||0,'number','min="0" max="59"')+'</div><div class="row">'+input('Offset (minutes)','offset',editing.offset||0,'number','min="-1440" max="1440"')+input('Random delay (minutes)','randomInterval',editing.randomInterval||0,'number','min="0" max="1440"')+'</div>'+weekdays(editing.weekdays)+'<p class="field-section">Delivery settings</p><div class="row">'+input('RF repeats','reps',editing.reps||1,'number','min="1" max="10"')+input('Offline retries','retries',editing.retries??3,'number','min="0" max="10"')+'</div>'+input('Retry interval (minutes)','retryInterval',editing.retryInterval||5,'number','min="1" max="1440"')+'<p class="field-note">Times use '+h(state.status.timezone)+'. Randomization adds a stable delay between zero and the selected interval.</p>'}
if(tab==='events'){const t=editing.trigger?.[0]||{},a=editing.action?.[0]||{},conditions=editing.condition||[];const days=conditions.find(c=>c.type==='weekdays'),window=conditions.find(c=>c.type==='time');form=input('Event name','description',editing.description||editing.name||'')+check('Event enabled','active',editing.active||0)+select('Trigger','triggerType',[['time','At a time'],['sunrise','At sunrise'],['sunset','At sunset'],['sensor','Sensor threshold'],['device','Device state'],...(t.type==='blockheater'?[['blockheater','Imported block heater — not configured']]:[])],t.type||'time')+'<div class="row">'+input('Hour','hour',t.hour||0,'number','min="0" max="23"')+input('Minute','minute',t.minute||0,'number','min="0" max="59"')+'</div>'+select('Sensor','sensorId',state.sensors.map(s=>[s.id,sensorName(s.id)]),t.sensorId)+select('Reading','field',[['temp','Temperature °C'],['humidity','Humidity %']],t.field||'temp')+'<div class="row">'+select('Comparison','operator',[['above','Above'],['below','Below'],['equals','Equals']],t.operator||'above')+input('Threshold','threshold',t.value||0,'number','step="0.1"')+'</div>'+deviceSelect('triggerDevice',t.deviceId)+select('Trigger device state','triggerMethod',[[1,'On'],[2,'Off']],t.method||1)+'<p class="field-section">Action</p>'+deviceSelect('actionDevice',a.deviceId)+select('Action','method',[[1,'On'],[2,'Off'],[16,'Dim']],a.method||1)+'<div class="row">'+input('Dim level (0–255)','methodValue',a.methodValue||0,'number','min="0" max="255"')+input('Delay (seconds)','delay',a.delay||0,'number','min="0" max="86400"')+'</div>'+input('RF repeats','repeats',a.repeats||1,'number','min="1" max="10"')+weekdays(days?.weekdays)+check('Restrict to time window','windowEnabled',window?1:0)+'<div class="row">'+input('From','from',window?String(window.fromHour).padStart(2,'0')+':'+String(window.fromMinute).padStart(2,'0'):'00:00','time')+input('Until','until',window?String(window.toHour).padStart(2,'0')+':'+String(window.toMinute).padStart(2,'0'):'23:59','time')+'</div>'+input('Minimum repeat interval (seconds)','minRepeatInterval',editing.minRepeatInterval??30,'number','min="0" max="86400"')+'<p class="field-note">Sensor triggers fire on threshold crossings using fresh local readings. Imported block-heater configuration is preserved while disabled; select a local trigger to replace it.</p>'}
$('#form-fields').innerHTML=form;$('#editor').showModal()}
$('#edit-form').onsubmit=async event=>{event.preventDefault();const fd=new FormData(event.target),get=n=>fd.get(n),yes=n=>fd.has(n),number=n=>Number(get(n));let value={...editing};try{if(tab==='devices'){const parameters=(editing.parameter||[]).filter(p=>!['house','unit'].includes(p.name));for(const name of ['house','unit'])if(get(name))parameters.push({name,value:get(name)});value={...value,name:get('name'),protocol:get('protocol'),model:get('model'),methods:yes('dimmable')?'19':'3',parameter:parameters,devices:fd.getAll('members').join(',')}}if(tab==='schedules'){for(const n of ['deviceId','type'])value[n]=get(n);for(const n of ['method','methodValue','hour','minute','offset','randomInterval','retries','retryInterval','reps'])value[n]=number(n);value.active=yes('active')?1:0;value.weekdays=fd.getAll('day').join(',');if(!value.weekdays)throw new Error('Select at least one day')}if(tab==='events'){const type=get('triggerType');let trigger={type,hour:get('hour'),minute:get('minute'),offset:0};if(type==='sensor')trigger={type,sensorId:get('sensorId'),field:get('field'),operator:get('operator'),value:number('threshold')};if(type==='device')trigger={type,deviceId:get('triggerDevice'),method:number('triggerMethod')};if(type==='blockheater')trigger=editing.trigger[0];const days=fd.getAll('day').join(',');if(!days)throw new Error('Select at least one day');let condition=[{type:'weekdays',weekdays:days,group:'local'}];if(yes('windowEnabled')){const [fh,fm]=get('from').split(':'),[th,tm]=get('until').split(':');condition.push({type:'time',fromHour:fh,fromMinute:fm,toHour:th,toMinute:tm,group:'local'})}value={...value,description:get('description'),active:yes('active')?1:0,minRepeatInterval:number('minRepeatInterval'),trigger:[trigger,...(editing.trigger||[]).slice(1)],condition,action:[{type:'device',deviceId:get('actionDevice'),method:number('method'),methodValue:number('methodValue'),delay:number('delay'),delayPolicy:'continue',repeats:number('repeats')},...(editing.action||[]).slice(1)]}}await post('/api/items/'+tab,value);$('#editor').close();toast('Saved locally');await refresh()}catch(error){$('#form-error').textContent=error.message}};
$('#delete').onclick=async()=>{if(!confirm('Delete this '+tab.slice(0,-1)+'?'))return;try{await post('/api/delete/'+tab+'/'+encodeURIComponent(editing.id),{});$('#editor').close();toast('Deleted locally');await refresh()}catch(e){$('#form-error').textContent=e.message}};
$('#pause').onclick=async()=>{try{await post('/api/settings',{scheduler_enabled:!state.status.scheduler_enabled});await refresh()}catch(e){toast(e.message)}};
$('#add').onclick=()=>edit(null);$('#close-editor').onclick=$('#cancel').onclick=()=>$('#editor').close();$('#search').oninput=()=>state&&renderContent();document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{switchTab(b.dataset.tab)});refresh();setInterval(refresh,5000);
