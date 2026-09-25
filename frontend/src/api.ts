export type Actor = {
  id: string;
  name: string;
  actor_type?: string;
  stability: number;
  economic_capacity: number;
  diplomatic_capacity?: number;
  security_capacity?: number;
  domestic_pressure: number;
  information_quality?: number;
  energy_security?: number;
  trade_resilience?: number;
  geography?: {
    latitude: number;
    longitude: number;
    region: string;
    source: string;
  };
};

export type Simulation = {
  id: string;
  status: string;
  ticks: number;
};

export type Tick = {
  tick: number;
  state_changes: Record<string, unknown>;
  phase_log: Record<string, unknown>;
  created_at?: string | null;
  explanation?: TickExplanation | null;
};

export type TickExplanation = {
  version: string;
  simulation_id: string;
  tick: number;
  summary: string;
  changes: Array<{ text: string; causes?: string[] }>;
  model_events?: Array<{ event_id: string; description: string }>;
  causal_chains?: Array<{ effect_id: string; text: string }>;
  observed_data: Array<{
    event_id: string; description: string; status: string; confidence: number;
    source_urls: string[]; timestamp: string;
  }>;
  actor_decisions: Array<{
    decision_id: string; text: string; confidence?: number;
    options?: Array<{ action?: string; expected_utility?: number; risk?: number; selected?: boolean; rule_matched?: boolean }>;
    information_state?: Record<string, unknown>;
  }>;
  actions: Array<{ actor_id: string; status: string; effects?: Record<string, unknown> }>;
  why_it_happened: string[];
  forecasts: Array<{ text: string; drivers?: string[]; model_version?: string;
    comparison?: Array<{ text: string }>; comparison_note?: string; sensitivity_text?: string[]; change_explanation?: string[] }>;
  alternative_scenarios: Array<{ actor_id: string; results: unknown; text?: string[] }>;
  key_uncertainties: string[];
};

export type Relationship = {
  source: string;
  target: string;
  diplomatic: number;
  economic: number;
  military: number;
  trade: number;
  energy: number;
};

export type Crisis = {
  id: string;
  event_type?: string;
  phase?: string;
  intensity: number;
  participants: string[];
  duration: number;
  escalation: number;
  contagion: number;
  uncertainty: number;
};

export type Decision = {
  actor_id: string;
  selected_action: string;
  confidence: number;
  reasoning_factors: string[];
  information_state: Record<string, unknown>;
};

export type Forecast = {
  target: string;
  tick: number;
  horizon: number;
  expected: number;
  lower: number;
  upper: number;
  confidence: number;
  drivers: Record<string, unknown>;
};

export type StrategicOverview = {
  simulation_id: string;
  tick: number;
  state_hash?: string | null;
  actors: Actor[];
  relationships: Relationship[];
  markets: Record<string, number>;
  active_crises: Crisis[];
  coalitions: Array<Record<string, unknown>>;
  brinkmanship: Array<Record<string, unknown>>;
  bargaining: Array<Record<string, unknown>>;
  decisions: Decision[];
  forecasts: Forecast[];
  forecast_calibration: Record<string, unknown>;
  strategic_memory_edges: number;
  belief_edges: number;
  pending_delayed_effects: number;
  forecast_model?: string | null;
};

export type ActorDetail = {
  simulation_id: string;
  actor: Actor & Record<string, unknown>;
  relationships: Relationship[];
  active_crises: Array<Record<string, unknown>>;
  latest_decisions: Array<Record<string, unknown>>;
  beliefs: Record<string, unknown>;
  strategic_memory: Record<string, unknown>;
};

export type CrisisDetail = {
  simulation_id: string;
  crisis_id: string;
  crisis: Record<string, unknown>;
  participants: Array<Actor & Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
  history: Array<Record<string, unknown>>;
};

export type ScenarioTree = {
  actor_id: string;
  depth: number;
  branching: number;
  leaf_count: number;
  expected_stability: number;
  escalation_probability: number;
  nodes: Array<{
    node_id: string;
    depth: number;
    probability: number;
    stability: number;
    market_stress: number;
    crisis_intensity: number;
    label: string;
    parent_id?: string | null;
  }>;
};

export type CausalChain = {
  simulation_id: string;
  effect_count: number;
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
};

export type PlayerActionResult = {
  simulation_id: string;
  tick: number;
  decision_id: string;
  action_id: string;
  actor_id: string;
  status: string;
  effects: Record<string, unknown>;
};

export type LiveIntelligenceStatus = {
  running: boolean;
  last_started_at?: string | null;
  last_finished_at?: string | null;
  last_error?: string | null;
  last_simulation_id?: string | null;
  last_raw_events: number;
  last_normalized_events: number;
  last_new_events: number;
  last_duplicates: number;
  source_errors: Record<string, string>;
};

export type LiveWorldEvent = {
  id: string;
  event_type: string;
  title: string;
  description: string;
  timestamp?: string | null;
  confidence: number;
  status: string;
  source_count: number;
  independent_source_count?: number;
  source_quality_mean?: number;
  confidence_model?: string;
  actors: string[];
  source_urls: string[];
};

