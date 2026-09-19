import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Actor,
  ActorDetail,
  CausalChain,
  Crisis,
  CrisisDetail,
  LiveIntelligenceStatus,
  LiveOutlook,
  LiveWorldEvent,
  Relationship,
  ScenarioTree,
  Simulation,
  StrategicOverview,
  Tick,
  api,
  simulationSocket
} from "./api";

const ACTIONS = [
  ["observe", "Observe"],
  ["diplomatic_outreach", "Diplomatic outreach"],
  ["economic_adjustment", "Economic adjustment"],
  ["defensive_posture", "Defensive posture"],
  ["public_statement", "Public statement"]
] as const;

function pct(value = 0) {
  return `${Math.round(value * 100)}%`;
}

function signed(value = 0) {
  const number = Math.round(value * 100);
  return number > 0 ? `+${number}` : String(number);
}

function project(latitude: number, longitude: number) {
  return {
    x: ((longitude + 180) / 360) * 1000,
    y: ((90 - latitude) / 180) * 500
  };
}

function Metric({ label, value = 0 }: { label: string; value?: number }) {
  return (
    <div className="metric">
      <div className="metric__top"><span>{label}</span><strong>{pct(value)}</strong></div>
      <div className="bar"><span style={{ width: pct(value) }} /></div>
    </div>
  );
}

function relationStrength(row: Relationship) {
  return Math.max(Math.abs(row.diplomatic), Math.abs(row.economic), Math.abs(row.military));
}

