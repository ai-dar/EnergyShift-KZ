// Левая колонка: факты о выбранной стране за выбранный год, сравнение с Казахстаном и подсказка к разделу.
import { state, data, country, val, rank, worldShare, subscribe } from "./store.js";
import { fmt, el } from "./util.js";

const HINTS = {
  globe: "Чем выше и горячее столбик страны, тем больше значение. Казахстан обведён бирюзой. Год меняется на кривой внизу.",
  mix: "Каждый столбец — год, каждый слой — источник энергии. Горячие цвета — ископаемое топливо, холодные — низкоуглеродные источники.",
  seasons: "Один виток спирали — год, круг — двенадцать месяцев. Чем дальше точка от оси, тем больше выбросов электростанций за месяц.",
  forecast: "Модели обучаются на сервере Python и проверяются на годах, которых не видели. Наивный прогноз служит точкой отсчёта.",
  sql: "Запросы выполняются в базе SQLite проекта прямо сейчас. Слева каталог, справа текст запроса и результат.",
};

export function initLede() {
  const year = document.getElementById("lede-year");
  const name = document.getElementById("lede-name");
  const facts = document.getElementById("lede-facts");
  const compare = document.getElementById("lede-compare");
  const hint = document.getElementById("lede-hint");

  function fact(key, value, unit, text) {
    const item = el("li", { class: key === state.metric ? "is-current" : "" });
    const strong = el("b", { text: value });
    if (unit) strong.append(" ", el("small", { text: unit }));
    item.append(strong, el("span", { text }));
    return item;
  }

  function render() {
    const c = country(state.iso);
    const target = data.boot.target;
    year.textContent = `${state.year} год`;
    name.textContent = c.label;
    name.classList.toggle("is-long", c.label.length > 11);

    const perCapita = val("co2_per_capita", state.iso, state.year);
    const place = rank("co2_per_capita", state.iso, state.year);
    const total = val("co2", state.iso, state.year);
    const share = worldShare(state.iso, state.year);
    const fossil = val("fossil_share_energy", state.iso, state.year);
    const clean = val("low_carbon_share_energy", state.iso, state.year);
    const energy = val("energy_per_capita", state.iso, state.year);

    facts.replaceChildren(
      fact("co2_per_capita", fmt(perCapita, 1), perCapita === null ? "" : "т",
        place ? `CO₂ на человека, ${place.place}-е место из ${place.total} стран` : "CO₂ на человека"),
      fact("co2", fmt(total, total !== null && total < 10 ? 1 : 0), total === null ? "" : "млн т",
        share === null ? "выбросы CO₂ за год" : `выбросы CO₂ за год, ${fmt(share, share < 1 ? 2 : 1)} % мировых`),
      fact("fossil_share_energy", fmt(fossil, 1), fossil === null ? "" : "%",
        fossil === null ? "доля угля, нефти и газа: в источнике нет энергобаланса этой страны" : "энергии из угля, нефти и газа"),
      fact("low_carbon_share_energy", fmt(clean, 1), clean === null ? "" : "%", "энергии из низкоуглеродных источников"),
      fact("energy_per_capita", fmt(energy, 0), energy === null ? "" : "кВт·ч", "энергии на человека за год"),
    );

    compare.textContent = "";
    if (state.iso !== target) {
      const kz = val("co2_per_capita", target, state.year);
      if (perCapita !== null && kz) {
        const ratio = perCapita / kz;
        compare.textContent = ratio >= 1
          ? `На человека в ${fmt(ratio, 1)} раза больше CO₂, чем в Казахстане (${fmt(kz, 1)} т).`
          : `На человека в ${fmt(1 / ratio, 1)} раза меньше CO₂, чем в Казахстане (${fmt(kz, 1)} т).`;
      }
    }
    hint.textContent = HINTS[state.view];
  }

  subscribe(render);
  render();
}