export type TurnResult = {
  parent_simulation_id: string;
  simulation_id: string;
  controlled_actor_id: string;
  action_points_start: number;
  action_points_spent: number;
  action_points_remaining: number;
  resource_costs: Record<string, number>;
  player_action: PlayerActionResult;
  overview: StrategicOverview;
};

export type LiveOutlook = {
  simulation_id?: string | null;
  status: string;
  tick?: number;
  future_events: Array<{
    parent_crisis_id: string;
    event_type: string;
    participants: string[];
    probability: number;
    confidence: number;
    horizon_ticks: number;
    mechanism: string;
  }>;
  next_actor_steps: Array<{
    actor_id: string;
    action: string;
    target_actor_id?: string | null;
    confidence: number;
    strategic_posture?: string | null;
    crisis_intensity?: number;
    mechanism: string;
  }>;
  forecasts: Forecast[];
};

export type OperationsAlertEvidence = {
  type: string;
  event_id?: string;
  title?: string;
  confidence?: number;
  fact_status?: string;
  source_count?: number;
  independent_source_count?: number;
  source_quality_mean?: number;
  confidence_model?: string;
  source_urls?: string[];
  source?: string;
  actor_id?: string;
  field?: string;
  horizon?: number;
  tick?: number;
};

export type OperationsAlert = {
  id: string;
  kind: string;
  subject: string;
  title: string;
  message: string;
  score: number;
  severity: "critical" | "high" | "medium" | "low";
  actor_ids: string[];
  crisis_id?: string | null;
  metrics: Record<string, unknown>;
  evidence: OperationsAlertEvidence[];
  operator_action: string;
  status: "open" | "acknowledged" | "resolved";
  acknowledged_by?: string | null;
  acknowledged_at?: string | null;
  note?: string | null;
  first_seen_tick?: number | null;
  last_seen_tick?: number | null;
  occurrence_count: number;
  resolved_at?: string | null;
};

export type AlertHistoryItem = {
  id: string;
  simulation_id: string;
  status: "open" | "acknowledged" | "resolved";
  title: string;
  severity: "critical" | "high" | "medium" | "low";
  first_seen_tick: number;
  last_seen_tick: number;
  occurrence_count: number;
  acknowledged_by?: string | null;
  acknowledged_at?: string | null;
  resolved_at?: string | null;
  note?: string | null;
  updated_at?: string | null;
};

export type OperationsCenter = {
  simulation_id: string | null;
  status?: string;
  tick: number;
  posture: "normal" | "watch" | "heightened" | "critical";
  summary: {
    critical: number;
    high: number;
    medium: number;
    low: number;
    open: number;
    acknowledged: number;
    resolved_recent?: number;
    total: number;
  };
  alerts: OperationsAlert[];
  recent_resolved?: AlertHistoryItem[];
  brief: {
    headline: string;
    top_priorities: Array<{ id: string; title: string; severity: string }>;
    recommended_actions: Array<{ alert_id: string; severity: string; action: string }>;
    watch_actors: string[];
    watch_crises: string[];
    forecast_calibration: Record<string, unknown>;
    generated_from_tick: number;
  };
};

export type PredictionCenter = {
  simulation_id: string;
  tick: number;
  horizons: number[];
  actors: Array<{
    actor_id: string;
    actor_name: string;
    current_stability: number;
    crisis_intensity: number;
    horizons: Record<string, {
      expected: number;
      probabilities: Record<string, number>;
      uncertainty: number;
      ensemble: Record<string, number>;
      drivers: string[];
    }>;
    calibration: {
      count: number;
      mean_brier: number | null;
      quality: string;
    };
  }>;
  scenario_matrix: Array<{
    actor_id: string;
    actor_name: string;
    scenarios: Record<string, Record<string, {
      expected: number;
      uncertainty: number;
      probabilities: Record<string, number>;
    }>>;
  }>;
  causal_graph: {
    nodes: Array<{
      id: string;
      kind: string;
      label: string;
      weight: number;
    }>;
    edges: Array<{
      source: string;
      target: string;
      probability: number;
      mechanism: string;
    }>;
  };
  calibration: {
    scored_targets: number;
    mean_brier: number | null;
    quality: string;
  };
  change_since_previous_snapshot: {
    market_stress_delta: number;
    active_crises_delta: number;
    previous_tick: number | null;
  };
  model_version: string;
};

