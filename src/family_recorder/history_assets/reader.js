"use strict";
// Offline only: no fetch, storage, telemetry, external links or HTML injection.
const search = document.getElementById("search");
if (search) {
  const month = document.getElementById("month");
  const state = document.getElementById("state");
  const calendarOnly = document.getElementById("calendar-only");
  const cards = [...document.querySelectorAll(".day-card")];
  const filter = () => {
    const query = search.value.trim().toLocaleLowerCase();
    let count = 0;
    for (const card of cards) {
      const show = (!query || card.dataset.search.includes(query)) &&
        (!month.value || card.dataset.month === month.value) &&
        (!state.value || card.dataset.state === state.value) &&
        (calendarOnly.disabled || !calendarOnly.checked || Number(card.dataset.calendar) > 0);
      card.hidden = !show;
      if (show) count++;
    }
    document.getElementById("result-count").textContent = `顯示 ${count} / ${cards.length} 天`;
    document.getElementById("no-results").hidden = count !== 0;
  };
  search.addEventListener("input", filter);
  month.addEventListener("change", filter);
  state.addEventListener("change", filter);
  calendarOnly.addEventListener("change", filter);
  window.addEventListener("pageshow", filter);
}

const toolbar = document.querySelector(".reader-tools");
if (toolbar) {
  const panels = [...document.querySelectorAll(".reading-panel")];
  const buttons = [...document.querySelectorAll("button[data-panel]")];
  const find = document.getElementById("find");
  const counter = document.getElementById("match-count");
  const next = document.getElementById("next-match");
  let matches = [];
  let current = -1;
  let findTimer;
  function highlight() {
    for (const panel of panels) {
      for (const mark of panel.querySelectorAll("mark")) {
        mark.replaceWith(document.createTextNode(mark.textContent));
      }
      panel.normalize();
    }
    matches = [];
    current = -1;
    const query = find.value.trim().toLocaleLowerCase();
    const active = panels.find(panel => !panel.hidden);
    if (query && active) {
      const walker = document.createTreeWalker(active, NodeFilter.SHOW_TEXT);
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      for (const node of nodes) {
        const source = node.textContent;
        const lower = source.toLocaleLowerCase();
        if (!lower.includes(query)) continue;
        const fragment = document.createDocumentFragment();
        let start = 0;
        let offset;
        while ((offset = lower.indexOf(query, start)) !== -1) {
          fragment.append(document.createTextNode(source.slice(start, offset)));
          const mark = document.createElement("mark");
          mark.textContent = source.slice(offset, offset + query.length);
          fragment.append(mark);
          matches.push(mark);
          start = offset + query.length;
        }
        fragment.append(document.createTextNode(source.slice(start)));
        node.replaceWith(fragment);
      }
    }
    counter.textContent = query ? `共 ${matches.length} 筆` : "";
    next.disabled = matches.length === 0;
  }
  function selectPanel() {
    const hash = window.location.hash.slice(1);
    const selected = panels.some(panel => panel.id === hash) ? hash : toolbar.dataset.default;
    panels.forEach(panel => { panel.hidden = panel.id !== selected; });
    buttons.forEach(button => {
      button.setAttribute("aria-pressed", String(button.dataset.panel === selected));
    });
    highlight();
  }
  buttons.forEach(button => button.addEventListener("click", () => {
    // replaceState avoids the scroll jump from setting a fragment on a long page.
    try { history.replaceState(null, "", `#${button.dataset.panel}`); }
    catch { window.location.hash = button.dataset.panel; }
    selectPanel();
  }));
  window.addEventListener("hashchange", selectPanel);
  find.addEventListener("input", () => {
    clearTimeout(findTimer);
    next.disabled = !find.value.trim();
    findTimer = setTimeout(() => { highlight(); findTimer = null; }, 150);
  });
  function nextMatch() {
    clearTimeout(findTimer);
    if (findTimer) { highlight(); findTimer = null; }
    if (!matches.length) return;
    if (current >= 0) matches[current].classList.remove("current");
    current = (current + 1) % matches.length;
    matches[current].classList.add("current");
    const disclosure = matches[current].closest("details");
    if (disclosure) disclosure.open = true;
    matches[current].scrollIntoView({block: "center"});
    counter.textContent = `${current + 1} / ${matches.length} 筆`;
  }
  next.addEventListener("click", nextMatch);
  find.addEventListener("keydown", event => {
    if (event.key === "Enter") { event.preventDefault(); nextMatch(); }
  });
  document.getElementById("font-size").addEventListener("click", event => {
    const large = document.querySelector(".reader").classList.toggle("large");
    event.currentTarget.textContent = large ? "標準字體" : "放大字體";
    event.currentTarget.setAttribute("aria-pressed", String(large));
  });
  document.getElementById("print").addEventListener("click", () => window.print());
  selectPanel();
}
