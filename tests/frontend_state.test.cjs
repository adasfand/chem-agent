"use strict";

// Run with: node --test tests/frontend_state.test.cjs
// This loads the real frontend in an isolated VM; no DOM package or network is used.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "../src/chem_agent/web/app.js"), "utf8",
).replace(/\nboot\(\);\s*$/, "\n");
const A = "a".repeat(32);
const B = "b".repeat(32);
const flush = () => new Promise((resolve) => setImmediate(resolve));

function job(id, finished = false) {
  return {
    job_id: id,
    finished,
    cancel_requested: false,
    result: {
      question: `question-${id}`,
      status: finished ? "completed" : "running",
      answer: finished ? `answer-${id}` : "",
      plan: [], calls: [], evidence: [],
    },
  };
}

function harness() {
  const elements = new Map();
  const requests = [];
  const timers = new Map();
  let timerId = 0;
  const element = (id) => {
    if (!elements.has(id)) {
      elements.set(id, {
        value: "", hidden: false, disabled: false, innerHTML: "", textContent: "",
        dataset: {}, events: {},
        classList: {add() {}, remove() {}, toggle() {return false;}},
        setAttribute() {}, replaceChildren() {}, append() {}, focus() {},
        addEventListener(kind, callback) {this.events[kind] = callback;},
      });
    }
    return elements.get(id);
  };
  const sandbox = {
    crypto: require("node:crypto").webcrypto,
    document: {
      getElementById: element, querySelectorAll: () => [], addEventListener() {},
      createElement: () => element(Symbol()),
    },
    setTimeout(callback, delay) {
      const id = ++timerId;
      timers.set(id, {callback, delay});
      return id;
    },
    clearTimeout(id) {timers.delete(id);},
    fetch(url, options) {
      return new Promise((resolve, reject) => requests.push({
        url, options, reject,
        respond(data, status = 200) {
          resolve({ok: status >= 200 && status < 300, status, json: async () => data});
        },
      }));
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox, {filename: "app.js"});
  const run = (code) => vm.runInContext(code, sandbox);
  run("state.configured=true");
  return {
    run, element, requests, timers,
    show(value) {run(`showJob(${JSON.stringify(value)})`);},
    submit(text) {
      element("question").value = text;
      return run("submit({preventDefault(){}})");
    },
    poll() {
      const id = run("state.poll");
      const timer = timers.get(id);
      assert.ok(timer, "the current poll must be scheduled");
      timers.delete(id);
      return timer.callback();
    },
  };
}

test("tab changes cannot unlock submission while POST is pending", async () => {
  const h = harness();
  const pending = h.submit("first question");
  assert.equal(h.requests.length, 1);
  h.run("selectView('steps')");
  assert.equal(h.run("state.busy"), true);
  assert.equal(h.element("submit").disabled, true);
  assert.equal(h.element("new-task").disabled, true);
  await h.submit("duplicate question");
  assert.equal(h.requests.length, 1);
  h.requests[0].respond(job(A));
  await flush();
  h.requests[1].respond({runs: [], active_job_id: A});
  await pending;
  assert.equal(h.run("state.activeId"), A);
  assert.equal(h.run("state.submitting"), false);
  assert.equal(h.run("state.busy"), true);
});

test("the last history selection wins when earlier responses arrive late", async () => {
  const h = harness();
  const first = h.run(`loadJob('${A}')`);
  const second = h.run(`loadJob('${B}')`);
  h.requests[1].respond(job(B, true));
  await second;
  h.requests[0].respond(job(A, true));
  await first;
  assert.equal(h.run("state.activeId"), B);
  assert.equal(h.run("state.job.job_id"), B);
  assert.equal(h.element("export-report").href, `/api/jobs/${B}/report.md`);
});

test("submitting while a history selection loads cannot use the previous parent", async () => {
  const h = harness();
  h.show(job(A, true));
  const loading = h.run(`loadJob('${B}')`);
  assert.equal(h.element("submit").disabled, true);
  await h.submit("followup intended for B");
  assert.equal(h.requests.length, 1);
  assert.equal(h.requests[0].url, `/api/jobs/${B}`);
  h.requests[0].respond(job(B, true));
  await loading;
  assert.equal(h.element("submit").disabled, false);
  assert.equal(h.run("state.activeId"), B);
});

test("starting a new task invalidates an outstanding history fetch", async () => {
  const h = harness();
  const loading = h.run(`loadJob('${A}')`);
  h.run("startNew('keep this new question')");
  h.requests[0].respond(job(A, true));
  await loading;
  assert.equal(h.run("state.activeId"), null);
  assert.equal(h.run("state.job"), null);
  assert.equal(h.element("question").value, "keep this new question");
});

test("a late cancellation reply cannot replace another selected job", async () => {
  const h = harness();
  h.show(job(A));
  const cancelling = h.element("cancel").events.click();
  assert.equal(h.element("cancel").disabled, true);
  // The normal poll finishes A while its cancellation response is still in flight.
  h.run(`state.job=${JSON.stringify(job(A, true))};render()`);
  const selecting = h.run(`loadJob('${B}')`);
  h.requests[1].respond(job(B, true));
  await selecting;
  h.requests[0].respond(job(A, true));
  await cancelling;
  assert.equal(h.run("state.activeId"), B);
  assert.equal(h.run("state.job.job_id"), B);
  assert.equal(h.element("export-report").href, `/api/jobs/${B}/report.md`);
});

test("a recovered poll clears its persistent connection warning", async () => {
  const h = harness();
  h.show(job(A));
  const failedPoll = h.poll();
  h.requests[0].reject(new Error("offline"));
  await failedPoll;
  assert.equal(h.element("notice").hidden, false);
  assert.equal(h.run("notice.connection"), true);
  const recoveredPoll = h.poll();
  h.requests[1].respond(job(A));
  await recoveredPoll;
  assert.equal(h.element("notice").hidden, true);
  assert.equal(h.run("notice.connection"), false);
});

test("expired jobs stop polling and release the new-task controls", async () => {
  const h = harness();
  h.show(job(A));
  const polling = h.poll();
  h.requests[0].respond({detail: "任务不存在或已过期。"}, 404);
  await polling;
  h.requests[1].respond({runs: [], active_job_id: null});
  await flush();
  assert.equal(h.run("state.job"), null);
  assert.equal(h.run("state.activeId"), null);
  assert.equal(h.run("state.busy"), false);
  assert.equal(h.element("new-task").disabled, false);
  assert.match(h.element("notice").textContent, /记录已过期/);
  assert.equal([...h.timers.values()].filter((timer) => timer.delay === 850).length, 0);
});

test("a stale session refresh failure cannot cancel the new job's polling", async () => {
  const h = harness();
  h.show(job(A));
  const oldPolling = h.poll();
  h.requests[0].respond(job(A, true));
  await flush();
  assert.equal(h.requests[1].url, "/api/session");
  h.run("startNew()");
  const newSubmission = h.submit("new task");
  h.requests[2].respond(job(B));
  await flush();
  h.requests[3].respond({runs: [], active_job_id: B});
  await newSubmission;
  const newTimer = h.run("state.poll");
  h.requests[1].reject(new Error("old refresh failed"));
  await oldPolling;
  assert.equal(h.run("state.activeId"), B);
  assert.equal(h.run("state.poll"), newTimer);
  assert.ok(h.timers.has(newTimer));
});

test("an older submission's finally block cannot unlock a newer POST", async () => {
  const h = harness();
  const first = h.submit("first question");
  h.requests[0].respond(job(A, true));
  await flush();
  const second = h.submit("followup question");
  h.requests[1].respond({runs: [], active_job_id: null});
  await first;
  assert.equal(h.run("state.submitting"), true);
  assert.equal(h.run("state.busy"), true);
  h.requests[2].respond(job(B));
  await flush();
  h.requests[3].respond({runs: [], active_job_id: B});
  await second;
  assert.equal(h.run("state.activeId"), B);
});

test("a lost POST response recovers the server's active job without resubmitting", async () => {
  const h = harness();
  const pending = h.submit("first question");
  h.requests[0].reject(new Error("response was lost"));
  await flush();
  const submission = JSON.parse(h.requests[0].options.body);
  h.requests[1].respond({runs: [{job_id:A, client_request_id:submission.client_request_id}], active_job_id: A});
  await flush();
  h.requests[2].respond(job(A));
  await pending;
  assert.equal(h.run("state.activeId"), A);
  assert.equal(h.run("state.busy"), true);
  assert.equal(h.element("notice").hidden, true);
  assert.equal(h.requests.filter((request) => request.options.method === "POST").length, 1);
});

test("a lost POST response also recovers the exact job after it has completed", async () => {
  const h = harness();
  const pending = h.submit("quickly completed question");
  const submission = JSON.parse(h.requests[0].options.body);
  assert.match(submission.client_request_id, /^[a-f0-9]{32}$/);
  assert.equal(h.requests[0].options.headers["X-Request-ID"], submission.client_request_id);
  h.requests[0].reject(new Error("response was lost"));
  await flush();
  h.requests[1].respond({runs: [{job_id:A, client_request_id:submission.client_request_id}], active_job_id: null});
  await flush();
  h.requests[2].respond(job(A, true));
  await pending;
  assert.equal(h.run("state.activeId"), A);
  assert.equal(h.run("state.job.finished"), true);
  assert.equal(h.run("state.busy"), false);
  assert.equal(h.element("export-report").href, `/api/jobs/${A}/report.md`);
  assert.equal(h.element("notice").hidden, true);
});

test("lost submission recovery cannot adopt another tab's unrelated job", async () => {
  const h = harness();
  const pending = h.submit("our question");
  h.requests[0].reject(new Error("response was lost"));
  await flush();
  h.requests[1].respond({runs: [{job_id:A, client_request_id:"f".repeat(32)}], active_job_id: A});
  await pending;
  assert.equal(h.run("state.activeId"), null);
  assert.equal(h.requests.length, 2);
  assert.equal(h.element("question").value, "our question");
});

test("retrying an unresolved submission preserves its idempotency key", async () => {
  const h = harness();
  const first = h.submit("our question");
  const original = JSON.parse(h.requests[0].options.body);
  h.requests[0].reject(new Error("response was lost"));
  await flush();
  h.requests[1].reject(new Error("recovery was also lost"));
  await first;
  const repeated = h.submit("our question");
  assert.deepEqual(JSON.parse(h.requests[2].options.body), original);
  h.requests[2].respond(job(A, true));
  await flush();
  h.requests[3].respond({runs: [], active_job_id: null});
  await repeated;
  assert.equal(h.run("state.pendingSubmission"), null);
});

test("the last knowledge selection wins over a delayed earlier response", async () => {
  const h = harness();
  const first = h.run("openKnowledge({doc_id:'first'}, {})");
  const second = h.run("openKnowledge({doc_id:'second'}, {})");
  h.requests[1].respond({text:"second selection",source:"second source"});
  await second;
  h.requests[0].respond({text:"first selection",source:"first source"});
  await first;
  assert.match(h.element("knowledge-content").innerHTML, /second selection/);
  assert.doesNotMatch(h.element("knowledge-content").innerHTML, /first selection/);
});

test("a stale knowledge error cannot hide a newer successful selection", async () => {
  const h = harness();
  h.element("notice").hidden = true;
  const first = h.run("openKnowledge({doc_id:'first'}, {})");
  const second = h.run("openKnowledge({doc_id:'second'}, {})");
  h.requests[1].respond({text:"second selection",source:"second source"});
  await second;
  h.requests[0].reject(new Error("old selection failed"));
  await first;
  assert.equal(h.element("notice").hidden, true);
  assert.match(h.element("knowledge-content").innerHTML, /second selection/);
});

test("save warnings remain visible and escaped while export stays available", () => {
  const h = harness();
  const result = job(A, true);
  result.result.run_id = "verified-run";
  result.result.record_warning = "保存失败 <img src=x onerror=alert(1)>；可从当前页面导出。";
  h.show(result);
  assert.match(h.element("panel-content").innerHTML, /保存失败 &lt;img/);
  assert.doesNotMatch(h.element("panel-content").innerHTML, /<img/);
  assert.match(h.element("run-note").title, /保存失败/);
  assert.equal(h.element("export-toggle").disabled, false);
});

test("metric cards round to six significant digits", () => {
  const h = harness();
  assert.equal(h.run("numeric(46.4444444444)"), "46.4444");
});

test("path view shows only returned retrieval relations and actual tool references", () => {
  const h = harness();
  const value = job(A, true);
  value.result.citations = ["chunk-1"];
  value.result.plan = [
    {step_id:"s1", goal:"检索热量关系", tool_name:"search_knowledge", depends_on:[], status:"succeeded"},
    {step_id:"s2", goal:"核对单位", tool_name:"convert_units", depends_on:["s1"], status:"succeeded"},
  ];
  value.result.calls = [
    {
      step_id:"s1", tool_name:"search_knowledge", status:"succeeded", arguments:{query:"显热负荷"},
      output:{
        hits:[{chunk_id:"chunk-1", title:"显热", text:"# 显热\n## 公式与输入\n热负荷公式\n来源：https://example.org/heat", source:"https://example.org/heat"}],
        retrieval:{
          query:"显热负荷", mode:"mix", keywords:{high_level:["热量"],low_level:["比热"]},
          entities:[{id:"heat",name:"显热",description:"显热说明<SEP>补充说明<SEP> 显热说明 <SEP> <img src=x>",source_ids:["chunk-1"]},{id:"cp",name:"比热",description:"比热说明"}],
          relationships:[{source:"heat",target:"cp",description:"由比热参与计算",source_ids:["chunk-2","unresolved-id"]}],
          chunks:[{chunk_id:"chunk-1",title:"显热",text:"# 显热\n## 公式与输入\n热负荷公式\n来源：https://example.org/heat",source:"https://example.org/heat"}],
          references:[{chunk_id:"chunk-1",source:"https://example.org/heat"}],
          graph_sources:[
            {chunk_id:"chunk-1",title:"显热图谱依据",source:"官方课程",url:"https://example.org/heat",text:"# 显热\n热负荷公式"},
            {chunk_id:"chunk-2",title:"关系图谱依据",source:"本地资料",url:"javascript:alert(1)",text:"关系说明 <script>alert(1)</script>"},
          ],
        },
      },
    },
    {
      step_id:"s2", tool_name:"convert_units", status:"succeeded", input_refs:[{ref:"s1.value",argument:"value",value:2,unit:"kg/s"}],
      output:{value:2,unit:"kg/s"},
    },
  ];
  h.show(value);
  h.run("selectView('path')");
  const html = h.element("panel-content").innerHTML;
  assert.match(html, /显热负荷/);
  assert.match(html, /<line [^>]*class="graph-edge"/);
  assert.match(html, /role="button" tabindex="0" aria-label="查看实体 显热"/);
  assert.match(html, /显热说明/);
  assert.match(html, /<ul class="entity-description-list"><li>显热说明<\/li><li>补充说明<\/li><li>&lt;img src=x&gt;<\/li><\/ul>/);
  assert.doesNotMatch(html, /<SEP>/);
  assert.doesNotMatch(html, /<img src=x>/);
  assert.match(html, /实体支撑片段 · 1/);
  assert.match(html, /显热图谱依据/);
  assert.match(html, /同时命中/);
  assert.match(html, /href="https:\/\/example.org\/heat"/);
  assert.match(html, /关系支撑片段 · 2/);
  assert.match(html, /关系图谱依据/);
  assert.match(html, /图谱支撑 · 非命中/);
  assert.match(html, /未解析来源/);
  assert.match(html, /unresolved-id/);
  assert.match(html, /全部图谱支撑资料 · 2 份/);
  assert.match(html, /1 命中/);
  assert.equal((html.match(/class="path-chunk(?: related)?"/g)||[]).length, 1);
  assert.doesNotMatch(html, /href="javascript:/);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.match(html, /class="path-chunk related"/);
  assert.match(html, /<p>公式与输入 热负荷公式<\/p>/);
  assert.doesNotMatch(html, /<p>[^<]*来源：/);
  assert.doesNotMatch(html, /<p>[^<]*##/);
  assert.match(html, /chunk-1/);
  assert.match(html, /已引用/);
  assert.match(html, /https:\/\/example.org\/heat/);
  assert.match(html, /s1.value → value = 2 kg\/s/);
  assert.match(html, /2 kg\/s/);
  let prevented = false;
  h.element("panel-content").events.keydown({
    key:"Enter", preventDefault(){prevented=true;},
    target:{closest:()=>({dataset:{queryIndex:"0",entityIndex:"1"}})},
  });
  assert.equal(prevented, true);
  assert.match(h.element("panel-content").innerHTML, /比热说明/);
  assert.match(h.element("panel-content").innerHTML, /该实体没有明确关联到本轮命中片段/);
  assert.match(h.element("panel-content").innerHTML, /图谱未返回来源编号/);
});

test("path view does not invent graph entities for a plain hit and escapes source content", () => {
  const h = harness();
  const value = job(A, true);
  value.result.calls = [{
    step_id:"s1", tool_name:"search_knowledge", status:"succeeded", arguments:{query:"热量"},
    output:{hits:[{chunk_id:"c1",title:"<img src=x>",text:"内容",source:"javascript:alert(1)"}]},
  }];
  h.show(value);
  h.run("selectView('path')");
  const html = h.element("panel-content").innerHTML;
  assert.match(html, /没有返回可展示的实体/);
  assert.doesNotMatch(html, /class="graph-edge"/);
  assert.match(html, /&lt;img src=x&gt;/);
  assert.doesNotMatch(html, /href="javascript:/);
});

test("index status distinguishes ready graph index from lexical fallback", () => {
  const h = harness();
  h.run("renderIndexStatus({state:'ready',backend:'lightrag',document_count:20,chunk_count:80,message:'ok'})");
  assert.match(h.element("index-status").textContent, /LightRAG 图谱索引就绪 · 20 份资料 · 80 个片段/);
  h.run("renderIndexStatus({state:'missing',backend:'lexical',message:'尚未构建索引'})");
  assert.match(h.element("index-status").textContent, /尚未构建索引.*词法检索降级/);
});
