"use strict";

const $ = (id) => document.getElementById(id);
const labels = {running:"运行中",completed:"已完成",needs_input:"等待补充",no_evidence:"资料不足",failed:"未完成",out_of_scope:"不适用",cancelled:"已取消",pending:"待执行",succeeded:"成功"};
const toolNames = {search_knowledge:"检索知识资料",convert_units:"核对并换算单位",calc_heat_duty:"计算显热负荷",calc_mass_balance:"计算混合衡算"};
const state = {job:null, runs:[], activeId:null, view:"summary", selectedEntity:null, poll:null, rendering:"", busy:false, configured:false, indexStatus:null, submitting:false, selectionVersion:0, sessionVersion:0, cancellingId:null, loadingId:null};
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const jsonText = (value) => esc(JSON.stringify(value, null, 2));
const badge = (status) => `<span class="badge ${Object.hasOwn(labels,status) ? status : "neutral"}">${esc(labels[status] || status)}</span>`;
const numeric = (value) => Number.isFinite(value) ? new Intl.NumberFormat("zh-CN",{maximumSignificantDigits:6}).format(value) : "—";
const isRunning = () => Boolean(state.job && !state.job.finished);

// Only a small, escaped Markdown subset is rendered. Raw HTML, images and links stay text.
function inline(text) {
  return esc(text).replace(/`([^`\n]+)`/g,"<code>$1</code>").replace(/\*\*([^*\n]+)\*\*/g,"<strong>$1</strong>");
}
function markdown(text) {
  const lines = String(text || "").split("\n");
  let output = "", paragraph = [], list = "", code = null, codeLines = [];
  const flush = () => {if(paragraph.length){output += `<p>${inline(paragraph.join("\n"))}</p>`;paragraph=[];}if(list){output += `</${list}>`;list="";}};
  for(const line of lines){
    if(/^\s*```/.test(line)){
      if(code){output += `<pre>${esc(codeLines.join("\n"))}</pre>`;code=null;codeLines=[];}
      else{flush();code=true;}
      continue;
    }
    if(code){codeLines.push(line);continue;}
    if(!line.trim()){flush();continue;}
    const heading=line.match(/^#{1,6}\s+(.+)/);
    const item=line.match(/^\s*(?:([-*])|\d+[.)、])\s+(.+)/);
    if(heading){flush();output+=`<h3>${inline(heading[1])}</h3>`;}
    else if(item){const kind=item[1]?"ul":"ol";if(list!==kind){flush();list=kind;output+=`<${kind}>`;}output+=`<li>${inline(item[2])}</li>`;}
    else if(/^>\s?/.test(line)){flush();output+=`<blockquote>${inline(line.replace(/^>\s?/,""))}</blockquote>`;}
    else {if(list)flush();paragraph.push(line);}
  }
  flush();if(codeLines.length)output+=`<pre>${esc(codeLines.join("\n"))}</pre>`;
  return output;
}

async function api(path, options={}) {
  const response = await fetch(path, {credentials:"same-origin",...options,headers:{"Content-Type":"application/json",...options.headers}});
  let data;
  try {data=await response.json();} catch {throw new Error("服务暂时没有响应，请确认本地服务仍在运行。");}
  if(!response.ok){const error=new Error(typeof data.detail==="string" ? data.detail : "请求未完成，请检查输入后重试。");error.status=response.status;throw error;}
  return data;
}
function notice(message, persistent=false) {
  notice.connection=false;
  $("notice").textContent=message;$("notice").hidden=false;
  clearTimeout(notice.timer);
  if(!persistent)notice.timer=setTimeout(()=>{$("notice").hidden=true;},6000);
}
function setBusy(busy) {
  busy=Boolean(busy || state.submitting);
  state.busy=busy;
  $("submit").disabled=busy || Boolean(state.loadingId) || !state.configured;
  $("new-task").disabled=busy;
  document.querySelectorAll(".example-button").forEach(b=>{b.disabled=busy;});
  $("cancel").hidden=!isRunning();
  $("cancel").disabled=Boolean(state.job?.cancel_requested || state.cancellingId===state.activeId);
  $("cancel").textContent=state.job?.cancel_requested?"停止中":"停止";
  $("submit").innerHTML=busy?"运行中…":(state.job ? "继续 <span aria-hidden='true'>↗</span>" : "运行 <span aria-hidden='true'>↗</span>");
  $("input-mode").textContent=state.job?"继续任务":"新任务";
  $("question").placeholder=state.job?"补充缺少的参数，或修改当前任务的条件…":"例如：1000 kg/h 液体从 25℃ 加热到 65℃，比热为 4.18 kJ/(kg·K)，求热负荷。";
}
function renderHistory() {
  $("history-count").textContent=state.runs.length;
  $("history-list").replaceChildren();
  if(!state.runs.length){$("history-list").innerHTML='<p class="muted">暂无记录</p>';return;}
  for(const run of state.runs){
    const button=document.createElement("button");button.className=`history-item${state.activeId===run.job_id?" active":""}`;
    button.setAttribute("aria-pressed",String(state.activeId===run.job_id));
    const time=run.created_at?new Date(run.created_at).toLocaleTimeString("zh-CN",{hour:"2-digit",minute:"2-digit"}):"";
    button.innerHTML=`<span class="history-title">${esc(run.question)}</span><span class="history-meta"><span>${esc(labels[run.status]||run.status)}</span><span>${esc(time)}</span></span>`;
    button.title=run.question;button.addEventListener("click",()=>loadJob(run.job_id));$("history-list").append(button);
  }
}
async function refreshSession() {
  const version=++state.sessionVersion;
  const session=await api("/api/session");
  if(version===state.sessionVersion){state.runs=session.runs || [];renderHistory();}
  return session;
}
function welcome() {
  return `<div class="welcome"><div class="signal" aria-hidden="true"><span></span><span></span><span></span></div><p class="ready-label">TRACEABLE WORKFLOW</p><h3>从问题走到依据</h3><p class="welcome-copy">输入实际工况或概念问题。任务运行后，可沿路径查看本轮检索返回的知识关系、来源片段，以及每次工具调用如何使用前一步的结果。</p><div class="workflow-preview" aria-label="任务流程"><span>问题</span><i aria-hidden="true">→</i><span>检索与计算</span><i aria-hidden="true">→</i><span>结果与依据</span></div></div>`;
}