const API_BASE = import.meta.env.VITE_API_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () =>
    request<{ status: string; engine: string; live_intelligence?: LiveIntelligenceStatus }>("/health"),
  actors: () => request<Actor[]>("/api/actors"),
  simulations: () => request<Simulation[]>("/api/simulations"),
  ticks: (simulationId: string) =>
    request<Tick[]>(`/api/simulations/${encodeURIComponent(simulationId)}/ticks`),
  strategicOverview: (simulationId: string) =>
    request<StrategicOverview>(
      `/api/simulations/${encodeURIComponent(simulationId)}/strategic-overview`
    ),
  actorDetail: (simulationId: string, actorId: string) =>
    request<ActorDetail>(
      `/api/simulations/${encodeURIComponent(simulationId)}/actors/${encodeURIComponent(actorId)}`
    ),
  crisisDetail: (simulationId: string, crisisId: string) =>
    request<CrisisDetail>(
      `/api/simulations/${encodeURIComponent(simulationId)}/crises/${encodeURIComponent(crisisId)}`
    ),
  scenarioTree: (simulationId: string, actorId: string, depth = 3, branching = 3) =>
    request<ScenarioTree>(
      `/api/simulations/${encodeURIComponent(simulationId)}/scenario-tree/${encodeURIComponent(actorId)}?depth=${depth}&branching=${branching}`
    ),
  causalChain: (simulationId: string, limit = 120) =>
    request<CausalChain>(
      `/api/simulations/${encodeURIComponent(simulationId)}/causal-chain?limit=${limit}`
    ),
  playerAction: (
    simulationId: string,
    payload: { actor_id: string; action_type: string; target_actor_id?: string; rationale?: string }
  ) =>
    request<PlayerActionResult>(
      `/api/simulations/${encodeURIComponent(simulationId)}/player-actions`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }
    ),
  playTurn: (
    simulationId: string,
    payload: {
      actor_id: string;
      action_type: string;
      target_actor_id?: string;
      seed: number;
      action_points?: number;
    }
  ) =>
    request<TurnResult>(
      `/api/simulations/${encodeURIComponent(simulationId)}/turns`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }
    ),
  liveStatus: () =>
    request<LiveIntelligenceStatus>("/api/live-intelligence/status"),
  liveEvents: (limit = 30) =>
    request<LiveWorldEvent[]>(`/api/live-intelligence/events?limit=${limit}`),
  liveOutlook: () =>
    request<LiveOutlook>("/api/live-intelligence/outlook"),
  predictionCenter: (simulationId: string) =>
    request<PredictionCenter>(
      `/api/simulations/${encodeURIComponent(simulationId)}/prediction-center`
    ),
  livePredictionCenter: () =>
    request<PredictionCenter | {
      simulation_id: null;
      status: string;
      horizons: number[];
      actors: [];
      scenario_matrix: [];
      causal_graph: { nodes: []; edges: [] };
      calibration: { scored_targets: number; mean_brier: null; quality: string };
    }>("/api/live-intelligence/prediction-center"),
  operationsCenter: (simulationId: string) =>
    request<OperationsCenter>(
      `/api/simulations/${encodeURIComponent(simulationId)}/operations-center`
    ),
  liveOperationsCenter: () =>
    request<OperationsCenter>("/api/live-intelligence/operations-center"),
  alertHistory: (
    simulationId: string,
    status?: "open" | "acknowledged" | "resolved",
    limit = 100
  ) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (status) query.set("status", status);
    return request<AlertHistoryItem[]>(
      `/api/simulations/${encodeURIComponent(simulationId)}/alerts/history?${query.toString()}`
    );
  },
  liveAlertHistory: (
    status?: "open" | "acknowledged" | "resolved",
    limit = 100
  ) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (status) query.set("status", status);
    return request<AlertHistoryItem[]>(
      `/api/live-intelligence/alerts/history?${query.toString()}`
    );
  },
  setAlertState: (
    simulationId: string,
    alertId: string,
    payload: {
      status: "open" | "acknowledged";
      acknowledged_by?: string;
      note?: string;
    }
  ) =>
    request<{
      alert_id: string;
      simulation_id: string;
      status: string;
      acknowledged_by?: string | null;
      acknowledged_at?: string | null;
      first_seen_tick: number;
      last_seen_tick: number;
      occurrence_count: number;
      note?: string | null;
    }>(
      `/api/simulations/${encodeURIComponent(simulationId)}/alerts/${encodeURIComponent(alertId)}/state`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }
    ),
  runLiveNow: () =>
    request<LiveIntelligenceStatus>(
      "/api/live-intelligence/run-now",
      { method: "POST" }
    ),
  runSimulation: (ticks: number, seed: number) =>
    request<{ simulation_id: string; ticks: number }>(
      `/api/simulations?ticks=${ticks}&seed=${seed}`,
      { method: "POST" }
    )
};

export function simulationSocket(
  simulationId: string,
  onMessage: (payload: unknown) => void
): WebSocket | null {
  if (!simulationId) return null;
  const explicit = import.meta.env.VITE_WS_URL as string | undefined;
  const base = explicit ?? (
    window.location.protocol === "https:"
      ? `wss://${window.location.host}`
      : `ws://${window.location.host}`
  );
  const socket = new WebSocket(
    `${base}/ws/simulation/${encodeURIComponent(simulationId)}`
  );
  socket.onmessage = (event) => {
    try {
      onMessage(JSON.parse(event.data));
    } catch {
      onMessage(event.data);
    }
  };
  return socket;
}