function WorldMap({
  actors,
  relationships,
  crises,
  selectedActor,
  selectedCrisis,
  onActor,
  onCrisis
}: {
  actors: Actor[];
  relationships: Relationship[];
  crises: Crisis[];
  selectedActor: string;
  selectedCrisis: string;
  onActor: (id: string) => void;
  onCrisis: (id: string) => void;
}) {
  const points = new Map(
    actors
      .filter((actor) => actor.geography)
      .map((actor) => [actor.id, project(actor.geography!.latitude, actor.geography!.longitude)])
  );

  const links = relationships
    .filter((row) => points.has(row.source) && points.has(row.target))
    .filter((row) => relationStrength(row) > 0.15)
    .slice(0, 100);

  return (
    <div className="world-map">
      <svg viewBox="0 0 1000 500" role="img" aria-label="Geographic strategic map">
        <defs>
          <radialGradient id="oceanGlow">
            <stop offset="0%" stopColor="rgba(41,98,170,.15)" />
            <stop offset="100%" stopColor="rgba(4,8,18,0)" />
          </radialGradient>
        </defs>
        <rect width="1000" height="500" fill="url(#oceanGlow)" />
        <g className="graticule">
          {[100,200,300,400,500,600,700,800,900].map((x) => <line key={`x${x}`} x1={x} x2={x} y1="0" y2="500" />)}
          {[100,200,300,400].map((y) => <line key={`y${y}`} x1="0" x2="1000" y1={y} y2={y} />)}
        </g>
        <g className="continents">
          <path d="M70 105 L145 70 220 85 260 125 235 175 185 190 160 235 110 210 90 160 Z" />
          <path d="M230 225 L275 245 300 300 290 385 250 440 220 370 205 300 Z" />
          <path d="M425 95 L500 75 560 90 620 75 705 100 770 120 835 155 800 205 735 215 685 195 620 225 570 190 520 205 485 170 445 170 Z" />
          <path d="M485 205 L555 210 595 270 575 350 525 390 485 330 460 260 Z" />
          <path d="M795 330 L850 315 900 345 885 395 825 405 790 370 Z" />
        </g>

        {links.map((row, index) => {
          const a = points.get(row.source)!;
          const b = points.get(row.target)!;
          const hostile = row.diplomatic < -0.25 || row.military > 0.55;
          return (
            <line
              key={`${row.source}-${row.target}-${index}`}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              className={hostile ? "geo-link geo-link--hostile" : "geo-link"}
              strokeWidth={0.7 + relationStrength(row) * 1.7}
            />
          );
        })}

        {crises.map((crisis) => {
          const participantPoints = crisis.participants.map((id) => points.get(id)).filter(Boolean) as Array<{x:number;y:number}>;
          if (!participantPoints.length) return null;
          const x = participantPoints.reduce((sum, point) => sum + point.x, 0) / participantPoints.length;
          const y = participantPoints.reduce((sum, point) => sum + point.y, 0) / participantPoints.length;
          const active = selectedCrisis === crisis.id;
          return (
            <g key={crisis.id} className={active ? "crisis-zone crisis-zone--active" : "crisis-zone"} onClick={() => onCrisis(crisis.id)}>
              <circle cx={x} cy={y} r={18 + crisis.intensity * 30} />
              <circle cx={x} cy={y} r={5 + crisis.intensity * 6} className="crisis-zone__core" />
            </g>
          );
        })}

        {actors.map((actor) => {
          if (!actor.geography) return null;
          const point = points.get(actor.id)!;
          const active = actor.id === selectedActor;
          return (
            <g key={actor.id} className={active ? "geo-actor geo-actor--active" : "geo-actor"} onClick={() => onActor(actor.id)}>
              <circle cx={point.x} cy={point.y} r={active ? 11 : 8} />
              <text x={point.x} y={point.y + 22} textAnchor="middle">{actor.name || actor.id}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function ScenarioPanel({ tree }: { tree: ScenarioTree | null }) {
  if (!tree) return <p className="muted">No scenario tree loaded.</p>;
  const leaves = tree.nodes.filter((node) => node.depth === tree.depth);
  const groups = ["escalation", "continuity", "deescalation"].map((label) => ({
    label,
    probability: leaves
      .filter((node) => node.label === label)
      .reduce((sum, node) => sum + node.probability, 0)
  }));
  return (
    <>
      <div className="scenario-summary">
        <div><span>expected stability</span><strong>{pct(tree.expected_stability)}</strong></div>
        <div><span>escalation</span><strong>{pct(tree.escalation_probability)}</strong></div>
        <div><span>leaves</span><strong>{tree.leaf_count}</strong></div>
      </div>
      <div className="scenario-bars">
        {groups.map((item) => (
          <div key={item.label}>
            <span>{item.label}</span>
            <div><i style={{ width: pct(item.probability) }} /></div>
            <strong>{pct(item.probability)}</strong>
          </div>
        ))}
      </div>
    </>
  );
}

function CausalPanel({ chain }: { chain: CausalChain | null }) {
  const effects = (chain?.nodes ?? [])
    .filter((node) => node.kind === "effect")
    .slice(-12)
    .reverse();
  return (
    <div className="causal-list">
      {effects.map((node, index) => (
        <div className="causal-step" key={String(node.id ?? index)}>
          <span>T{String(node.tick ?? "—")}</span>
          <strong>{String(node.label ?? "effect")}</strong>
          <em>{typeof node.delta === "number" ? signed(node.delta as number) : "—"}</em>
          <small>{String(node.mechanism ?? "direct")}</small>
        </div>
      ))}
      {!effects.length && <p className="muted">No causal effects recorded yet.</p>}
    </div>
  );
}

export default function App() {
  const [simulations, setSimulations] = useState<Simulation[]>([]);
  const [ticks, setTicks] = useState<Tick[]>([]);
  const [overview, setOverview] = useState<StrategicOverview | null>(null);
  const [actorDetail, setActorDetail] = useState<ActorDetail | null>(null);
  const [crisisDetail, setCrisisDetail] = useState<CrisisDetail | null>(null);
  const [scenarioTree, setScenarioTree] = useState<ScenarioTree | null>(null);
  const [causalChain, setCausalChain] = useState<CausalChain | null>(null);
  const [selectedSimulation, setSelectedSimulation] = useState("");
  const [selectedActor, setSelectedActor] = useState("");
  const [selectedCrisis, setSelectedCrisis] = useState("");
  const [engineStatus, setEngineStatus] = useState("connecting");
  const [runTicks, setRunTicks] = useState(5);
  const [seed, setSeed] = useState(42);
  const [running, setRunning] = useState(false);
  const [liveEvents, setLiveEvents] = useState<unknown[]>([]);
  const [error, setError] = useState("");
  const [actionType, setActionType] = useState("diplomatic_outreach");
  const [actionTarget, setActionTarget] = useState("");
  const [actionBusy, setActionBusy] = useState(false);
  const [actionResult, setActionResult] = useState("");
  const [actionPoints, setActionPoints] = useState(2);
  const [liveStatus, setLiveStatus] = useState<LiveIntelligenceStatus | null>(null);
  const [worldEvents, setWorldEvents] = useState<LiveWorldEvent[]>([]);
  const [liveOutlook, setLiveOutlook] = useState<LiveOutlook | null>(null);
  const [liveBusy, setLiveBusy] = useState(false);

  async function refreshBase() {
    try {
      const [health, simulationRows] = await Promise.all([api.health(), api.simulations()]);
      setEngineStatus(health.status);
      setSimulations(simulationRows);
      if (health.live_intelligence) setLiveStatus(health.live_intelligence);
      if (!selectedSimulation && simulationRows[0]) setSelectedSimulation(simulationRows[0].id);
    } catch (err) {
      setEngineStatus("offline");
      setError(err instanceof Error ? err.message : "API unavailable");
    }
  }

  async function refreshLive() {
    const [status, events, outlook] = await Promise.all([
      api.liveStatus(),
      api.liveEvents(20),
      api.liveOutlook()
    ]);
    setLiveStatus(status);
    setWorldEvents(events);
    setLiveOutlook(outlook);
  }

  async function refreshSimulation(simulationId: string) {
    const [tickRows, strategic, chain] = await Promise.all([
      api.ticks(simulationId),
      api.strategicOverview(simulationId),
      api.causalChain(simulationId, 160)
    ]);
    setTicks(tickRows);
    setOverview(strategic);
    setCausalChain(chain);
    if (!selectedActor && strategic.actors[0]) setSelectedActor(strategic.actors[0].id);
  }

  useEffect(() => {
    refreshBase();
    refreshLive().catch(() => undefined);
    const baseTimer = window.setInterval(refreshBase, 10000);
    const liveTimer = window.setInterval(() => refreshLive().catch(() => undefined), 60000);
    return () => {
      window.clearInterval(baseTimer);
      window.clearInterval(liveTimer);
    };
  }, []);

  useEffect(() => {
    if (!selectedSimulation) return;
    refreshSimulation(selectedSimulation).catch((err) =>
      setError(err instanceof Error ? err.message : "Failed to load strategic state")
    );
    const socket = simulationSocket(selectedSimulation, (payload) => {
      setLiveEvents((items) => [payload, ...items].slice(0, 30));
      if (typeof payload === "object" && payload !== null && "type" in payload) {
        const type = (payload as {type?: string}).type;
        if (type === "tick_completed") refreshSimulation(selectedSimulation).catch(() => undefined);
      }
    });
    return () => socket?.close();
  }, [selectedSimulation]);

  useEffect(() => {
    if (!selectedSimulation || !selectedActor) return;
    Promise.all([
      api.actorDetail(selectedSimulation, selectedActor),
      api.scenarioTree(selectedSimulation, selectedActor, 3, 3)
    ])
      .then(([detail, tree]) => {
        setActorDetail(detail);
        setScenarioTree(tree);
        const fallbackTarget = detail.relationships
          .map((row) => row.source === selectedActor ? row.target : row.source)
          .find((id) => id !== selectedActor);
        if (fallbackTarget) setActionTarget(fallbackTarget);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Actor detail failed"));
  }, [selectedSimulation, selectedActor]);

  useEffect(() => {
    if (!selectedSimulation || !selectedCrisis) {
      setCrisisDetail(null);
      return;
    }
    api.crisisDetail(selectedSimulation, selectedCrisis)
      .then(setCrisisDetail)
      .catch((err) => setError(err instanceof Error ? err.message : "Crisis detail failed"));
  }, [selectedSimulation, selectedCrisis]);

  const actors = overview?.actors ?? [];
  const actor = actors.find((item) => item.id === selectedActor) ?? actors[0];
  const decision = overview?.decisions.find((item) => item.actor_id === actor?.id);
  const forecast = overview?.forecasts.find((item) => item.target === `${actor?.id}:stability`);
  const selected = simulations.find((item) => item.id === selectedSimulation);

  const actionTargets = useMemo(
    () => actors.filter((item) => item.id !== actor?.id),
    [actors, actor?.id]
  );

  async function runWorld(event: FormEvent) {
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

  async function submitAction(event: FormEvent) {
    event.preventDefault();
    if (!selectedSimulation || !actor) return;
    setActionBusy(true);
    setActionResult("");
    try {
      const result = await api.playTurn(selectedSimulation, {
        actor_id: actor.id,
        action_type: actionType,
        target_actor_id: actionTarget || undefined,
        seed,
        action_points: actionPoints
      });
      setActionResult(
        `turn completed · spent ${result.action_points_spent} AP · AI responded`
      );
      setActionPoints(2);
      setSelectedSimulation(result.simulation_id);
      setOverview(result.overview);
      await refreshBase();
      await refreshSimulation(result.simulation_id);
      setActorDetail(await api.actorDetail(result.simulation_id, actor.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Turn failed");
    } finally {
      setActionBusy(false);
    }
  }

  async function syncLiveNow() {
    setLiveBusy(true);
    setError("");
    try {
      const status = await api.runLiveNow();
      setLiveStatus(status);
      await refreshLive();
      if (status.last_simulation_id) {
        setSelectedSimulation(status.last_simulation_id);
        await refreshSimulation(status.last_simulation_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Live intelligence sync failed");
    } finally {
      setLiveBusy(false);
    }
  }

  return (
    <main className="shell">
      <header className="hero">
        <div>
          <p className="eyebrow">WORLD ENGINE / PLAYER COMMAND</p>
          <h1>World map.<br />Strategic consequences.</h1>
          <p className="sub">География, кризисы, дипломатия, сценарии и причинные цепочки — поверх того же simulation core.</p>
        </div>
        <div className={`status status--${engineStatus === "ok" ? "ok" : "bad"}`}><span />API {engineStatus}</div>
      </header>

      {error && <div className="alert">{error}</div>}

      <section className="command-grid">
        <article className="panel">
          <p className="eyebrow">WORLD CONTROL</p>
          <form className="controls" onSubmit={runWorld}>
            <label>Тики<input type="number" min={1} max={120} value={runTicks} onChange={(e) => setRunTicks(Number(e.target.value))} /></label>
            <label>Seed<input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} /></label>
            <button disabled={running}>{running ? "SIMULATING…" : "RUN WORLD"}</button>
          </form>
          <div className="simulation-picker">
            <span>Simulation</span>
            <select value={selectedSimulation} onChange={(e) => setSelectedSimulation(e.target.value)}>
              <option value="">—</option>
              {simulations.map((item) => <option key={item.id} value={item.id}>{item.id} · {item.status}</option>)}
            </select>
          </div>
        </article>
        <article className="panel telemetry">
          <div><span>TICK</span><strong>{overview?.tick ?? selected?.ticks ?? 0}</strong></div>
          <div><span>ACTORS</span><strong>{actors.length}</strong></div>
          <div><span>CRISES</span><strong>{overview?.active_crises.length ?? 0}</strong></div>
          <div><span>EFFECTS</span><strong>{causalChain?.effect_count ?? 0}</strong></div>
        </article>
      </section>

      <section className="world-layout">
        <article className="panel map-panel">
          <div className="panel__heading">
            <div><p className="eyebrow">GEOGRAPHIC LAYER</p><h2>World strategic map</h2></div>
            <span className="muted">click actor / crisis zone</span>
          </div>
          <WorldMap
            actors={actors}
            relationships={overview?.relationships ?? []}
            crises={overview?.active_crises ?? []}
            selectedActor={actor?.id ?? ""}
            selectedCrisis={selectedCrisis}
            onActor={setSelectedActor}
            onCrisis={setSelectedCrisis}
          />
        </article>

        <aside className="stack">
          <article className="panel actor-focus">
            <p className="eyebrow">SELECTED ACTOR</p>
            <div className="focus-title">
              <div><span>{actor?.geography?.region ?? actor?.id ?? "—"}</span><h2>{actor?.name ?? "No actor"}</h2></div>
              <b>{decision?.selected_action ?? "—"}</b>
            </div>
            {actor && <>
              <Metric label="Stability" value={actor.stability} />
              <Metric label="Economy" value={actor.economic_capacity} />
              <Metric label="Security" value={actor.security_capacity} />
              <Metric label="Diplomacy" value={actor.diplomatic_capacity} />
              <Metric label="Information" value={actor.information_quality} />
            </>}
            <div className="focus-meta">
              <span>pressure <strong>{pct(actor?.domestic_pressure)}</strong></span>
              <span>decision confidence <strong>{pct(decision?.confidence)}</strong></span>
              <span>memory edges <strong>{Object.keys(actorDetail?.strategic_memory ?? {}).length}</strong></span>
            </div>
          </article>

          <article className="panel decision-panel">
            <div className="panel__heading">
              <div><p className="eyebrow">TURN MODE</p><h2>Player command</h2></div>
              <span className="ap-badge">{actionPoints} AP</span>
            </div>
            <form onSubmit={submitAction}>
              <label>Action<select value={actionType} onChange={(e) => setActionType(e.target.value)}>{ACTIONS.map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              <label>Target<select value={actionTarget} onChange={(e) => setActionTarget(e.target.value)}><option value="">No target</option>{actionTargets.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
              <button disabled={actionBusy || !actor}>{actionBusy ? "RESOLVING TURN…" : "COMMIT TURN"}</button>
            </form>
            <p className="muted turn-note">Your action resolves first; AI controls every other actor in the same turn.</p>
            {actionResult && <p className="action-result">{actionResult}</p>}
          </article>
        </aside>
      </section>

      <section className="live-intelligence panel">
        <div className="panel__heading">
          <div>
            <p className="eyebrow">LIVE WORLD INTELLIGENCE</p>
            <h2>Real events → simulation → outlook</h2>
          </div>
          <button className="secondary-action" type="button" onClick={syncLiveNow} disabled={liveBusy}>
            {liveBusy ? "SYNCING…" : "SYNC NOW"}
          </button>
        </div>
        <div className="live-kpis">
          <div><span>monitor</span><strong>{liveStatus?.running ? "RUNNING" : "IDLE"}</strong></div>
          <div><span>new events</span><strong>{liveStatus?.last_new_events ?? 0}</strong></div>
          <div><span>normalized</span><strong>{liveStatus?.last_normalized_events ?? 0}</strong></div>
          <div><span>live run</span><strong>{liveStatus?.last_simulation_id ? "READY" : "—"}</strong></div>
        </div>
        <div className="live-columns">
          <div>
            <h3>Latest world events</h3>
            <div className="world-event-list">
              {worldEvents.slice(0, 8).map((item) => (
                <div key={item.id}>
                  <span>{item.event_type}</span>
                  <strong>{item.title}</strong>
                  <small>{pct(item.confidence)} confidence · {item.actors.join(" · ") || "unlinked"}</small>
                </div>
              ))}
              {!worldEvents.length && <p className="muted">No ingested live events yet.</p>}
            </div>
          </div>
          <div>
            <h3>Forecasted next events</h3>
            <div className="outlook-list">
              {(liveOutlook?.future_events ?? []).slice(0, 6).map((item, index) => (
                <div key={`${item.parent_crisis_id}-${item.event_type}-${index}`}>
                  <strong>{item.event_type}</strong>
                  <span>{pct(item.probability)} · {item.horizon_ticks} tick horizon</span>
                </div>
              ))}
              {!liveOutlook?.future_events.length && <p className="muted">No crisis-branch forecast yet.</p>}
            </div>
          </div>
          <div>
            <h3>Expected actor steps</h3>
            <div className="outlook-list">
              {(liveOutlook?.next_actor_steps ?? []).slice(0, 6).map((item) => (
                <div key={item.actor_id}>
                  <strong>{item.actor_id} → {item.action}</strong>
                  <span>{pct(item.confidence)} · {item.target_actor_id ?? "self/system"}</span>
                </div>
              ))}
              {!liveOutlook?.next_actor_steps.length && <p className="muted">No live actor forecast yet.</p>}
            </div>
          </div>
        </div>
        {liveStatus?.last_error && <p className="live-error">{liveStatus.last_error}</p>}
      </section>

      <section className="intel-grid">
        <article className="panel">
          <p className="eyebrow">CRISIS DETAIL</p>
          {crisisDetail ? (
            <div className="crisis-detail">
              <h2>{String(crisisDetail.crisis.event_type ?? crisisDetail.crisis_id)}</h2>
              <div className="detail-kpis">
                <div><span>phase</span><strong>{String(crisisDetail.crisis.phase ?? "—")}</strong></div>
                <div><span>intensity</span><strong>{pct(Number(crisisDetail.crisis.intensity ?? 0))}</strong></div>
                <div><span>participants</span><strong>{crisisDetail.participants.length}</strong></div>
              </div>
              <p className="muted">{crisisDetail.participants.map((item) => item.name).join(" · ")}</p>
            </div>
          ) : <p className="muted">Select a crisis zone on the map.</p>}
        </article>

        <article className="panel">
          <p className="eyebrow">SCENARIO COMPARISON</p>
          <ScenarioPanel tree={scenarioTree} />
        </article>

        <article className="panel">
          <p className="eyebrow">FORECAST</p>
          <div className="forecast-number">{pct(forecast?.expected)}</div>
          <p className="muted">stability · horizon {forecast?.horizon ?? "—"} · confidence {pct(forecast?.confidence)}</p>
          <div className="forecast-range"><span>{pct(forecast?.lower)}</span><div><i style={{ left: pct(forecast?.lower), width: pct((forecast?.upper ?? 0) - (forecast?.lower ?? 0)) }} /></div><span>{pct(forecast?.upper)}</span></div>
        </article>
      </section>

      <section className="grid grid--bottom">
        <article className="panel">
          <div className="panel__heading"><div><p className="eyebrow">CAUSAL CHAIN</p><h2>Why the world changed</h2></div></div>
          <CausalPanel chain={causalChain} />
        </article>
        <article className="panel">
          <div className="panel__heading"><div><p className="eyebrow">LIVE FEED</p><h2>Realtime engine events</h2></div></div>
          <div className="feed">{liveEvents.length === 0 && <p className="muted">Waiting for WebSocket events.</p>}{liveEvents.map((event,index) => <pre key={index}>{JSON.stringify(event,null,2)}</pre>)}</div>
        </article>
      </section>

      <section className="panel tick-panel">
        <div className="panel__heading"><div><p className="eyebrow">TIMELINE</p><h2>Tick history</h2></div></div>
        <div className="timeline">{[...ticks].reverse().slice(0,16).map((tick) => <div className="timeline__item" key={tick.tick}><span className="timeline__dot" /><div><strong>TICK {tick.tick}</strong><p>{Object.keys(tick.state_changes ?? {}).length} changed scopes · {Object.keys(tick.phase_log ?? {}).length} phases</p></div></div>)}</div>
      </section>
    </main>
  );
}
