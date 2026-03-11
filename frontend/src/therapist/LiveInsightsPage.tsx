/**
 * LiveInsightsPage — /therapist/live
 *
 * The most important screen for the hackathon demo.
 * Polls the backend every 3s via useLiveInsights and renders:
 *   - KPI cards (Emotional State, Active Triggers, Engagement, Session Duration)
 *   - Story & Diagnostics Timeline (mock drawing frames)
 *   - Silent Alerts panel (real data from backend)
 *   - Intervention Tools panel (static UI)
 *
 * All historical/static data is mocked. Only Silent Alerts is live.
 */

import { useState, useEffect } from "react";
import { useSearchParams, Link } from "react-router-dom";
import {
  LayoutDashboard,
  Users,
  CalendarDays,
  BarChart2,
  Settings,
  Bell,
  StopCircle,
  Music,
  Palette,
  MessageSquare,
  FileText,
  Download,
  Pencil,
  Sparkles,
  AlertTriangle,
  Zap,
  Clock,
  Smile,
  Activity,
} from "lucide-react";
import { useLiveInsights, type ClinicalAlert } from "./useLiveInsights";

/* ── Mock timeline frames ── */
const MOCK_FRAMES = [
  {
    id: "f4",
    title: 'Drawing Frame 4: "The Helper"',
    time: "14:30 PM",
    label: "ANXIETY",
    labelValue: "2/10 (Low)",
    keyword: '"Robot"',
    tag: "Current",
    tagColor: "#4F46E5",
    image: null,
    isCurrent: true,
  },
  {
    id: "f3",
    title: 'Drawing Frame 3: "Space Travel"',
    time: "14:25 PM",
    label: "INSIGHT",
    labelValue: "Creativity Spike",
    keyword: '"Spaceship"',
    tag: null,
    image: null,
    isCurrent: false,
  },
  {
    id: "f2",
    title: 'Drawing Frame 2: "The Cave"',
    time: "14:15 PM",
    label: "TRIGGER",
    labelValue: "Hesitation",
    keyword: '"Dark"',
    tag: null,
    image: null,
    isCurrent: false,
    triggerColor: "#F97316",
  },
];

/* ── KPI card ── */
interface KpiCardProps {
  label: string;
  value: string;
  sub?: string;
  icon: React.ReactNode;
  accent?: string;
  barWidth?: number; // 0-100
}

function KpiCard({ label, value, sub, icon, accent = "#6366F1", barWidth }: KpiCardProps) {
  return (
    <div
      style={{
        background: "#fff",
        borderRadius: 16,
        border: "1px solid #E2E8F0",
        padding: "1.25rem",
        display: "flex",
        flexDirection: "column",
        gap: 6,
        boxShadow: "0 1px 4px rgba(0,0,0,.05)",
        flex: 1,
        minWidth: 0,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: "0.8125rem", color: "#64748B", fontWeight: 500 }}>{label}</span>
        <div style={{ color: accent }}>{icon}</div>
      </div>
      <div
        style={{
          fontFamily: "var(--font-display)",
          fontSize: "clamp(1.375rem, 2.5vw, 1.75rem)",
          fontWeight: 700,
          color: "#1E1B4B",
          lineHeight: 1.1,
        }}
      >
        {value}
      </div>
      {barWidth !== undefined && (
        <div style={{ height: 6, background: "#F1F5F9", borderRadius: 99, overflow: "hidden" }}>
          <div
            style={{
              height: "100%",
              width: `${barWidth}%`,
              background: `linear-gradient(90deg, ${accent}, ${accent}cc)`,
              borderRadius: 99,
            }}
          />
        </div>
      )}
      {sub && (
        <span style={{ fontSize: "0.75rem", color: "#64748B", display: "flex", alignItems: "center", gap: 4 }}>
          {sub}
        </span>
      )}
    </div>
  );
}