function metrics(result) {
  const successful=(result.calls||[]).filter(c=>c.status==="succeeded");
  const calculations=successful.filter(c=>c.tool_name==="calc_heat_duty"||c.tool_name==="calc_mass_balance");
  const targets=calculations.length?calculations:successful.filter(c=>c.tool_name==="convert_units");
  const cards=[];
  for(const call of targets){
    const out=call.output || {};
    const add=(label,value,unit)=>{if(Number.isFinite(value))cards.push(`<div class="metric"><div class="metric-label">${esc(label)}</div><div class="metric-value">${numeric(value)}<span>${esc(unit)}</span></div><div class="metric-source">工具 · ${esc(call.step_id)}</div></div>`);};
    if(call.tool_name==="calc_heat_duty")add("显热负荷",out.heat_duty_kw,"kW");
    if(call.tool_name==="calc_mass_balance"){
      add("总出口流量",out.total_flow_kg_h,"kg/h");add("组分质量分数",out.mass_fraction*100,"%");add("组分流量",out.component_flow_kg_h,"kg/h");
    }
    if(call.tool_name==="convert_units")add("单位换算结果",out.value,out.unit);
  }
  return cards.length?`<div class="metrics">${cards.join("")}</div>`:"";
}
const list = (value) => Array.isArray(value) ? value.filter(Boolean) : value ? [value] : [];
const safeUrl = (value) => typeof value==="string" && /^https?:\/\/[^\s<>"']+$/i.test(value) ? value : "";
const sourceText = (item) => item?.source || item?.url || item?.file_path || item?.doc_id || "来源未标注";
function sourceLabel(item) {
  const label=sourceText(item), url=safeUrl(item?.url || (safeUrl(label)?label:""));
  return url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`:esc(label);
}
function retrievalFor(call) {
  const output=call.output || {};
  const data=output.retrieval && typeof output.retrieval==="object" ? output.retrieval : {};
  const hits=list(output.hits);
  const chunks=hits;
  return {data,hits,chunks,entities:list(data.entities),relationships:list(data.relationships),references:list(data.references),graphSources:list(data.graph_sources)};
}
function sourceIds(record) {
  return [...new Set([...list(record?.source_ids),...list(record?.source_id)].flatMap(value=>String(value).split(/<SEP>/i)).map(value=>value.trim()).filter(Boolean))];
}
function descriptionParts(value) {
  const seen=new Set();
  return list(value).flatMap(part=>String(part).split(/<SEP>/i)).map(part=>part.trim()).filter(part=>{
    const key=part.replace(/\s+/g," ").toLocaleLowerCase();
    if(!key||seen.has(key))return false;
    seen.add(key);return true;
  });
}
function entityDescription(value) {
  const parts=descriptionParts(value);
  if(!parts.length)return "<p>本轮未返回实体说明。</p>";
  if(parts.length===1)return `<p>${esc(parts[0])}</p>`;
  return `<ul class="entity-description-list">${parts.map(part=>`<li>${esc(part)}</li>`).join("")}</ul>`;
}
function relationDescription(value) {
  const parts=descriptionParts(value);
  return parts.length?`<div class="graph-relation-description">${parts.map(part=>`<p>${esc(part)}</p>`).join("")}</div>`:"";
}
function chunkPreview(value) {
  return String(value||"").split(/\r?\n/).map(line=>line.trim()).filter(line=>line&&!/^#(?:\s|$)/.test(line)&&!/^(?:资料来源|原始来源|来源|source)\s*[:：]/i.test(line)).map(line=>line.replace(/^#{2,6}\s*/,"")).join(" ").replace(/\s+/g," ").trim();
}
function relatedChunks(entity, chunks) {
  const ids=new Set(sourceIds(entity));
  const names=new Set([entity.id,entity.name,entity.entity_name].filter(Boolean).map(String));
  return chunks.filter(chunk=>ids.has(String(chunk.chunk_id||chunk.reference_id||chunk.id||"")) || list(chunk.entity_ids).some(id=>names.has(String(id))));
}
function graphSourceCard(id, source, hitIds) {
  if(!source)return `<div class="graph-source-card unresolved"><strong>未解析来源</strong><code>${esc(id)}</code><p>索引未提供该编号的原文或出处，不能据此核验。</p></div>`;
  const title=source.title||source.chunk_id||id;
  const preview=chunkPreview(source.text);
  const alsoHit=hitIds.has(id);
  return `<details class="graph-source-card"><summary><span>${esc(title)}</span><em>${alsoHit?"图谱支撑 · 同时命中":"图谱支撑 · 非命中"}</em></summary><p class="graph-source-excerpt">${esc(preview.slice(0,200))}${preview.length>200?"…":""}</p><p class="graph-source-origin">来源：${sourceLabel(source)}</p><small>片段编号 ${esc(id)}</small>${source.text?`<div class="graph-source-original"><span>原文</span><article class="prose">${markdown(source.text)}</article></div>`:"<p>索引没有提供原文。</p>"}</details>`;
}
function graphSourceCards(ids, graphSources, hits) {
  if(!ids.length)return '<p class="graph-source-missing">图谱未返回来源编号，无法追溯该节点的原文。</p>';
  const byId=new Map(graphSources.map(source=>[String(source.chunk_id||""),source]));
  const hitIds=new Set(hits.map(hit=>String(hit.chunk_id||"")));
  return `<div class="graph-source-list">${ids.map(id=>graphSourceCard(id,byId.get(id),hitIds)).join("")}</div>`;
}
function entityMap(entities, relationships, queryIndex, selectedIndex) {
  const visible=entities.slice(0,9).map((entity,index)=>({
    id:String(entity.id||entity.name||entity.entity_name||index),
    name:String(entity.name||entity.entity_name||entity.id||`实体 ${index+1}`),
    type:String(entity.type||entity.entity_type||""),
  }));
  if(!visible.length)return '<div class="path-empty">本轮没有返回可展示的实体。</div>';
  const positions=visible.map((node,index)=>{
    const angle=-Math.PI/2+2*Math.PI*index/visible.length;
    return {...node,x:visible.length===1?320:320+Math.cos(angle)*220,y:visible.length===1?170:170+Math.sin(angle)*120};
  });
  const byId=new Map();
  for(const node of positions){byId.set(node.id.toLowerCase(),node);byId.set(node.name.toLowerCase(),node);}
  let drawn=0;
  const lines=relationships.map(rel=>{
    const from=byId.get(String(rel.source||rel.src_id||"").toLowerCase());
    const to=byId.get(String(rel.target||rel.tgt_id||"").toLowerCase());
    if(!from || !to || from===to)return "";
    drawn++;
    return `<line x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}" class="graph-edge"><title>${esc(rel.description||rel.keywords||`${from.name} → ${to.name}`)}</title></line>`;
  }).join("");
  const nodes=positions.map((node,index)=>`<g class="graph-node${index===selectedIndex?" selected":""}" role="button" tabindex="0" aria-label="查看实体 ${esc(node.name)}" data-query-index="${queryIndex}" data-entity-index="${index}"><circle cx="${node.x}" cy="${node.y}" r="40"></circle><text x="${node.x}" y="${node.y+4}" text-anchor="middle">${esc(node.name.slice(0,7))}${node.name.length>7?"…":""}</text><title>${esc(node.name)}${node.type?` · ${esc(node.type)}`:""}</title></g>`).join("");
  return `<div class="entity-graph"><svg viewBox="0 0 640 340" role="group" aria-label="${visible.length} 个检索实体、${drawn} 条实体关系">${lines}${nodes}</svg><p>选择实体查看说明和关联片段。图中只连接本轮返回且端点可匹配的关系。${entities.length>visible.length?`显示前 ${visible.length} / ${entities.length} 个实体。`:""}</p></div>`;
}
function retrievalCard(call, index, citations) {
  const {data,hits,chunks,entities,relationships,references,graphSources}=retrievalFor(call);
  const query=data.query||call.arguments?.query||call.requested_arguments?.query||"查询未记录";
  const mode=data.mode||"未标注";
  const high=list(data.keywords?.high_level), low=list(data.keywords?.low_level);
  const keywords=(high.length||low.length)?`<div class="keyword-groups">${high.length?`<div><small>主题词</small>${high.map(word=>`<span>${esc(word)}</span>`).join("")}</div>`:""}${low.length?`<div><small>细节词</small>${low.map(word=>`<span>${esc(word)}</span>`).join("")}</div>`:""}</div>`:"<p class=\"path-muted\">本轮没有返回关键词。</p>";
  const relationRows=relationships.length?`<details class="graph-relations"><summary>查看 ${relationships.length} 条返回的关系及其来源</summary><ul>${relationships.map(rel=>`<li><strong>${esc(rel.source||rel.src_id||"?")}</strong><span>→</span><strong>${esc(rel.target||rel.tgt_id||"?")}</strong>${relationDescription(rel.description)}<div class="graph-source-label">关系支撑片段 · ${sourceIds(rel).length}</div>${graphSourceCards(sourceIds(rel),graphSources,hits)}</li>`).join("")}</ul></details>`:"";
  const refsByChunk=new Map(references.map(ref=>[String(ref.chunk_id||ref.reference_id||""),ref]));
  const selectedIndex=state.selectedEntity?.queryIndex===index?Math.min(state.selectedEntity.entityIndex,entities.length-1):0;
  const selected=entities[selectedIndex];
  const linked=selected?relatedChunks(selected,hits):[];
  const activeIds=new Set(linked.map(chunk=>String(chunk.chunk_id||chunk.reference_id||chunk.id||"")));
  const details=selected?`<div class="entity-detail"><small>实体详情 · ${esc(selected.type||selected.entity_type||"未分类")}</small><strong>${esc(selected.name||selected.entity_name||selected.id||"未命名实体")}</strong>${entityDescription(selected.description)}<div class="entity-links">${linked.length?`关联本轮命中片段：${linked.map(chunk=>esc(chunk.title||chunk.document_title||chunk.chunk_id||"片段")).join("、")}`:"该实体没有明确关联到本轮命中片段；下方图谱支撑资料可能来自索引中的其他片段。"}</div><div class="graph-source-label">实体支撑片段 · ${sourceIds(selected).length}</div>${graphSourceCards(sourceIds(selected),graphSources,hits)}</div>`:"";
  const graphSourceIndex=graphSources.length?`<details class="graph-source-index"><summary>全部图谱支撑资料 · ${graphSources.length} 份（含非命中片段）</summary>${graphSourceCards([...new Set(graphSources.map(source=>String(source.chunk_id||"")).filter(Boolean))],graphSources,hits)}</details>`:"";
  const chunkRows=chunks.length?chunks.map((chunk,i)=>{
    const id=String(chunk.chunk_id||chunk.reference_id||chunk.id||`片段 ${i+1}`);
    const source=refsByChunk.get(id)||chunk;
    const title=chunk.title||chunk.document_title||`片段 ${i+1}`;
    const excerpt=chunkPreview(chunk.text||chunk.content);
    return `<div class="path-chunk${activeIds.has(id)?" related":""}"><div><span class="path-node-index">${String(i+1).padStart(2,"0")}</span><strong>${esc(title)}</strong>${citations.has(id)?'<span class="path-cited">已引用</span>':""}</div><p>${esc(excerpt.slice(0,175))}${excerpt.length>175?"…":""}</p><small>${esc(id)} · ${sourceLabel(source)}</small></div>`;
  }).join(""):"<div class=\"path-empty\">本轮检索没有返回片段。</div>";
  const independent=references.filter(ref=>!chunks.some(chunk=>String(chunk.chunk_id||chunk.reference_id||chunk.id||"")===String(ref.chunk_id||ref.reference_id||"")));
  const independentSources=independent.length?`<details class="path-references"><summary>另有 ${independent.length} 条来源记录</summary><ul>${independent.map(ref=>`<li>${esc(ref.chunk_id||ref.reference_id||"来源")} · ${sourceLabel(ref)}</li>`).join("")}</ul></details>`:"";
  return `<section class="retrieval-card"><div class="path-query"><span class="path-node-index">${String(index+1).padStart(2,"0")}</span><div><small>检索查询 · ${esc(mode)}</small><strong>${esc(query)}</strong></div><span class="path-count">${hits.length} 命中</span></div><div class="path-branch"><div class="path-branch-head"><span>01 · 查询展开</span><span>02 · 实体关系与支撑资料</span><span>03 · 本轮命中片段</span></div><div class="path-keywords">${keywords}</div><div class="path-entities">${entityMap(entities,relationships,index,selectedIndex)}${details}${relationRows}${graphSourceIndex}</div><div class="path-chunks">${chunkRows}${independentSources}</div></div></section>`;
}
function toolOutput(call) {
  if(!call)return "尚未调用";
  if(call.status==="failed")return esc(call.error||"调用失败");
  if(call.status!=="succeeded")return "运行中";
  const out=call.output||{};
  if(call.tool_name==="search_knowledge")return `返回 ${list(out.hits).length} 个片段`;
  if(call.tool_name==="convert_units")return `${numeric(out.value)} ${esc(out.unit||"")}`;
  if(call.tool_name==="calc_heat_duty")return `${numeric(out.heat_duty_kw)} kW`;
  if(call.tool_name==="calc_mass_balance")return `${numeric(out.total_flow_kg_h)} kg/h`;
  return "已返回结果";
}
function toolFlow(result) {
  const plan=list(result.plan), calls=list(result.calls);
  if(!plan.length && !calls.length)return '<div class="path-empty">本轮尚无工具调用。</div>';
  const entries=[...calls.map(call=>({call,step:plan.find(step=>step.step_id===call.step_id)||{step_id:call.step_id,tool_name:call.tool_name,goal:toolNames[call.tool_name]||call.tool_name,depends_on:[]}})),...plan.filter(step=>!calls.some(call=>call.step_id===step.step_id)).map(step=>({call:null,step}))];
  return `<div class="tool-flow">${entries.map(({call,step},index)=>{
    const deps=list(step.depends_on);
    const refs=list(call?.input_refs);
    const status=call?.status||step.status||"pending";
    return `<div class="tool-flow-item ${esc(status)}"><span class="tool-flow-line" aria-hidden="true"></span><span class="tool-flow-dot" aria-hidden="true">${String(index+1).padStart(2,"0")}</span><div class="tool-flow-body"><div class="tool-flow-top"><div><small>${esc(call?.call_id||step.step_id||`s${index+1}`)} · ${esc(toolNames[step.tool_name]||step.tool_name||"工具")}</small><strong>${esc(step.goal||"工具调用")}</strong></div>${badge(status)}</div>${deps.length?`<p class="tool-deps">计划依赖 ${deps.map(esc).join("、")}</p>`:""}<div class="tool-result"><span>实际结果</span><strong>${toolOutput(call)}</strong></div>${refs.length?`<div class="tool-refs">${refs.map(ref=>`<span>${esc(ref.ref)} → ${esc(ref.argument)}${ref.value!==undefined?` = ${esc(ref.value)} ${esc(ref.unit||"")}`:""}</span>`).join("")}</div>`:""}</div></div>`;
  }).join("")}</div>`;
}
function pathView(result) {
  const searches=list(result.calls).filter(call=>call.tool_name==="search_knowledge" && call.output);
  const citations=new Set(result.citations||[]);
  const retrieval=searches.length?searches.map((call,index)=>retrievalCard(call,index,citations)).join(""):'<div class="path-empty">本轮没有知识检索调用。计算任务仍可在下方查看工具执行链。</div>';
  return `<div class="path-view"><p class="path-intro">节点与关系来自本轮检索返回；图谱支撑片段按 source_ids 从索引解析，可能不在本轮命中列表。工具链按实际调用、计划依赖和结果引用展示。</p><div class="path-section-heading"><span>KNOWLEDGE RETRIEVAL</span><h3>知识检索路径 <em>${searches.length}</em></h3></div>${retrieval}<div class="path-section-heading tool-heading"><span>TOOL EXECUTION</span><h3>工具执行链 <em>${list(result.calls).length}</em></h3></div>${toolFlow(result)}</div>`;
}
function summary(result) {
  const status=result.status;
  if(!state.job.finished){
    const done=(result.plan||[]).filter(s=>s.status==="succeeded").length;
    return `<div class="working"><div class="working-line"><span class="spinner" aria-hidden="true"></span>${state.job.cancel_requested?"停止中":"处理中"}</div><p>${state.job.cancel_requested?"等待当前请求返回。":""}</p><div class="live-steps">${result.plan?.length?result.plan.map(s=>`<div class="live-step"><span><span class="step-no">${esc(s.step_id)}</span>${esc(s.goal)}</span>${badge(s.status)}</div>`).join(""):"连接模型…"}</div>${done?`<div class="followup-note">已完成 ${done} / ${result.plan.length} 个步骤</div>`:""}</div>`;
  }
  const callouts={needs_input:["等待补充","补充参数后继续。"],failed:["未完成","保留已完成步骤，可继续或新建任务。"],cancelled:["已取消","已保留执行记录。"],no_evidence:["资料不足","请缩小范围或查看资料库。"],out_of_scope:["不适用","当前工具无法处理该工况。"]};
  let output=callouts[status]?`<div class="state-callout"><strong>${callouts[status][0]}</strong>${callouts[status][1]}</div>`:"";
  if(result.record_warning)output+=`<div class="state-callout">${esc(result.record_warning)}</div>`;
  output+=metrics(result);
  if(result.calls?.length)output+=`<button type="button" class="path-open" data-action="open-path"><span>查看本轮检索与工具路径</span><span aria-hidden="true">↗</span></button>`;
  output+=`<div class="content-label">${status==="completed"?"说明":"说明"}</div><article class="prose">${markdown(result.answer || "本轮没有产生可显示的答复，请查看执行过程。")}</article>`;
  const conditions=[...new Set((result.calls||[]).filter(c=>c.status==="succeeded").flatMap(c=>c.output?.assumptions||[]))];
  if(conditions.length)output+=`<details class="followup-note"><summary>工具适用条件 · ${conditions.length} 项</summary><ul>${conditions.map(a=>`<li>${esc(a)}</li>`).join("")}</ul></details>`;
  return output;
}
function steps(result) {
  if(!result.plan?.length)return '<div class="empty-state">本轮未执行工具。</div>';
  return result.plan.map((step,index)=>{
    const calls=(result.calls||[]).filter(c=>c.step_id===step.step_id);
    return `<section class="step-card"><header><span class="step-index">${String(index+1).padStart(2,"0")}</span><div class="step-title">${esc(step.goal)}<span class="step-tool">${esc(toolNames[step.tool_name]||step.tool_name)} · ${esc(step.step_id)}</span></div>${badge(step.status)}</header>${calls.length?calls.map((call,i)=>`<div class="step-detail">${calls.length>1?`<p>第 ${i+1} 次调用 · ${esc(labels[call.status]||call.status)}</p>`:""}${call.input_refs?.length?`<div class="ref-line">输入引用：${call.input_refs.map(ref=>`${esc(ref.ref)} → ${esc(ref.argument)} = ${esc(ref.value)} ${esc(ref.unit||"")}`).join("；")}</div>`:""}<details><summary>查看实际输入与${call.status==="failed"?"错误":"输出"}</summary><p class="content-label">实际输入</p><pre class="raw-block">${jsonText(call.arguments || call.requested_arguments)}</pre><p class="content-label">${call.status==="failed"?"错误":"工具输出"}</p><pre class="raw-block">${jsonText(call.status==="failed"?call.error:call.output)}</pre></details></div>`).join(""):'<div class="step-detail">未执行</div>'}</section>`;
  }).join("");
}
function evidence(result) {
  const citations=new Set(result.citations || []);
  if(!result.evidence?.length)return '<div class="empty-state">本轮无检索记录。</div>';
  const modes=[...new Set(list(result.calls).filter(call=>call.tool_name==="search_knowledge").map(call=>call.output?.retrieval?.mode).filter(Boolean))];
  const intro=modes.length?`本轮检索模式：${modes.map(esc).join("、")}。相关度仅用于排序，不代表事实可靠性。`:"本轮返回的资料片段。相关度仅用于排序，不代表事实可靠性。";
  return `<p class="evidence-intro">${intro}</p>`+result.evidence.map(hit=>{
    const excerpt=String(hit.text||"").split("\n").filter(line=>!/^\s*#/.test(line)).join("\n").trim();
    return `<section class="evidence-card"><header><h3>${esc(hit.title)}</h3><span class="badge ${citations.has(hit.chunk_id)?"":"neutral"}">${citations.has(hit.chunk_id)?"已引用":"仅检索"}</span></header><p class="evidence-source">${esc(hit.chunk_id)} · 相关度 ${Number.isFinite(hit.score)?hit.score.toFixed(3):"—"}</p><p class="evidence-preview">${esc(excerpt.slice(0,145))}${excerpt.length>145?"…":""}</p><details><summary>展开资料与来源</summary><article class="prose">${markdown(hit.text)}</article><p class="evidence-source">来源：${sourceLabel(hit)}</p></details></section>`;
  }).join("");
}
function render(force=false) {
  const result=state.job?.result;
  const signature=JSON.stringify([state.view,state.job]);
  if(!force && signature===state.rendering)return;
  state.rendering=signature;
  $("panel-content").innerHTML=!result?welcome():state.view==="path"?pathView(result):state.view==="steps"?steps(result):state.view==="evidence"?evidence(result):summary(result);
  $("step-count").textContent=result?.plan?.length||0;
  $("evidence-count").textContent=result?.evidence?.length||0;
  $("run-status").className=`badge ${result?.status||"neutral"}`;
  $("run-status").textContent=state.job?.cancel_requested&&!state.job.finished?"正在停止":labels[result?.status]||"就绪";
  $("task-question").hidden=!result?.question;
  $("task-question").textContent=result?.question||"";
  $("export-toggle").disabled=!state.job?.finished;
  if(state.job?.finished){$("export-report").href=`/api/jobs/${state.activeId}/report.md`;$("export-trace").href=`/api/jobs/${state.activeId}/trace.json`;}
  $("run-note").textContent=result?.run_id?`记录 ${result.run_id}${result.parent_run_id?" · 关联补充轮次":""}`:"本地会话";
  $("run-note").title=[result?.run_id,result?.record_warning].filter(Boolean).join(" · ");
  $("run-time").textContent=result?.finished_at&&result?.started_at?`${Math.max(0,(new Date(result.finished_at)-new Date(result.started_at))/1000).toFixed(1)} s`:"";
  setBusy(isRunning());
}
function selectView(view) {
  state.view=view;
  document.querySelectorAll(".tab").forEach(tab=>{const selected=tab.dataset.view===view;tab.classList.toggle("active",selected);tab.setAttribute("aria-selected",String(selected));tab.tabIndex=selected?0:-1;});
  $("panel-content").setAttribute("aria-labelledby",`tab-${view}`);
  render(true);$("panel-content").scrollTop=0;
}
function selectEntity(queryIndex, entityIndex) {
  if(!Number.isInteger(queryIndex)||!Number.isInteger(entityIndex)||queryIndex<0||entityIndex<0)return;
  state.selectedEntity={queryIndex,entityIndex};
  render(true);
  document.querySelector?.(`[data-query-index="${queryIndex}"][data-entity-index="${entityIndex}"]`)?.focus();
}
function renderIndexStatus(status) {
  const node=$("index-status");
  if(!status || typeof status!=="object"){
    node.className="index-status unknown";
    node.textContent="知识索引状态未提供；运行后请核对实际检索记录。";
    return;
  }
  const ready=status.state==="ready" && status.backend==="lightrag";
  const count=Number.isFinite(status.document_count)?`${status.document_count} 份资料`:"";
  const chunks=Number.isFinite(status.chunk_count)?`${status.chunk_count} 个片段`:"";
  const detail=[count,chunks].filter(Boolean).join(" · ");
  node.className=`index-status ${ready?"ready":"degraded"}`;
  node.textContent=ready?`LightRAG 图谱索引就绪${detail?` · ${detail}`:""}`:`${status.message||"知识索引尚未就绪。"}${status.backend==="lexical"?" 当前使用词法检索降级。":""}`;
}
function closeExports() {$("export-menu").hidden=true;$("export-toggle").setAttribute("aria-expanded","false");}
function closeSidebar() {$("sidebar").classList.remove("open");$("history-toggle").setAttribute("aria-expanded","false");}
function startNew(question="") {
  if(state.busy){notice("请等待当前任务完成，或先停止任务。");return;}
  ++state.selectionVersion;clearTimeout(state.poll);state.job=null;state.activeId=null;state.loadingId=null;state.selectedEntity=null;state.rendering="";
  $("question").value=question;updateCount();selectView("summary");renderHistory();closeSidebar();closeExports();$("question").focus();
}
function updateCount() {$("char-count").textContent=`${$("question").value.length} / 4000`;}
async function loadJob(id) {
  if(state.submitting)return;
  if(state.busy && state.activeId!==id){notice("当前任务正在执行，完成或停止后可切换记录。");return;}
  const version=++state.selectionVersion;
  state.loadingId=id;setBusy(isRunning());
  clearTimeout(state.poll);
  try{
    const job=await api(`/api/jobs/${id}`);
    if(version!==state.selectionVersion)return;
    showJob(job);
  }catch(error){if(version===state.selectionVersion){notice(error.message);if(isRunning())schedulePoll(state.activeId);}}
  finally{if(version===state.selectionVersion){state.loadingId=null;setBusy(isRunning());}}
}
function showJob(job) {
  if(notice.connection){$("notice").hidden=true;notice.connection=false;}
  state.activeId=job.job_id;state.job=job;state.loadingId=null;state.selectedEntity=null;
  $("question").value="";updateCount();selectView("summary");renderHistory();closeSidebar();closeExports();
  if(!job.finished)schedulePoll(job.job_id);
}
function schedulePoll(id) {
  if(state.activeId!==id)return;
  const version=state.selectionVersion;
  const current=()=>state.activeId===id && state.selectionVersion===version;
  clearTimeout(state.poll);
  state.poll=setTimeout(async()=>{
    if(!current())return;
    try{
      const job=await api(`/api/jobs/${id}`);
      if(!current())return;
      if(notice.connection){$("notice").hidden=true;notice.connection=false;}
      const wasFinished=Boolean(state.job?.finished);
      if(state.job?.cancel_requested)job.cancel_requested=true;
      state.job=job;render();
      if(job.finished){
        await refreshSession();
        if(!current())return;
        if(!wasFinished){selectView("summary");$("panel-content").scrollTop=0;notice(labels[job.result.status]||"任务已结束");}
      }else schedulePoll(id);
    }catch(error){
      if(!current())return;
      if(error.status===404){
        ++state.selectionVersion;state.job=null;state.activeId=null;state.rendering="";
        render();renderHistory();closeExports();
        notice("记录已过期，请新建任务。",true);
        refreshSession().catch(()=>{});
        return;
      }
      notice(error.message+" 正在尝试恢复连接。",true);notice.connection=true;schedulePoll(id);
    }
  },850);
}
async function submit(event) {
  event.preventDefault();if(state.busy || state.loadingId)return;
  const question=$("question").value.trim();
  if(!question){$("question").focus();return;}
  const parent=state.activeId, version=++state.selectionVersion;
  state.submitting=true;setBusy(true);closeExports();
  let accepted=false;
  try{
    const response=await api("/api/jobs",{method:"POST",body:JSON.stringify({question,parent_job_id:parent})});
    accepted=true;
    if(version!==state.selectionVersion)return;
    state.submitting=false;
    showJob(response);
    await refreshSession();
  }catch(error){
    if(version!==state.selectionVersion)return;
    notice(error.message,true);
    notice.connection=accepted || !error.status || error.status>=500;
    if(!accepted){
      // A lost POST response may still have started a server-side task.
      try{
        const session=await refreshSession();
        if(version!==state.selectionVersion || !session.active_job_id)return;
        const job=await api(`/api/jobs/${session.active_job_id}`);
        if(version===state.selectionVersion){state.submitting=false;showJob(job);}
      }catch{}
    }else schedulePoll(state.activeId);
  }finally{
    if(version===state.selectionVersion){state.submitting=false;setBusy(isRunning());}
  }
}
$("question-form").addEventListener("submit",submit);
$("question").addEventListener("input",updateCount);
$("question").addEventListener("keydown",event=>{if((event.ctrlKey||event.metaKey)&&event.key==="Enter"){event.preventDefault();$("question-form").requestSubmit();}});
$("new-task").addEventListener("click",()=>startNew());
$("cancel").addEventListener("click",async()=>{
  const id=state.activeId, version=state.selectionVersion;
  if(!id || state.cancellingId===id)return;
  state.cancellingId=id;setBusy(isRunning());
  try{
    const job=await api(`/api/jobs/${id}/cancel`,{method:"POST"});
    if(state.activeId!==id || state.selectionVersion!==version)return;
    state.job=job;render();if(!job.finished)schedulePoll(id);
  }catch(error){if(state.activeId===id && state.selectionVersion===version)notice(error.message);}
  finally{if(state.cancellingId===id)state.cancellingId=null;setBusy(isRunning());}
});
document.querySelectorAll(".tab").forEach((tab,index)=>{
  tab.addEventListener("click",()=>selectView(tab.dataset.view));
  tab.addEventListener("keydown",event=>{const tabs=[...document.querySelectorAll(".tab")];let next;if(event.key==="ArrowRight")next=(index+1)%tabs.length;if(event.key==="ArrowLeft")next=(index+tabs.length-1)%tabs.length;if(event.key==="Home")next=0;if(event.key==="End")next=tabs.length-1;if(next!==undefined){event.preventDefault();selectView(tabs[next].dataset.view);tabs[next].focus();}});
});
$("panel-content").addEventListener("click",event=>{
  if(event.target.closest('[data-action="open-path"]')){selectView("path");return;}
  const entity=event.target.closest("[data-entity-index]");
  if(entity)selectEntity(Number(entity.dataset.queryIndex),Number(entity.dataset.entityIndex));
});
$("panel-content").addEventListener("keydown",event=>{
  if(event.key!=="Enter"&&event.key!==" ")return;
  const entity=event.target.closest("[data-entity-index]");
  if(!entity)return;
  event.preventDefault();selectEntity(Number(entity.dataset.queryIndex),Number(entity.dataset.entityIndex));
});
$("export-toggle").addEventListener("click",()=>{const open=$("export-menu").hidden;$("export-menu").hidden=!open;$("export-toggle").setAttribute("aria-expanded",String(open));});
document.addEventListener("click",event=>{if(!event.target.closest(".export-wrap"))closeExports();if(!event.target.closest("#sidebar")&&!event.target.closest("#history-toggle"))closeSidebar();});
document.addEventListener("keydown",event=>{if(event.key==="Escape"){closeExports();closeSidebar();}});
$("history-toggle").addEventListener("click",()=>{const open=$("sidebar").classList.toggle("open");$("history-toggle").setAttribute("aria-expanded",String(open));});
$("about-open").addEventListener("click",()=>$("about-dialog").showModal());
$("knowledge-open").addEventListener("click",()=>{$("knowledge-dialog").showModal();closeSidebar();});
document.querySelectorAll(".close-dialog").forEach(button=>button.addEventListener("click",()=>button.closest("dialog").close()));
async function openKnowledge(item,button) {
  try{
    const detail=await api(`/api/knowledge/${encodeURIComponent(item.doc_id)}`);
    document.querySelectorAll(".knowledge-item").forEach(b=>b.classList.toggle("active",b===button));
    $("knowledge-content").innerHTML=markdown(detail.text)+`<p class="evidence-source">来源：${esc(detail.source)}</p>`;
    $("knowledge-content").scrollTop=0;
  }catch(error){notice(error.message);}
}
async function boot() {
  render();
  try{
    const data=await api("/api/bootstrap");state.configured=data.configured;state.indexStatus=data.index_status;
    renderIndexStatus(state.indexStatus);
    $("version").textContent=`v${data.version}`;
    $("model-status").textContent=data.configured?"DeepSeek":"尚未配置模型";
    $("model-status").title=data.model;
    $("model-status").classList.toggle("unconfigured",!data.configured);
    $("knowledge-count").textContent=data.knowledge.length;
    const symbols=["cp","Q","Σ","⇄","?"];
    for(const [i,example] of data.examples.entries()){
      const button=document.createElement("button");button.className="example-button";
      button.innerHTML=`<span class="example-symbol" aria-hidden="true">${symbols[i]||"↗"}</span>${esc(example.title||example.label)}`;
      button.addEventListener("click",()=>startNew(example.question));$("examples").append(button);
    }
    for(const item of data.knowledge){
      const button=document.createElement("button");button.className="knowledge-item";button.textContent=item.title;
      button.addEventListener("click",()=>openKnowledge(item,button));$("knowledge-list").append(button);
    }
    state.runs=data.session.runs || [];renderHistory();
    const resume=data.session.active_job_id || state.runs[0]?.job_id;
    if(resume)await loadJob(resume);else setBusy(false);
    if(!data.configured)notice("尚未配置模型密钥。请参照 README 配置后重启服务；知识资料可直接浏览。",true);
  }catch(error){notice(error.message+" 刷新页面可重试。",true);$("model-status").textContent="服务连接失败";$("model-status").classList.add("unconfigured");}
}
boot();
