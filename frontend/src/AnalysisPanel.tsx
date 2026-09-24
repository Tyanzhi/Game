import { useState } from "react";
import type { Tick } from "./api";

const labels: Record<string, string> = {
  observe: "сбор информации", diplomatic_outreach: "дипломатический контакт",
  economic_adjustment: "экономическая корректировка", defensive_posture: "оборонная позиция",
  public_statement: "публичное заявление"
};

export function AnalysisPanel({ ticks }: { ticks: Tick[] }) {
  const [level, setLevel] = useState("brief");
  const [selected, setSelected] = useState("latest");
  const ordered = [...ticks].sort((a, b) => b.tick - a.tick);
  const current = selected === "latest" ? ordered[0] : ordered.find(t => String(t.tick) === selected);
  const report = current?.explanation;
  return <section className="panel analysis-panel" aria-label="World Engine Analysis">
    <p className="eyebrow">WORLD ENGINE ANALYSIS</p>
    <h2>Объяснение результатов симуляции</h2>
    <div className="analysis-controls">
      <label>Цикл <select value={selected} onChange={e => setSelected(e.target.value)}>
        <option value="latest">Последний</option>
        {ordered.map(t => <option key={t.tick} value={t.tick}>Тик {t.tick}</option>)}
      </select></label>
      <label>Подробность <select value={level} onChange={e => setLevel(e.target.value)}>
        <option value="brief">Кратко</option><option value="analysis">Аналитически</option>
        <option value="technical">Технически</option>
      </select></label>
    </div>
    {!report ? <p>Для этого тика объяснение не сохранено. Старые результаты не дополняются вымышленными причинами.</p> : <>
      <p className="muted">Тик {report.tick} · {current?.created_at ?? "время не записано"} · {report.version}</p>
      <h3>Краткий итог</h3><p>{report.summary}</p>
      <h3>Изменения относительно предыдущего шага</h3>
      <ul>{report.changes.slice(0, level === "brief" ? 3 : 30).map((c, i) => <li key={i}>{c.text}</li>)}</ul>
      {report.changes.length > (level === "brief" ? 3 : 30) && <p>Показаны крупнейшие изменения; полный перечень — в техническом отчёте.</p>}
      {level !== "brief" && <>
        <h3>Внешние данные и сообщения</h3>
        <p>Статус FACT/CLAIM/HYPOTHESIS присвоен обработчиком источников и не является независимой проверкой истинности.</p>
        {report.observed_data.length === 0 && <p>Новых внешних событий нет.</p>}
        {report.observed_data.map(e => <article key={e.event_id}>
          <p><strong>{e.status}</strong> · {e.timestamp} · оценка достоверности {Math.round(e.confidence * 100)}%</p>
          <p>{e.description}</p>
          {e.source_urls.filter(url => /^https?:\/\//i.test(url)).map(url =>
            <p key={url}><a href={url} target="_blank" rel="noopener noreferrer">Источник</a></p>)}
        </article>)}
        <h3>Решения акторов — интерпретация модели</h3>
        {report.actor_decisions.map(d => <article key={d.decision_id}>
          <p>{d.text}</p>
          {typeof d.confidence === "number" && <p>Оценка уверенности в выборе: {Math.round(d.confidence * 100)}%.</p>}
          <p>Рассмотренные варианты:</p>
          <ul>{(d.options ?? []).map((o, i) => <li key={i}>{labels[o.action ?? ""] ?? o.action ?? "Вариант"}
            {typeof o.expected_utility === "number" ? `; полезность ${o.expected_utility.toFixed(3)}` : ""}
            {typeof o.risk === "number" ? `; риск ${o.risk.toFixed(3)}` : ""}</li>)}</ul>
          {!d.options?.length && <p>Альтернативы не записаны.</p>}
        </article>)}
        <h3>Исполненные действия и реакции</h3>
        <ul>{report.actions.map((a, i) => <li key={i}>{a.actor_id}: {labels[String(a.effects?.action)] ?? String(a.effects?.action ?? "действие")} · {a.status}
          {a.effects?.reaction_to_action_id ? `; ответ на ${String(a.effects.reaction_to_action_id)}` : ""}</li>)}</ul>
        <h3>Почему это произошло: записанные механизмы и каскадные эффекты</h3>
        <ul>{report.why_it_happened.slice(0, 30).map((s, i) => <li key={i}>{s}</li>)}</ul>
        <p>Перечень эффектов не доказывает полную причинную цепочку. Незаписанные связи с событиями и источниками не достраиваются.</p>
        <h3>Альтернативные сценарии</h3>
        {report.alternative_scenarios.length ? report.alternative_scenarios.map((s, i) =>
          <details key={i}><summary>{s.actor_id}: расчёт альтернатив движком</summary><pre>{JSON.stringify(s.results, null, 2)}</pre></details>)
          : <p>Контрфактическое сравнение не рассчитано.</p>}
      </>}
      <h3>Симуляционный прогноз</h3>
      {report.forecasts.length === 0 && <p>Прогноз для этого тика не рассчитан.</p>}
      {report.forecasts.slice(0, level === "brief" ? 3 : 30).map((f, i) => <article key={i}>
        <p>{f.text}</p>{level !== "brief" && <p>Факторы: {(f.drivers ?? []).join(", ")} · модель {f.model_version}</p>}
      </article>)}
      <h3>Ключевые неопределённости</h3><ul>{report.key_uncertainties.map(s => <li key={s}>{s}</li>)}</ul>
      {level === "technical" && <><h3>Структурированный отчёт</h3><pre>{JSON.stringify(report, null, 2)}</pre></>}
    </>}
  </section>;
}
