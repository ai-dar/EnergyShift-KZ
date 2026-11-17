// «SQL»: каталог из 12 запросов проекта; запрос выполняется в SQLite на сервере, результат приходит таблицей.
import { state, subscribe } from "./store.js";
import { getJSON, el, fmt, fmtCell } from "./util.js";

export function initSql(showError) {
  const list = document.getElementById("sql-list");
  const title = document.getElementById("sql-title");
  const code = document.getElementById("sql-code");
  const count = document.getElementById("sql-count");
  const head = document.querySelector("#sql-table thead");
  const body = document.querySelector("#sql-table tbody");
  let catalog = null, current = null;

  async function run(name) {
    current = name;
    list.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.name === name)));
    try {
      const result = await getJSON(`/api/sql/${name}`);
      if (current !== name) return;
      title.textContent = result.title;
      code.textContent = result.sql;
      count.textContent = result.rows.length < result.total
        ? `Показано ${fmt(result.rows.length)} из ${fmt(result.total)} строк`
        : `Строк в результате: ${fmt(result.total)}`;
      head.replaceChildren(el("tr", {}, ...result.columns.map((c) => el("th", { text: c }))));
      body.replaceChildren(...result.rows.map((row) =>
        el("tr", {}, ...row.map((v) => el("td", { class: typeof v === "number" ? "num" : "", text: fmtCell(v) })))));
      showError(null);
    } catch (err) {
      showError(err.message);
    }
  }

  async function open() {
    try {
      if (!catalog) {
        catalog = await getJSON("/api/sql");
        list.replaceChildren(...catalog.map((q) => el("li", {},
          el("button", { type: "button", "data-name": q.name, "aria-pressed": "false", text: q.title, onclick: () => run(q.name) }))));
      }
      if (!current && catalog.length) run(catalog[0].name);
    } catch (err) {
      showError(err.message);
    }
  }

  subscribe((_, changed) => { if (changed.includes("view") && state.view === "sql") open(); });
}
