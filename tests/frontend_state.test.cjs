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
  h.requests[1].respond({runs: [], active_job_id: A});
  await flush();
  h.requests[2].respond(job(A));
  await pending;
  assert.equal(h.run("state.activeId"), A);
  assert.equal(h.run("state.busy"), true);
  assert.equal(h.element("notice").hidden, true);
  assert.equal(h.requests.filter((request) => request.options.method === "POST").length, 1);
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
