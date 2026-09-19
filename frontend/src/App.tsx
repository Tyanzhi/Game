import { FormEvent, useEffect, useMemo, useState } from "react";
import { Actor, Simulation, Tick, api, simulationSocket } from "./api";

function pct(value: number) {
  return `${Math.round(value * 100)}%`;
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric">
      <div className="metric__top">
        <span>{label}</span>
        <strong>{pct(value)}</strong>
      </div>
      <div className="bar">
        <span style={{ width: pct(value) }} />
      </div>
    </div>
  );
}

export default function App() {
  const [actors, setActors] = useState<Actor[]>([]);
  const [simulations, setSimulations] = useState<Simulation[]>([]);
  const [ticks, setTicks] = useState<Tick[]>([]);
  const [selectedSimulation, setSelectedSimulation] = useState("");
  const [engineStatus, setEngineStatus] = useState("connecting");
  const [runTicks, setRunTicks] = useState(5);
  const [seed, setSeed] = useState(42);
  const [running, setRunning] = useState(false);
  const [liveEvents, setLiveEvents] = useState<unknown[]>([]);
  const [error, setError] = useState("");

  async function refresh() {
    try {
      const [health, actorRows, simulationRows] = await Promise.all([
        api.health(),
        api.actors(),
        api.simulations()
      ]);
      setEngineStatus(health.status);
      setActors(actorRows);
      setSimulations(simulationRows);
      setError("");
      if (!selectedSimulation && simulationRows[0]) {
        setSelectedSimulation(simulationRows[0].id);
      }
    } catch (err) {
      setEngineStatus("offline");
      setError(err instanceof Error ? err.message : "API unavailable");
    }
  }

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 10000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!selectedSimulation) {
      setTicks([]);
      return;
    }
    api.ticks(selectedSimulation)
      .then(setTicks)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load ticks"));

    const socket = simulationSocket(selectedSimulation, (payload) => {
      setLiveEvents((items) => [payload, ...items].slice(0, 20));
      if (
        typeof payload === "object" &&
        payload !== null &&
        "type" in payload &&
        (payload as { type?: string }).type === "tick_completed"
      ) {
        api.ticks(selectedSimulation).then(setTicks).catch(() => undefined);
      }
    });
    return () => socket?.close();
  }, [selectedSimulation]);

  const selected = useMemo(
    () => simulations.find((item) => item.id === selectedSimulation),
    [simulations, selectedSimulation]
  );

  async function submit(event: FormEvent) {
    event.preventDefault();
    setRunning(true);
    setError("");
    try {
      const result = await api.runSimulation(runTicks, seed);
      setSelectedSimulation(result.simulation_id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Simulation failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <main className="shell">
      <header className="hero">
        <div>
          <p className="eyebrow">WORLD ENGINE / COMMAND LAYER</p>
          <h1>Strategic World Simulator</h1>
          <p className="sub">
            Кризисы, рынки, восприятие, стратегии, коалиции и прогнозы —
            в одном живом тиковом контуре.
          </p>
        </div>
        <div className={`status status--${engineStatus === "ok" ? "ok" : "bad"}`}>
          <span />
          API {engineStatus}
        </div>
      </header>

      {error && <div className="alert">{error}</div>}

      <section className="grid grid--top">
        <article className="panel panel--control">
          <div className="panel__heading">
            <div>
              <p className="eyebrow">SIMULATION CONTROL</p>
              <h2>Запуск мира</h2>
            </div>
          </div>
          <form className="controls" onSubmit={submit}>
            <label>
              Тики
              <input
                type="number"
                min={1}
                max={120}
                value={runTicks}
                onChange={(e) => setRunTicks(Number(e.target.value))}
              />
            </label>
            <label>
              Seed
              <input
                type="number"
                value={seed}
                onChange={(e) => setSeed(Number(e.target.value))}
              />
            </label>
            <button disabled={running}>
              {running ? "SIMULATING…" : "RUN SIMULATION"}
            </button>
          </form>

          <div className="simulation-picker">
            <span>Активная симуляция</span>
            <select
              value={selectedSimulation}
              onChange={(e) => setSelectedSimulation(e.target.value)}
            >
              <option value="">—</option>
              {simulations.map((simulation) => (
                <option key={simulation.id} value={simulation.id}>
                  {simulation.id} · {simulation.status} · {simulation.ticks} ticks
                </option>
              ))}
            </select>
          </div>
        </article>

        <article className="panel">
          <p className="eyebrow">ACTIVE RUN</p>
          <div className="headline-stat">
            <strong>{selected?.ticks ?? ticks.length}</strong>
            <span>processed ticks</span>
          </div>
          <div className="mini-stats">
            <div><strong>{actors.length}</strong><span>actors</span></div>
            <div><strong>{liveEvents.length}</strong><span>live events</span></div>
            <div><strong>{selected?.status ?? "—"}</strong><span>status</span></div>
          </div>
        </article>
      </section>

      <section className="section">
        <div className="section__heading">
          <div>
            <p className="eyebrow">ACTOR STATE</p>
            <h2>Стратегические акторы</h2>
          </div>
          <span className="muted">{actors.length} entities</span>
        </div>
        <div className="actor-grid">
          {actors.map((actor) => (
            <article className="panel actor-card" key={actor.id}>
              <div className="actor-card__title">
                <div>
                  <span className="actor-id">{actor.id}</span>
                  <h3>{actor.name}</h3>
                </div>
                <span className={`pressure ${actor.domestic_pressure > 0.55 ? "pressure--high" : ""}`}>
                  pressure {pct(actor.domestic_pressure)}
                </span>
              </div>
              <Metric label="Stability" value={actor.stability} />
              <Metric label="Economic capacity" value={actor.economic_capacity} />
            </article>
          ))}
        </div>
      </section>

      <section className="grid grid--bottom">
        <article className="panel">
          <div className="panel__heading">
            <div>
              <p className="eyebrow">TIMELINE</p>
              <h2>Tick history</h2>
            </div>
          </div>
          <div className="timeline">
            {ticks.length === 0 && <p className="muted">Нет загруженных тиков.</p>}
            {[...ticks].reverse().slice(0, 12).map((tick) => (
              <div className="timeline__item" key={tick.tick}>
                <span className="timeline__dot" />
                <div>
                  <strong>TICK {tick.tick}</strong>
                  <p>
                    {Object.keys(tick.state_changes ?? {}).length} changed scopes ·
                    {" "}
                    {Object.keys(tick.phase_log ?? {}).length} phases
                  </p>
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="panel">
          <div className="panel__heading">
            <div>
              <p className="eyebrow">LIVE FEED</p>
              <h2>Realtime events</h2>
            </div>
          </div>
          <div className="feed">
            {liveEvents.length === 0 && (
              <p className="muted">WebSocket feed появится после подключения к run.</p>
            )}
            {liveEvents.map((event, index) => (
              <pre key={index}>{JSON.stringify(event, null, 2)}</pre>
            ))}
          </div>
        </article>
      </section>
    </main>
  );
}
