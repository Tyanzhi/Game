export type Actor = {
  id: string;
  name: string;
  stability: number;
  economic_capacity: number;
  domestic_pressure: number;
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
