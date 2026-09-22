import { useMemo, useState } from "react";
import type { AlertHistoryItem, OperationsAlert, OperationsCenter } from "./api";

const SEVERITIES = ["all", "critical", "high", "medium", "low"] as const;

function percent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function Evidence({ alert }: { alert: OperationsAlert }) {
  const rows = alert.evidence.slice(0, 3);
  if (!rows.length) return <p className="ops-evidence-empty">No attached evidence.</p>;

  return (
    <div className="ops-evidence">
      {rows.map((item, index) => {
        const urls = Array.isArray(item.source_urls)
          ? item.source_urls.filter((value): value is string => typeof value === "string")
          : [];
        return (
          <div key={`${alert.id}-evidence-${index}`}>
            <span>{String(item.type ?? "evidence").replace(/_/g, " ")}</span>
            <strong>{String(item.title ?? item.source ?? item.event_id ?? "model state")}</strong>
            <small>
              {typeof item.confidence === "number" ? `${percent(item.confidence)} confidence · ` : ""}
              {typeof item.source_count === "number" ? `${item.source_count} sources` : ""}
            </small>
            {urls.slice(0, 2).map((url) => (
              <a key={url} href={url} target="_blank" rel="noreferrer">
                source
              </a>
            ))}
          </div>
        );
      })}
    </div>
  );
}