/* ── Alert card ── */
function AlertCard({ alert }: { alert: ClinicalAlert }) {
  const isHigh = alert.risk_level === "high";
  const isMed = alert.risk_level === "medium";

  const accentColor = isHigh ? "#DC2626" : isMed ? "#D97706" : "#4F46E5";
  const bgColor = isHigh ? "#FEF2F2" : isMed ? "#FFFBEB" : "#EEF2FF";
  const borderColor = isHigh ? "#FECACA" : isMed ? "#FDE68A" : "#C7D2FE";

  const iconMap: Record<string, React.ReactNode> = {
    high: <AlertTriangle size={16} color={accentColor} />,
    medium: <Zap size={16} color={accentColor} />,
    low: <Activity size={16} color={accentColor} />,
  };

  return (
    <div
      style={{
        display: "flex",
        gap: 10,
        padding: "0.875rem",
        borderRadius: 12,
        background: bgColor,
        border: `1px solid ${borderColor}`,
        animation: "fade-in-up .3s ease",
      }}
    >
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: 8,
          background: `${accentColor}18`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          marginTop: 2,
        }}
      >
        {iconMap[alert.risk_level] ?? iconMap.low}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 700, fontSize: "0.875rem", color: "#1E1B4B", marginBottom: 2 }}>
          {alert.trigger.length > 60 ? alert.trigger.slice(0, 60) + "…" : alert.trigger}
        </div>
        {alert.child_quote_summary && (
          <div style={{ fontSize: "0.8125rem", color: "#64748B", fontStyle: "italic", marginBottom: 4 }}>
            "{alert.child_quote_summary}"
          </div>
        )}
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <span
            style={{
              fontSize: "0.6875rem",
              fontWeight: 700,
              padding: "2px 8px",
              borderRadius: 99,
              background: accentColor,
              color: "#fff",
              textTransform: "uppercase",
              letterSpacing: "0.06em",
            }}
          >
            {alert.risk_level}
          </span>
          <span
            style={{
              fontSize: "0.6875rem",
              fontWeight: 600,
              padding: "2px 8px",
              borderRadius: 99,
              background: "#E2E8F0",
              color: "#475569",
              textTransform: "capitalize",
            }}
          >
            {alert.primary_emotion}
          </span>
        </div>
        {alert.recommended_strategy && (
          <div style={{ marginTop: 4, fontSize: "0.75rem", color: "#475569", lineHeight: 1.4 }}>
            {alert.recommended_strategy}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Sidebar nav item ── */
function NavItem({
  icon,
  label,
  to,
  active,
}: {
  icon: React.ReactNode;
  label: string;
  to: string;
  active?: boolean;
}) {
  return (
    <Link
      to={to}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "0.625rem 0.875rem",
        borderRadius: 10,
        textDecoration: "none",
        background: active ? "#EEF2FF" : "transparent",
        color: active ? "#4F46E5" : "#64748B",
        fontWeight: active ? 700 : 500,
        fontSize: "0.9375rem",
        transition: "background .15s",
      }}
    >
      {icon}
      {label}
    </Link>
  );
}

