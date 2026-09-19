import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Actor,
  Relationship,
  Simulation,
  StrategicOverview,
  Tick,
  api,
  simulationSocket
} from "./api";

function pct(value = 0) {
  return `${Math.round(value * 100)}%`;
}

function signed(value = 0) {
  const number = Math.round(value * 100);
  return number > 0 ? `+${number}` : String(number);
}

function Metric({ label, value = 0 }: { label: string; value?: number }) {
  return (
    <div className="metric">
      <div className="metric__top">
        <span>{label}</span>
        <strong>{pct(value)}</strong>
      </div>
      <div className="bar"><span style={{ width: pct(value) }} /></div>
    </div>
  );
}

function relationshipStrength(row: Relationship) {
  return Math.max(
    Math.abs(row.diplomatic || 0),
    Math.abs(row.economic || 0),
    Math.abs(row.military || 0)
  );
}

function StrategicMap({
  actors,
  relationships,
  selectedActor,
  onSelect
}: {
  actors: Actor[];
  relationships: Relationship[];
  selectedActor: string;
  onSelect: (id: string) => void;
}) {
  const width = 720;
  const height = 440;
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.36;
  const positions = new Map(
    actors.map((actor, index) => {
      const angle = (Math.PI * 2 * index) / Math.max(1, actors.length) - Math.PI / 2;
      return [
        actor.id,
        { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius }
      ] as const;
    })
  );

  const visibleRelationships = relationships
    .filter((row) => positions.has(row.source) && positions.has(row.target))
    .filter((row) => relationshipStrength(row) >= 0.08)
    .slice(0, 80);

  return (
    <div className="strategic-map">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Strategic actor network">
        <defs>
          <radialGradient id="mapGlow">
            <stop offset="0%" stopColor="rgba(62,136,255,.18)" />
            <stop offset="100%" stopColor="rgba(5,10,18,0)" />
          </radialGradient>
        </defs>
        <circle cx={cx} cy={cy} r={190} fill="url(#mapGlow)" />
        {visibleRelationships.map((row, index) => {
          const a = positions.get(row.source)!;
          const b = positions.get(row.target)!;
          const strength = relationshipStrength(row);
          const hostile = row.diplomatic < -0.2 || row.military > 0.5;
          return (
            <line
              key={`${row.source}-${row.target}-${index}`}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              className={hostile ? "link link--hostile" : "link"}
              strokeWidth={0.6 + strength * 2.2}
              opacity={0.2 + strength * 0.55}
            />
          );
        })}
        {actors.map((actor) => {
          const point = positions.get(actor.id)!;
          const active = actor.id === selectedActor;
          return (
            <g
              key={actor.id}
              className={active ? "map-node map-node--active" : "map-node"}
              onClick={() => onSelect(actor.id)}
              role="button"
              tabIndex={0}
            >
              <circle
                cx={point.x}
                cy={point.y}
                r={active ? 27 : 22}
                className="map-node__ring"
              />
              <circle
                cx={point.x}
                cy={point.y}
                r={8 + actor.stability * 7}
                className="map-node__core"
              />
              <text x={point.x} y={point.y + 39} textAnchor="middle">
                {actor.name || actor.id}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export default function App() {
  const [simulations, setSimulations] = useState<Simulation[]>([]);
  const [ticks, setTicks] = useState<Tick[]>([]);
  const [overview, setOverview] = useState<StrategicOverview | null>(null);
  const [selectedSimulation, setSelectedSimulation] = useState("");
  const [selectedActor, setSelectedActor] = useState("");
  const [engineStatus, setEngineStatus] = useState("connecting");
  const [runTicks, setRunTicks] = useState(5);
  const [seed, setSeed] = useState(42);
  const [running, setRunning] = useState(false);
  const [liveEvents, setLiveEvents] = useState<unknown[]>([]);
  const [error, setError] = useState("");

  async function refreshBase() {
    try {
      const [health, simulationRows] = await Promise.all([
        api.health(),
        api.simulations()
      ]);
      setEngineStatus(health.status);
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

  async function refreshSimulation(simulationId: string) {
    const [tickRows, strategic] = await Promise.all([
      api.ticks(simulationId),
      api.strategicOverview(simulationId)
    ]);
    setTicks(tickRows);
    setOverview(strategic);
    if (!selectedActor && strategic.actors[0]) {
      setSelectedActor(strategic.actors[0].id);
    }
  }

  useEffect(() => {
    refreshBase();
    const timer = window.setInterval(refreshBase, 10000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!selectedSimulation) {
      setTicks([]);
      setOverview(null);
      return;
    }
    refreshSimulation(selectedSimulation).catch((err) =>
      setError(err instanceof Error ? err.message : "Failed to load strategic state")
    );

    const socket = simulationSocket(selectedSimulation, (payload) => {
      setLiveEvents((items) => [payload, ...items].slice(0, 30));
      if (
        typeof payload === "object" &&
        payload !== null &&
        "type" in payload &&
        (payload as { type?: string }).type === "tick_completed"
      ) {
        refreshSimulation(selectedSimulation).catch(() => undefined);
      }
    });
    return () => socket?.close();
  }, [selectedSimulation]);

  const selected = useMemo(
    () => simulations.find((item) => item.id === selectedSimulation),
    [simulations, selectedSimulation]
  );

  const actors = overview?.actors ?? [];
  const actor = actors.find((item) => item.id === selectedActor) ?? actors[0];
  const decision = overview?.decisions.find((item) => item.actor_id === actor?.id);
  const forecast = overview?.forecasts.find((item) => item.target === `${actor?.id}:stability`);
  const actorCrises = overview?.active_crises.filter((item) =>
    item.participants.includes(actor?.id ?? "")
  ) ?? [];
  const actorLinks = overview?.relationships
    .filter((row) => row.source === actor?.id || row.target === actor?.id)
    .sort((a, b) => relationshipStrength(b) - relationshipStrength(a))
    .slice(0, 8) ?? [];

  async function submit(event: FormEvent) {
    event.preventDefault();
    setRunning(true);
    setError("");
    try {
      const result = await api.runSimulation(runTicks, seed);
      setSelectedSimulation(result.simulation_id);
      await refreshBase();
      await refreshSimulation(result.simulation_id);
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
          <p className="eyebrow">WORLD ENGINE / STRATEGIC OPERATIONS</p>
          <h1>Command the system.<br />Read the consequences.</h1>
          <p className="sub">
            Живая стратегическая сеть: акторы, кризисы, рынки, прогнозы,
            коалиции и причинные каскады на каждом тике.
          </p>
        </div>
        <div className={`status status--${engineStatus === "ok" ? "ok" : "bad"}`}>
          <span /> API {engineStatus}
        </div>
      </header>

      {error && <div className="alert">{error}</div>}

      <section className="command-grid">
        <article className="panel command-panel">
          <p className="eyebrow">WORLD CONTROL</p>
          <form className="controls" onSubmit={submit}>
            <label>Тики<input type="number" min={1} max={120} value={runTicks} onChange={(e) => setRunTicks(Number(e.target.value))} /></label>
            <label>Seed<input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} /></label>
            <button disabled={running}>{running ? "SIMULATING…" : "RUN WORLD"}</button>
          </form>
          <div className="simulation-picker">
            <span>Simulation</span>
            <select value={selectedSimulation} onChange={(e) => setSelectedSimulation(e.target.value)}>
              <option value="">—</option>
              {simulations.map((item) => (
                <option key={item.id} value={item.id}>{item.id} · {item.status}</option>
              ))}
            </select>
          </div>
        </article>

        <article className="panel telemetry">
          <div><span>TICK</span><strong>{overview?.tick ?? selected?.ticks ?? 0}</strong></div>
          <div><span>ACTORS</span><strong>{actors.length}</strong></div>
          <div><span>CRISES</span><strong>{overview?.active_crises.length ?? 0}</strong></div>
          <div><span>BELIEFS</span><strong>{overview?.belief_edges ?? 0}</strong></div>
        </article>
      </section>

      <section className="operations-layout">
        <article className="panel map-panel">
          <div className="panel__heading">
            <div><p className="eyebrow">STRATEGIC NETWORK</p><h2>Actor topology</h2></div>
            <span className="muted">{overview?.relationships.length ?? 0} directed links</span>
          </div>
          <StrategicMap
            actors={actors}
            relationships={overview?.relationships ?? []}
            selectedActor={actor?.id ?? ""}
            onSelect={setSelectedActor}
          />
          <div className="map-legend">
            <span><i className="legend-line" /> cooperative / neutral</span>
            <span><i className="legend-line legend-line--hostile" /> hostile / military pressure</span>
          </div>
        </article>

        <aside className="stack">
          <article className="panel actor-focus">
            <p className="eyebrow">SELECTED ACTOR</p>
            <div className="focus-title">
              <div><span>{actor?.id ?? "—"}</span><h2>{actor?.name ?? "No actor"}</h2></div>
              <b>{decision?.selected_action ?? "—"}</b>
            </div>
            {actor && (
              <>
                <Metric label="Stability" value={actor.stability} />
                <Metric label="Economy" value={actor.economic_capacity} />
                <Metric label="Security" value={actor.security_capacity} />
                <Metric label="Diplomacy" value={actor.diplomatic_capacity} />
                <Metric label="Information" value={actor.information_quality} />
              </>
            )}
            <div className="focus-meta">
              <span>pressure <strong>{pct(actor?.domestic_pressure)}</strong></span>
              <span>decision confidence <strong>{pct(decision?.confidence)}</strong></span>
              <span>crises <strong>{actorCrises.length}</strong></span>
            </div>
          </article>

          <article className="panel forecast-card">
            <p className="eyebrow">FORECAST</p>
            <div className="forecast-number">{pct(forecast?.expected)}</div>
            <p className="muted">expected stability · horizon {forecast?.horizon ?? "—"}</p>
            <div className="forecast-range">
              <span>{pct(forecast?.lower)}</span>
              <div><i style={{ left: pct(forecast?.lower), width: pct((forecast?.upper ?? 0) - (forecast?.lower ?? 0)) }} /></div>
              <span>{pct(forecast?.upper)}</span>
            </div>
          </article>
        </aside>
      </section>

      <section className="intel-grid">
        <article className="panel">
          <div className="panel__heading"><div><p className="eyebrow">CRISIS LAYER</p><h2>Active crises</h2></div></div>
          <div className="crisis-list">
            {(overview?.active_crises ?? []).slice(0, 8).map((crisis) => (
              <button className="crisis-row" key={crisis.id} onClick={() => crisis.participants[0] && setSelectedActor(crisis.participants[0])}>
                <div><strong>{crisis.event_type ?? crisis.id}</strong><span>{crisis.phase} · {crisis.duration} ticks</span></div>
                <div className="crisis-intensity"><i style={{ width: pct(crisis.intensity) }} /><span>{pct(crisis.intensity)}</span></div>
              </button>
            ))}
            {!overview?.active_crises.length && <p className="muted">No active crises in the current snapshot.</p>}
          </div>
        </article>

        <article className="panel">
          <p className="eyebrow">GLOBAL MARKETS</p>
          <div className="market-grid">
            {Object.entries(overview?.markets ?? {}).map(([key, value]) => (
              <div key={key}><span>{key.replace(/_/g, " ")}</span><strong>{signed(value)}</strong></div>
            ))}
          </div>
          <p className="eyebrow section-gap">COALITIONS</p>
          <div className="coalition-list">
            {(overview?.coalitions ?? []).slice(0, 6).map((item, index) => (
              <div key={index}>
                <strong>{Array.isArray(item.members) ? item.members.join(" · ") : "coalition"}</strong>
                <span>reliability {typeof item.reliability === "number" ? pct(item.reliability) : "—"}</span>
              </div>
            ))}
            {!overview?.coalitions.length && <span className="muted">No multilateral coalition active.</span>}
          </div>
        </article>

        <article className="panel">
          <p className="eyebrow">RELATIONSHIP INTELLIGENCE</p>
          <div className="relationship-list">
            {actorLinks.map((row, index) => {
              const counterpart = row.source === actor?.id ? row.target : row.source;
              return (
                <button key={index} onClick={() => setSelectedActor(counterpart)}>
                  <span>{counterpart}</span>
                  <small>dip {signed(row.diplomatic)} · econ {signed(row.economic)} · mil {signed(row.military)}</small>
                </button>
              );
            })}
          </div>
        </article>
      </section>

      <section className="grid grid--bottom">
        <article className="panel">
          <div className="panel__heading"><div><p className="eyebrow">TIMELINE</p><h2>Causal tick history</h2></div></div>
          <div className="timeline">
            {[...ticks].reverse().slice(0, 12).map((tick) => (
              <div className="timeline__item" key={tick.tick}>
                <span className="timeline__dot" />
                <div><strong>TICK {tick.tick}</strong><p>{Object.keys(tick.state_changes ?? {}).length} changed scopes · {Object.keys(tick.phase_log ?? {}).length} phases</p></div>
              </div>
            ))}
          </div>
        </article>

        <article className="panel">
          <div className="panel__heading"><div><p className="eyebrow">LIVE FEED</p><h2>Realtime engine events</h2></div></div>
          <div className="feed">
            {liveEvents.length === 0 && <p className="muted">Waiting for WebSocket events.</p>}
            {liveEvents.map((event, index) => <pre key={index}>{JSON.stringify(event, null, 2)}</pre>)}
          </div>
        </article>
      </section>
    </main>
  );
}