export default function OperationsCenterPanel({
  center,
  history,
  busyAlertId,
  onAlertState,
  onActor,
  onCrisis
}: {
  center: OperationsCenter | null;
  history: AlertHistoryItem[];
  busyAlertId: string;
  onAlertState: (alert: OperationsAlert, status: "open" | "acknowledged") => void;
  onActor: (actorId: string) => void;
  onCrisis: (crisisId: string) => void;
}) {
  const [severity, setSeverity] = useState<(typeof SEVERITIES)[number]>("all");
  const [expanded, setExpanded] = useState("");

  const alerts = useMemo(
    () => (center?.alerts ?? []).filter((item) => severity === "all" || item.severity === severity),
    [center, severity]
  );

  return (
    <section className={`operations-center panel operations-center--${center?.posture ?? "normal"}`}>
      <div className="panel__heading ops-heading">
        <div>
          <p className="eyebrow">STAGE 7 / ALERT & OPERATIONS CENTER</p>
          <h2>Operational posture · {center?.posture ?? "offline"}</h2>
        </div>
        <div className="ops-posture">
          <span>POSTURE</span>
          <strong>{center?.posture?.toUpperCase() ?? "—"}</strong>
        </div>
      </div>

      {!center ? (
        <p className="muted ops-empty">Select a simulation to load operational alerts.</p>
      ) : (
        <>
          <div className="ops-kpis">
            <div className="ops-kpi ops-kpi--critical"><span>critical</span><strong>{center.summary.critical}</strong></div>
            <div className="ops-kpi ops-kpi--high"><span>high</span><strong>{center.summary.high}</strong></div>
            <div><span>open</span><strong>{center.summary.open}</strong></div>
            <div><span>acknowledged</span><strong>{center.summary.acknowledged}</strong></div>
            <div><span>resolved</span><strong>{center.summary.resolved_recent ?? 0}</strong></div>
          </div>

          <div className="ops-layout">
            <div className="ops-main">
              <div className="ops-toolbar">
                <div>
                  <h3>Alert queue</h3>
                  <span>{center.brief.headline}</span>
                </div>
                <div className="ops-filters">
                  {SEVERITIES.map((item) => (
                    <button
                      type="button"
                      key={item}
                      className={severity === item ? "active" : ""}
                      onClick={() => setSeverity(item)}
                    >
                      {item}
                    </button>
                  ))}
                </div>
              </div>

              <div className="ops-alert-list">
                {alerts.map((alert) => {
                  const isExpanded = expanded === alert.id;
                  return (
                    <article
                      key={alert.id}
                      className={`ops-alert ops-alert--${alert.severity} ops-alert--${alert.status}`}
                    >
                      <div className="ops-alert__top">
                        <div className="ops-alert__identity">
                          <span className="ops-severity">{alert.severity}</span>
                          <span>{alert.kind}</span>
                          <span>T{alert.last_seen_tick ?? center.tick}</span>
                        </div>
                        <strong>{percent(alert.score)}</strong>
                      </div>
                      <h3>{alert.title}</h3>
                      <p>{alert.message}</p>

                      <div className="ops-alert__chips">
                        {alert.actor_ids.map((actorId) => (
                          <button type="button" key={actorId} onClick={() => onActor(actorId)}>
                            actor · {actorId}
                          </button>
                        ))}
                        {alert.crisis_id && (
                          <button type="button" onClick={() => onCrisis(alert.crisis_id!)}>
                            crisis · {alert.crisis_id}
                          </button>
                        )}
                        <span>{alert.status}</span>
                        {alert.occurrence_count > 1 && <span>×{alert.occurrence_count}</span>}
                      </div>

                      <div className="ops-operator-action">
                        <span>operator action</span>
                        <strong>{alert.operator_action}</strong>
                      </div>

                      <div className="ops-alert__actions">
                        <button type="button" onClick={() => setExpanded(isExpanded ? "" : alert.id)}>
                          {isExpanded ? "HIDE EVIDENCE" : "EVIDENCE"}
                        </button>
                        <button
                          type="button"
                          disabled={busyAlertId === alert.id}
                          onClick={() => onAlertState(
                            alert,
                            alert.status === "acknowledged" ? "open" : "acknowledged"
                          )}
                        >
                          {busyAlertId === alert.id
                            ? "UPDATING…"
                            : alert.status === "acknowledged"
                              ? "REOPEN"
                              : "ACKNOWLEDGE"}
                        </button>
                      </div>

                      {isExpanded && <Evidence alert={alert} />}
                    </article>
                  );
                })}
                {!alerts.length && <p className="muted">No alerts match this severity filter.</p>}
              </div>
            </div>

            <aside className="ops-sidebar">
              <div className="ops-brief-block">
                <p className="eyebrow">COMMAND BRIEF</p>
                <h3>Top priorities</h3>
                {center.brief.top_priorities.slice(0, 5).map((item, index) => (
                  <div className="ops-priority" key={item.id}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <div><strong>{item.title}</strong><small>{item.severity}</small></div>
                  </div>
                ))}
              </div>

              <div className="ops-brief-block">
                <h3>Recommended actions</h3>
                {center.brief.recommended_actions.slice(0, 5).map((item) => (
                  <div className="ops-recommendation" key={item.alert_id}>
                    <span>{item.severity}</span>
                    <p>{item.action}</p>
                  </div>
                ))}
              </div>

              <div className="ops-brief-block">
                <h3>Watch actors</h3>
                <div className="ops-watchlist">
                  {center.brief.watch_actors.map((actorId) => (
                    <button type="button" key={actorId} onClick={() => onActor(actorId)}>
                      {actorId}
                    </button>
                  ))}
                  {!center.brief.watch_actors.length && <span className="muted">None</span>}
                </div>
                <h3 className="ops-subheading">Watch crises</h3>
                <div className="ops-watchlist">
                  {center.brief.watch_crises.map((crisisId) => (
                    <button type="button" key={crisisId} onClick={() => onCrisis(crisisId)}>
                      {crisisId}
                    </button>
                  ))}
                  {!center.brief.watch_crises.length && <span className="muted">None</span>}
                </div>
              </div>

              <div className="ops-brief-block">
                <h3>Recently resolved</h3>
                <div className="ops-history">
                  {history.filter((item) => item.status === "resolved").slice(0, 6).map((item) => (
                    <div key={item.id}>
                      <strong>{item.title}</strong>
                      <span>{item.severity} · T{item.last_seen_tick}</span>
                    </div>
                  ))}
                  {!history.some((item) => item.status === "resolved") && (
                    <span className="muted">No resolved alerts yet.</span>
                  )}
                </div>
              </div>
            </aside>
          </div>
        </>
      )}
    </section>
  );
}