/* ── Main page ── */
export default function LiveInsightsPage() {
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get("session_id");
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL as string | undefined;

  const { alerts, status, lastUpdated, childName, sessionStartTime } = useLiveInsights(sessionId, apiBaseUrl);

  // Session duration (calculated from backend start time if available)
  const [sessionDuration, setSessionDuration] = useState(0);
  useEffect(() => {
    const t = setInterval(() => {
      if (sessionStartTime) {
        setSessionDuration(Math.floor((Date.now() - sessionStartTime.getTime()) / 1000));
      } else {
        // Fallback to local ticking if no start time yet, or keep at 0
        setSessionDuration((d) => d + 1);
      }
    }, 1000);
    return () => clearInterval(t);
  }, [sessionStartTime]);
  const minutes = String(Math.floor(sessionDuration / 60)).padStart(2, "0");
  const seconds = String(sessionDuration % 60).padStart(2, "0");

  // Derive aggregate KPIs from latest alerts
  const latestAlert = alerts[alerts.length - 1];
  const hasHighRisk = alerts.some((a) => a.risk_level === "high");
  const emotionalState = latestAlert?.primary_emotion ?? "Calm";
  const triggerCount = alerts.filter((a) => a.trigger).length;

  return (
    <div
      style={{
        display: "flex",
        minHeight: "100vh",
        background: "#F8FAFC",
        fontFamily: "var(--font-body)",
      }}
    >
      {/* ── Sidebar ── */}
      <aside
        style={{
          width: 232,
          flexShrink: 0,
          background: "#fff",
          borderRight: "1px solid #E2E8F0",
          display: "flex",
          flexDirection: "column",
          padding: "1.25rem 0.875rem",
          gap: 4,
        }}
      >
        {/* Logo */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "0 0.5rem 1.25rem",
            borderBottom: "1px solid #F1F5F9",
            marginBottom: "0.5rem",
          }}
        >
          <div
            style={{
              width: 34,
              height: 34,
              borderRadius: "50%",
              background: "linear-gradient(135deg, #FB923C, #F97316)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Sparkles size={17} color="#fff" strokeWidth={2.5} />
          </div>
          <span
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "1.125rem",
              fontWeight: 700,
              color: "#1E1B4B",
            }}
          >
            DoodleSoul
          </span>
        </div>

        <NavItem icon={<LayoutDashboard size={18} />} label="Dashboard" to="/therapist" />
        <NavItem icon={<Users size={18} />} label="Patients" to="/therapist/patients" />
        <NavItem icon={<CalendarDays size={18} />} label="Sessions" to="/therapist/live" active />
        <NavItem icon={<BarChart2 size={18} />} label="Reports" to="/therapist/reports" />
        <NavItem icon={<Settings size={18} />} label="Settings" to="/therapist/settings" />

        {/* Doctor profile at bottom */}
        <div
          style={{
            marginTop: "auto",
            padding: "0.875rem 0.5rem",
            borderTop: "1px solid #F1F5F9",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <div
            style={{
              width: 40,
              height: 40,
              borderRadius: "50%",
              background: "linear-gradient(135deg, #A5B4FC, #818CF8)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#fff",
              fontFamily: "var(--font-display)",
              fontSize: "1rem",
              fontWeight: 700,
            }}
          >
            Dr
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: "0.9rem", color: "#1E1B4B" }}>Dr. Sarah</div>
            <div style={{ fontSize: "0.75rem", color: "#64748B" }}>Child Psychologist</div>
          </div>
        </div>
      </aside>

      {/* ── Main content ── */}
      <main style={{ flex: 1, overflow: "auto" }}>
        {/* Top bar */}
        <header
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "1rem 1.5rem",
            background: "#fff",
            borderBottom: "1px solid #E2E8F0",
            gap: 12,
          }}
        >
          <div>
            <h1
              style={{
                fontFamily: "var(--font-display)",
                fontSize: "1.375rem",
                fontWeight: 700,
                color: "#1E1B4B",
                lineHeight: 1.2,
              }}
            >
              Live Session Insights
            </h1>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginTop: 2,
                fontSize: "0.875rem",
                color: "#64748B",
              }}
            >
              Patient: {childName || "Loading..."} (Age 8)
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  color: "#16A34A",
                  fontWeight: 600,
                }}
              >
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: "#16A34A",
                    display: "inline-block",
                    animation: "gentle-pulse 2s ease-in-out infinite",
                  }}
                />
                Live
              </span>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <button
              type="button"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "0.5rem 1rem",
                borderRadius: 9999,
                border: "1.5px solid #FECACA",
                background: "#FEF2F2",
                color: "#DC2626",
                fontWeight: 700,
                fontSize: "0.875rem",
                cursor: "pointer",
                fontFamily: "var(--font-body)",
              }}
            >
              <StopCircle size={15} />
              End Session
            </button>
            <button
              type="button"
              aria-label="Notifications"
              style={{
                width: 36,
                height: 36,
                borderRadius: "50%",
                border: "1.5px solid #E2E8F0",
                background: "#fff",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "pointer",
                color: "#64748B",
                position: "relative",
              }}
            >
              <Bell size={16} />
              {alerts.length > 0 && (
                <span
                  style={{
                    position: "absolute",
                    top: -3,
                    right: -3,
                    width: 16,
                    height: 16,
                    borderRadius: "50%",
                    background: "#DC2626",
                    color: "#fff",
                    fontSize: "0.6rem",
                    fontWeight: 700,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  {alerts.length}
                </span>
              )}
            </button>
          </div>
        </header>

        <div style={{ padding: "1.5rem" }}>
          {/* ── KPI row ── */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
              gap: 16,
              marginBottom: 24,
            }}
          >
            <KpiCard
              label="Emotional State"
              value={emotionalState.charAt(0).toUpperCase() + emotionalState.slice(1)}
              sub={hasHighRisk ? "High risk detected" : "Stable"}
              icon={<Smile size={20} />}
              accent="#6366F1"
            />
            <KpiCard
              label="Active Triggers"
              value={triggerCount === 0 ? "None" : String(triggerCount)}
              sub={latestAlert ? `Last: ${latestAlert.trigger.slice(0, 30)}…` : "No triggers yet"}
              icon={<AlertTriangle size={20} />}
              accent="#F97316"
            />
            <KpiCard
              label="Engagement"
              value="High"
              sub="Stable for 12m"
              icon={<Zap size={20} />}
              accent="#F97316"
              barWidth={82}
            />
            <KpiCard
              label="Session Duration"
              value={`${minutes}:${seconds}`}
              sub="Scheduled: 45:00"
              icon={<Clock size={20} />}
              accent="#16A34A"
            />
          </div>

          {/* ── Two-column layout ── */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: 20, alignItems: "start" }}>
            {/* ── Story & Diagnostics Timeline ── */}
            <div
              style={{
                background: "#fff",
                borderRadius: 16,
                border: "1px solid #E2E8F0",
                padding: "1.5rem",
                boxShadow: "0 1px 4px rgba(0,0,0,.04)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 20,
                }}
              >
                <h2
                  style={{
                    fontFamily: "var(--font-display)",
                    fontSize: "1rem",
                    fontWeight: 700,
                    color: "#1E1B4B",
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                  }}
                >
                  Story & Diagnostics Timeline
                </h2>
                <button
                  type="button"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    color: "#4F46E5",
                    fontWeight: 600,
                    fontSize: "0.875rem",
                    fontFamily: "var(--font-body)",
                  }}
                >
                  <Download size={14} />
                  Export Data
                </button>
              </div>

              {/* Frames */}
              <div style={{ display: "flex", flexDirection: "column", gap: 0, position: "relative" }}>
                {/* Vertical line */}
                <div
                  style={{
                    position: "absolute",
                    left: 17,
                    top: 0,
                    bottom: 0,
                    width: 2,
                    background: "#E2E8F0",
                    zIndex: 0,
                  }}
                />
                {MOCK_FRAMES.map((frame, idx) => (
                  <div
                    key={frame.id}
                    style={{
                      display: "flex",
                      gap: 16,
                      paddingBottom: idx < MOCK_FRAMES.length - 1 ? 24 : 0,
                      position: "relative",
                      zIndex: 1,
                    }}
                  >
                    {/* Dot */}
                    <div
                      style={{
                        width: 36,
                        height: 36,
                        borderRadius: "50%",
                        background: frame.isCurrent
                          ? "linear-gradient(135deg, #818CF8, #4F46E5)"
                          : "#F1F5F9",
                        border: "3px solid #fff",
                        boxShadow: "0 0 0 2px #E2E8F0",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        flexShrink: 0,
                        color: frame.isCurrent ? "#fff" : "#94A3B8",
                      }}
                    >
                      {frame.isCurrent ? (
                        <Pencil size={14} strokeWidth={2.5} />
                      ) : (
                        <Sparkles size={14} strokeWidth={2} />
                      )}
                    </div>

                    {/* Content */}
                    <div
                      style={{
                        flex: 1,
                        display: "flex",
                        gap: 16,
                        alignItems: "flex-start",
                        padding: "0.625rem 0",
                      }}
                    >
                      {/* Thumbnail placeholder */}
                      <div
                        style={{
                          width: 72,
                          height: 72,
                          borderRadius: 10,
                          background: frame.isCurrent
                            ? "linear-gradient(135deg, #1E1B4B, #312E81)"
                            : frame.triggerColor
                            ? "linear-gradient(135deg, #374151, #111827)"
                            : "linear-gradient(135deg, #EEF2FF, #C7D2FE)",
                          flexShrink: 0,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          overflow: "hidden",
                        }}
                      >
                        {frame.isCurrent ? (
                          <Sparkles size={28} color="#A5B4FC" strokeWidth={1.5} />
                        ) : frame.triggerColor ? (
                          <div
                            style={{
                              width: "100%",
                              height: "100%",
                              background: "radial-gradient(circle at 50% 60%, #9CA3AF 0%, #374151 60%, #111827 100%)",
                            }}
                          />
                        ) : (
                          <Sparkles size={28} color="#818CF8" strokeWidth={1.5} />
                        )}
                      </div>

                      {/* Text */}
                      <div style={{ flex: 1 }}>
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            marginBottom: 4,
                          }}
                        >
                          <span
                            style={{
                              fontWeight: 700,
                              fontSize: "0.9375rem",
                              color: "#1E1B4B",
                            }}
                          >
                            {frame.title}
                          </span>
                          {frame.tag && (
                            <span
                              style={{
                                fontSize: "0.6875rem",
                                fontWeight: 700,
                                padding: "2px 8px",
                                borderRadius: 99,
                                background: frame.tagColor ?? "#4F46E5",
                                color: "#fff",
                                letterSpacing: "0.06em",
                              }}
                            >
                              {frame.tag}
                            </span>
                          )}
                        </div>
                        <div
                          style={{
                            fontSize: "0.8125rem",
                            color: "#64748B",
                            marginBottom: 8,
                          }}
                        >
                          {frame.time}
                        </div>
                        <div style={{ display: "flex", gap: 24 }}>
                          <div>
                            <div
                              style={{
                                fontSize: "0.6875rem",
                                fontWeight: 700,
                                color: "#94A3B8",
                                letterSpacing: "0.08em",
                                textTransform: "uppercase",
                                marginBottom: 2,
                              }}
                            >
                              {frame.label}
                            </div>
                            <div
                              style={{
                                fontSize: "0.875rem",
                                fontWeight: 600,
                                color: frame.triggerColor ?? "#1E1B4B",
                              }}
                            >
                              {frame.labelValue}
                            </div>
                          </div>
                          <div>
                            <div
                              style={{
                                fontSize: "0.6875rem",
                                fontWeight: 700,
                                color: "#94A3B8",
                                letterSpacing: "0.08em",
                                textTransform: "uppercase",
                                marginBottom: 2,
                              }}
                            >
                              KEYWORD
                            </div>
                            <div
                              style={{
                                fontSize: "0.875rem",
                                fontWeight: 700,
                                color: "#4F46E5",
                              }}
                            >
                              {frame.keyword}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* ── Right column ── */}
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {/* Silent Alerts */}
              <div
                style={{
                  background: "#fff",
                  borderRadius: 16,
                  border: "1px solid #E2E8F0",
                  padding: "1.25rem",
                  boxShadow: "0 1px 4px rgba(0,0,0,.04)",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginBottom: 14,
                  }}
                >
                  <h2
                    style={{
                      fontFamily: "var(--font-display)",
                      fontSize: "1rem",
                      fontWeight: 700,
                      color: "#1E1B4B",
                    }}
                  >
                    Silent Alerts
                  </h2>
                  {alerts.length > 0 && (
                    <span
                      style={{
                        width: 22,
                        height: 22,
                        borderRadius: "50%",
                        background: hasHighRisk ? "#DC2626" : "#4F46E5",
                        color: "#fff",
                        fontWeight: 700,
                        fontSize: "0.75rem",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                      }}
                    >
                      {alerts.length}
                    </span>
                  )}
                </div>

                {/* Status indicator */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    marginBottom: 12,
                    fontSize: "0.75rem",
                    color: "#64748B",
                  }}
                >
                  <div
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: "50%",
                      background: status === "ok" ? "#16A34A" : status === "error" ? "#DC2626" : "#F97316",
                      animation: "gentle-pulse 2s ease-in-out infinite",
                    }}
                  />
                  {status === "loading" && "Connecting…"}
                  {status === "ok" && `Live · updated ${lastUpdated?.toLocaleTimeString() ?? ""}`}
                  {status === "error" && "Connection error — retrying"}
                  {status === "idle" && "No session selected"}
                </div>

                {/* Alerts list */}
                {alerts.length === 0 ? (
                  <div
                    style={{
                      padding: "1.5rem",
                      textAlign: "center",
                      color: "#94A3B8",
                      fontSize: "0.875rem",
                      background: "#F8FAFC",
                      borderRadius: 10,
                      border: "1.5px dashed #E2E8F0",
                    }}
                  >
                    {status === "idle"
                      ? "Add ?session_id=YOUR_ID to the URL to see live alerts."
                      : "No alerts detected yet. Session is calm."}
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {alerts.map((alert, i) => (
                      <AlertCard key={i} alert={alert} />
                    ))}
                  </div>
                )}

                {alerts.length > 0 && (
                  <button
                    type="button"
                    style={{
                      width: "100%",
                      marginTop: 10,
                      padding: "0.625rem",
                      borderRadius: 10,
                      border: "1.5px solid #E2E8F0",
                      background: "#F8FAFC",
                      color: "#64748B",
                      fontSize: "0.875rem",
                      fontWeight: 600,
                      cursor: "pointer",
                      fontFamily: "var(--font-body)",
                    }}
                  >
                    View Full Analysis Log
                  </button>
                )}
              </div>

              {/* Intervention Tools */}
              <div
                style={{
                  background: "#fff",
                  borderRadius: 16,
                  border: "1px solid #E2E8F0",
                  padding: "1.25rem",
                  boxShadow: "0 1px 4px rgba(0,0,0,.04)",
                }}
              >
                <h2
                  style={{
                    fontFamily: "var(--font-display)",
                    fontSize: "1rem",
                    fontWeight: 700,
                    color: "#1E1B4B",
                    marginBottom: 14,
                  }}
                >
                  Intervention Tools
                </h2>
                <div
                  style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}
                >
                  {[
                    { icon: <Music size={22} />, label: "Calming Audio", color: "#4F46E5" },
                    { icon: <Palette size={22} />, label: "Color Palette", color: "#4F46E5" },
                    { icon: <MessageSquare size={22} />, label: "Suggest Prompts", color: "#4F46E5" },
                    { icon: <FileText size={22} />, label: "Previous Note", color: "#4F46E5" },
                  ].map((tool) => (
                    <button
                      key={tool.label}
                      type="button"
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        gap: 6,
                        padding: "0.875rem 0.5rem",
                        borderRadius: 12,
                        border: "1.5px solid #E2E8F0",
                        background: "#F8FAFC",
                        cursor: "pointer",
                        color: tool.color,
                        transition: "background .15s",
                        fontFamily: "var(--font-body)",
                      }}
                    >
                      {tool.icon}
                      <span
                        style={{
                          fontSize: "0.8125rem",
                          fontWeight: 600,
                          color: "#1E1B4B",
                          textAlign: "center",
                        }}
                      >
                        {tool.label}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
