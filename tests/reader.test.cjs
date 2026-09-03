// DOM-only interaction tests. No browser, server, network or private journal access.
const {test, after} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {execFileSync} = require("node:child_process");
const {JSDOM} = require("jsdom");
const root = path.resolve(__dirname, "..");
const data = fs.mkdtempSync(path.join(os.tmpdir(), "familyrecorder-reader-test-"));
fs.cpSync(path.join(__dirname, "fixtures/history"), data, {recursive: true});
execFileSync(process.env.FR_TEST_PYTHON || "python3", ["-c",
  "import sys; from pathlib import Path; from family_recorder.history import build_history; build_history(Path(sys.argv[1]))",
  data], {cwd: root, env: {...process.env, PYTHONPATH: path.join(root, "src")}});
after(() => fs.rmSync(data, {recursive: true, force: true}));
function load(name, hash = "") {
  const source = fs.readFileSync(path.join(data, "history", name), "utf8");
  const dom = new JSDOM(source, {runScripts: "outside-only", url: `file:///reader/${name}${hash}`});
  dom.window.HTMLElement.prototype.scrollIntoView = function () {};
  dom.window.eval(dom.window.document.querySelector("script").textContent);
  return dom;
}
function change(dom, selector, value, event = "input") {
  const element = dom.window.document.querySelector(selector);
  element.value = value;
  element.dispatchEvent(new dom.window.Event(event, {bubbles: true}));
}
test("homepage combines summary search/month/status filters and reset", () => {
  const dom = load("index.html");
  const doc = dom.window.document;
  change(dom, "#search", "包裹");
  assert.equal(doc.querySelectorAll(".day-card:not([hidden])").length, 1);
  assert.match(doc.querySelector(".day-card:not([hidden])").textContent, /2026-09-02/);
  change(dom, "#month", "2026-08", "change");
  assert.equal(doc.querySelector("#no-results").hidden, false);
  change(dom, "#search", "");
  assert.equal(doc.querySelectorAll(".day-card:not([hidden])").length, 1);
  change(dom, "#month", "", "change");
  change(dom, "#state", "pending", "change");
  assert.match(doc.querySelector(".day-card:not([hidden])").textContent, /2026-09-03/);
  change(dom, "#state", "", "change");
  assert.equal(doc.querySelectorAll(".day-card:not([hidden])").length, 3);
  dom.window.close();
});
test("day defaults to available content; tabs, anchors, font size and print work", () => {
  const dom = load("2026-09-02.html");
  const doc = dom.window.document;
  assert.equal(doc.querySelector("#summary").hidden, false);
  assert.equal(doc.querySelector("#transcript").hidden, true);
  doc.querySelector('[data-panel="transcript"]').click();
  assert.equal(doc.querySelector("#transcript").hidden, false);
  assert.equal(doc.querySelector('[data-panel="transcript"]').getAttribute("aria-pressed"), "true");
  doc.querySelector("#font-size").click();
  assert.equal(doc.querySelector(".reader").classList.contains("large"), true);
  let prints = 0;
  dom.window.print = () => prints++;
  doc.querySelector("#print").click();
  assert.equal(prints, 1);
  dom.window.close();
  const transcriptOnly = load("2026-09-03.html");
  assert.equal(transcriptOnly.window.document.querySelector("#transcript").hidden, false);
  transcriptOnly.window.close();
  const anchor = load("2026-09-02.html", "#transcript");
  assert.equal(anchor.window.document.querySelector("#transcript").hidden, false);
  anchor.window.close();
});
test("find highlights text safely, cycles multiple matches, and resets when switching", () => {
  const dom = load("2026-09-02.html", "#transcript");
  const doc = dom.window.document;
  const before = doc.querySelector("#transcript").textContent;
  change(dom, "#find", "包裹");
  doc.querySelector("#next-match").click();
  assert.equal(doc.querySelectorAll("mark").length, 2);
  assert.equal(doc.querySelector("#match-count").textContent, "1 / 2 筆");
  doc.querySelector("#next-match").click();
  assert.equal(doc.querySelector("#match-count").textContent, "2 / 2 筆");
  doc.querySelector("#next-match").click();
  assert.equal(doc.querySelector("#match-count").textContent, "1 / 2 筆");
  assert.equal(doc.querySelector("#transcript").textContent, before);
  doc.querySelector('[data-panel="summary"]').click();
  assert.equal(doc.querySelectorAll("#transcript mark").length, 0);
  change(dom, "#find", '<img src=x onerror="alert(1)">');
  // Enter works even if the existing Next button was disabled for a previous query.
  doc.querySelector("#find").dispatchEvent(new dom.window.KeyboardEvent("keydown", {key: "Enter"}));
  assert.equal(doc.querySelectorAll("img").length, 0);
  assert.equal(doc.querySelector("#match-count").textContent, "共 0 筆");
  dom.window.close();
});
