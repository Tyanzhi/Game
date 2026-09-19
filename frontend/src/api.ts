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
  health: () => request<{ status: string; engine: string }>("/health"),
  actors: () => request<Actor[]>("/api/actors"),
  simulations: () => request<Simulation[]>("/api/simulations"),
  ticks: (simulationId: string) =>
    request<Tick[]>(`/api/simulations/${encodeURIComponent(simulationId)}/ticks`),
  strategicOverview: (simulationId: string) =>
    request<StrategicOverview>(
      `/api/simulations/${encodeURIComponent(simulationId)}/strategic-overview`
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
