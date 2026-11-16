import {merge} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {esc,fmt,date,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
import {parseCSV} from '../utils/csv.js';
import {Channel,ChannelShort,MergeStatus,ArbitrationStatus,SourceStatus} from '../constants/enums.js';
const FIELDS=['units','run_hours','temp_c','idle_hours','kwh'];
const CHANNELS=['meter','schedule','env'];
const canWrite=()=>session.user.role!=='viewer';
const chip=st=>'<span class="chip st-'+esc(st)+'">'+esc(MergeStatus[st]||st)+'</span>';
function fieldLabel(key){const c=(workspace.meta.columns||[]).find(x=>x.key===key);return c?c.label:key;}
function srcBadges(s){
 const has=new Set();for(const f of FIELDS)(s.provenance?.[f]?.candidates||[]).forEach(c=>has.add(c.channel));
 return CHANNELS.map(c=>'<span class="src-badge'+(has.has(c)?'':' off')+'" title="'+esc(Channel[c])+(has.has(c)?'已上报':'未上报')+'">'+esc(ChannelShort[c])+'</span>').join('');
}
function cell(s,f){
 const p=s.provenance?.[f],v=s.values?.[f];
 if(!p||!p.candidates?.length)return '<td class="mv-missing" title="待补：尚无生效来源上报该字段">缺</td>';
 if(v===null||v===undefined)return '<td class="mv-conflict" title="同字段异值，待人工裁决">冲突</td>';
 if(p.resolved_by==='arbitration')return '<td class="mv-arb" title="裁决取值">'+esc(fmt(v))+'<small class="mark">裁</small></td>';
 return '<td>'+esc(fmt(v))+'</td>';
}
function groupCands(cands){
 const map=new Map();
 for(const c of cands||[]){const k=String(c.value);if(!map.has(k))map.set(k,{value:c.value,sources:[]});map.get(k).sources.push(c);}
 return [...map.values()];
}
const srcOf=c=>esc(Channel[c.channel]||c.channel)+' · '+esc(c.stream)+' · v'+esc(c.version)+' · 批次#'+esc(c.batch_id);
function arbLine(a){
 if(!a)return '';
 return '<div class="arb-meta '+(a.status==='stale'?'stale':'')+'">裁决 '+esc(ArbitrationStatus[a.status]||a.status)+' · 取值 '+esc(fmt(a.chosen_value))+' · '+esc(a.decided_by)+' · 确认于 '+esc(date(a.confirmed_at))+'<br>理由：'+esc(a.reason)+'</div>';
}
function fieldBlock(s,f,arb){
 const p=s.provenance?.[f]||{candidates:[]},groups=groupCands(p.candidates),v=s.values?.[f];
 const writable=canWrite();
 let head='<div class="field-head"><strong>'+esc(fieldLabel(f))+'</strong><span>'+(!groups.length?'待补：尚无生效来源上报':v===null||v===undefined?'异值待裁决':p.resolved_by==='arbitration'?'裁决取值':'自动取唯一值')+'</span></div>';
 let body='';
 if(!groups.length)body+='<p class="hint">等待 '+esc(CHANNELS.filter(c=>(workspace.meta.channels.find(x=>x.key===c)?.fields||[]).includes(f)).map(c=>Channel[c]).join('、')||'来源')+' 班组补报后自动汇合。</p>';
 for(const g of groups){
  const picked=v!==null&&v!==undefined&&String(g.value)===String(v);
  body+='<div class="cand'+(picked?' picked':'')+'"><strong>'+esc(fmt(g.value))+'</strong><span>'+g.sources.map(srcOf).join('<br>')+'</span></div>';
 }
 if(arb)body+=arbLine(arb);
 const conflict=groups.length>1&&(v===null||v===undefined);
 if(conflict&&writable){
  body+='<form class="arb-form" data-line="'+esc(s.line)+'" data-day="'+esc(s.day)+'" data-field="'+esc(f)+'"><div class="cand-options">'+groups.map((g,i)=>'<label class="cand-option"><input type="radio" name="chosen" value="'+esc(g.value)+'"'+(i===0?' checked':'')+'> '+esc(fmt(g.value))+'<small>'+g.sources.map(srcOf).join('；')+'</small></label>').join('')+'</div><input name="reason" required minlength="2" maxlength="300" placeholder="裁决理由（随发布留档）"><button type="submit" class="primary small">提交裁决</button></form>';
 }
 if(arb&&arb.status==='stale'&&writable){
  const stillThere=groups.some(g=>String(g.value)===String(arb.chosen_value));
  body+='<p class="warning">上游来源已更新，原裁决绑定的版本失效，需重新确认后才可发布。</p>'+(stillThere&&conflict?'<button class="button small" data-confirm="'+arb.id+'">沿用原值 '+esc(fmt(arb.chosen_value))+' 重新确认</button>':'');
 }
 return '<div class="field-block" id="fb-'+esc(f)+'">'+head+body+'</div>';
}
function renderDetail(){
 const box=document.querySelector('#merge-detail');
 if(!box)return;
 const data=workspace.mergeData,s=data?.samples.find(x=>x.day===workspace.mergeDay);
 if(!s){box.innerHTML='<p class="empty">点击样本行，查看每个字段的来源批次、候选值与裁决依据。</p>';return;}
 const arbOf=f=>data.arbitrations.find(a=>a.day===s.day&&a.field===f);
 box.innerHTML='<div class="section-title"><h2>'+esc(s.day)+' · '+esc(s.line)+'</h2>'+chip(s.status)+(s.published_dataset_id?'<span>已发布至批次 #'+esc(s.published_dataset_id)+'</span>':'<span>更新于 '+esc(date(s.updated_at))+'</span>')+'</div>'+FIELDS.map(f=>fieldBlock(s,f,arbOf(f))).join('');
 box.querySelectorAll('.arb-form').forEach(form=>submit(form,async f=>{
  await merge.arbitrate({line:form.dataset.line,day:form.dataset.day,field:form.dataset.field,chosen_value:Number(f.get('chosen')),reason:f.get('reason')});
  notify('裁决已记录，样本已重算');workspace.mergeDay=form.dataset.day;await workspace.refreshMerge();
 }));
 box.querySelectorAll('[data-confirm]').forEach(b=>b.onclick=async()=>{try{await merge.confirm(b.dataset.confirm);notify('已按原值重新确认，裁决恢复生效');await workspace.refreshMerge();}catch(e){notify(e.message,true);}});
}
export async function mergePage(){
 const [ov,sources]=await Promise.all([merge.overview(),merge.sources()]);
 const m=workspace.meta,lines=ov.lines.map(l=>l.line);
 if(!workspace.mergeLine||!lines.includes(workspace.mergeLine))workspace.mergeLine=lines[0]||null;
 const line=workspace.mergeLine;
 const data=line?await merge.samples(line):{summary:null,samples:[],arbitrations:[]};
 const publishes=line?await merge.publishes(line):[];
 workspace.mergeData=data;
 const sum=data.summary;
 const ready=sum&&sum.pending_fill===0&&sum.pending_arbitration===0&&sum.total>=5;
 const ro=canWrite()?'':'disabled';
 const batchItem=b=>'<div class="batch-item static"><strong>'+esc(b.name)+'</strong><span>'+esc(Channel[b.channel]||b.channel)+' · '+esc(b.stream)+' · v'+b.version+' · '+b.rows+' 条 · '+esc(SourceStatus[b.status]||b.status)+'</span><small>'+esc(b.created_by)+' · '+esc(date(b.created_at))+' · SHA256 '+esc(b.checksum.slice(0,14))+'…</small></div>';
 const sourcePanel='<section class="panel"><div class="section-title"><h2>来源批次</h2><span>生效 '+ov.active_sources+' 路'+(ov.pending_tasks?' · 汇合中 '+ov.pending_tasks:'')+'</span></div><div class="batch-list source-list">'+(sources.slice(0,12).map(batchItem).join('')||'<p class="empty">尚无来源批次。</p>')+'</div><div class="section-title"><h2>上报来源批次</h2></div><form id="source-form"><label>资料渠道<select name="channel">'+m.channels.map(c=>'<option value="'+esc(c.key)+'">'+esc(c.label)+'</option>').join('')+'</select></label><label>上报班组<input name="stream" required minlength="2" maxlength="80" placeholder="如：抄表一组"></label><label>批次说明<input name="name" maxlength="160" placeholder="如：11月第3周读数（可留空）"></label><label>上传 CSV 或 JSON<input type="file" id="merge-file" accept=".json,.csv"></label><label>记录 JSON<textarea name="records" rows="5" placeholder="粘贴 JSON 数组，或先选择上方文件" required></textarea></label><p class="hint" id="channel-hint"></p><p class="hint">同一班组再次上报即修订：新版生效、旧版废止，相关样本自动重汇合；受影响裁决将失效待确认。</p><button type="submit" class="primary" '+ro+'>校验并上报</button></form></section>';
 const tabs=lines.map(l=>'<button class="small'+(l===line?' active':'')+'" data-line-tab="'+esc(l)+'">'+esc(l)+'</button>').join('');
 const chips=sum?['pending_fill','pending_arbitration','publishable','published'].map(k=>'<span class="chip st-'+k+'">'+MergeStatus[k]+' '+sum[k]+'</span>').join(''):'';
 const rows=data.samples.map(s=>'<tr data-day="'+esc(s.day)+'" class="'+(workspace.mergeDay===s.day?'selected':'')+'"><td>'+esc(s.day)+'</td>'+FIELDS.map(f=>cell(s,f)).join('')+'<td class="src-cell">'+srcBadges(s)+'</td><td>'+chip(s.status)+'</td></tr>').join('');
 const samplePanel='<section class="panel"><div class="section-title"><h2>汇合样本</h2><span>'+(sum?sum.total+' 条':'')+'</span></div>'+(lines.length?'<div class="line-tabs">'+tabs+'</div><div class="chip-row">'+chips+'</div>':'')+(data.samples.length?'<div class="table-wrap merge-table"><table><thead><tr><th>日期</th>'+FIELDS.map(f=>'<th>'+esc(fieldLabel(f))+'</th>').join('')+'<th>来源</th><th>状态</th></tr></thead><tbody>'+rows+'</tbody></table></div>':'<p class="empty">'+(lines.length?'该线体暂无样本。':'尚无汇合样本。请先在左侧上报三路来源批次，系统按线体与日期自动汇合。')+'</p>')+'<div id="merge-detail" class="merge-detail"></div></section>';
 const history=publishes.map(p=>'<div class="delivery"><div><strong>'+esc(p.dataset||('批次 #'+p.dataset_id))+'</strong><p>'+esc(p.created_by)+' · '+esc(date(p.created_at))+' · 裁决依据 '+p.basis.length+' 条</p><small>整组指纹 '+esc(p.group_checksum.slice(0,24))+'…</small>'+(p.basis.length?'<details class="basis"><summary>裁决依据明细</summary>'+p.basis.map(b=>'<div class="basis-item"><strong>'+esc(b.day)+' · '+esc(fieldLabel(b.field))+'</strong> 取 '+esc(fmt(b.chosen_value))+'<br><span>'+esc(b.reason)+'（'+esc(b.decided_by)+'）</span><small>绑定来源：'+b.candidates.map(srcOf).join('；')+'</small></div>').join('')+'</details>':'')+'</div></div>').join('');
 const publishPanel='<section class="panel publish-panel"><div class="section-title"><h2>整组发布</h2><span>样本与裁决依据同一事务生效</span></div>'+(line?'<p class="hint">线体 '+esc(line)+'：'+(sum?('待补齐 '+sum.pending_fill+' · 待裁决 '+sum.pending_arbitration+' · 可发布 '+sum.publishable+' · 已发布 '+sum.published):'无样本')+'。发布后归因试验才能读取该批次；内容未变化时再次发布沿用已有样本批次。</p><button class="primary" id="publish-line" '+(ready&&canWrite()?'':'disabled')+'>发布 '+esc(line)+' 整组样本（'+(sum?sum.total:0)+' 条）</button>'+(ready?'':'<p class="warning">存在待补齐或待裁决样本（或样本不足 5 条），整组就绪前不能发布，归因试验不会读到半成品。</p>'):'<p class="empty">暂无可发布线体。</p>')+'<div class="section-title"><h2>发布历史</h2><span>'+publishes.length+' 次</span></div>'+(history||'<p class="empty">尚无发布记录。</p>')+'</section>';
 return heading('03 / SOURCE MERGE','三路资料汇合与发布','抄表、排产、环境记录按线体与日期自动汇合：缺项待补、异值人工裁决、整组原子发布。归因试验只读取发布后的完整样本批次。','<button class="button" id="refresh-merge">刷新 ↻</button>')+'<div class="merge-grid">'+sourcePanel+samplePanel+'</div>'+publishPanel;
}
export function bindMerge(refresh){
 workspace.refreshMerge=refresh;
 document.querySelector('#refresh-merge').onclick=refresh;
 const hint=document.querySelector('#channel-hint'),chSelect=document.querySelector('[name=channel]');
 const showHint=()=>{const c=workspace.meta.channels.find(x=>x.key===chSelect.value);hint.textContent='该渠道每行字段：day、line、'+c.fields.join('、')+'（其余字段由其他渠道上报）。';};
 chSelect.addEventListener('change',showHint);showHint();
 document.querySelector('#merge-file').addEventListener('change',async e=>{try{const file=e.target.files[0];if(!file)return;const text=await file.text(),records=file.name.endsWith('.csv')?parseCSV(text):JSON.parse(text);document.querySelector('#source-form [name=records]').value=JSON.stringify(records,null,2);}catch(error){notify(error.message,true);}});
 submit(document.querySelector('#source-form'),async f=>{await merge.upload({channel:f.get('channel'),stream:f.get('stream'),name:f.get('name'),records:JSON.parse(f.get('records'))});notify('来源批次已登记，样本已重新汇合');await refresh();});
 document.querySelectorAll('[data-line-tab]').forEach(b=>b.onclick=()=>{workspace.mergeLine=b.dataset.lineTab;workspace.mergeDay=null;refresh();});
 document.querySelectorAll('.merge-table tbody tr').forEach(tr=>tr.onclick=()=>{workspace.mergeDay=tr.dataset.day;document.querySelectorAll('.merge-table tr.selected').forEach(x=>x.classList.remove('selected'));tr.classList.add('selected');renderDetail();});
 document.querySelector('#publish-line')?.addEventListener('click',async()=>{try{const r=await merge.publish(workspace.mergeLine);notify(r.reused?'内容未变化，沿用已有样本批次 #'+r.dataset.id:'已发布样本批次 #'+r.dataset.id+'（'+(r.dataset.rows)+' 条），可前往工作台分析');await refresh();}catch(e){notify(e.message,true);}});
 renderDetail();
}
