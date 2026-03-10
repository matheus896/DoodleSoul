/**
 * TherapistDashboard — /therapist
 *
 * Overview dashboard with mock session history and patient data.
 * All data is hardcoded for the demo. No database required.
 */

import { Link } from "react-router-dom";
import {
  LayoutDashboard,
  Users,
  CalendarDays,
  BarChart2,
  Settings,
  Sparkles,
  TrendingUp,
  Clock,
  AlertCircle,
  ChevronRight,
  Play,
} from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from "recharts";

/* ── Mock data ── */
const MOCK_PATIENTS = [
  { id: "p1", name: "Leo", age: 8, lastSession: "Today", status: "active", risk: "low" },
  { id: "p2", name: "Maya", age: 6, lastSession: "Yesterday", status: "scheduled", risk: "medium" },
  { id: "p3", name: "Noah", age: 9, lastSession: "3 days ago", status: "completed", risk: "low" },
  { id: "p4", name: "Aria", age: 7, lastSession: "1 week ago", status: "completed", risk: "low" },
];

const MOCK_SESSIONS = [
  { id: "s1", patient: "Leo", date: "Today, 14:00", duration: "32m", status: "active", alerts: 2 },
  { id: "s2", patient: "Maya", date: "Yesterday, 10:00", duration: "45m", status: "completed", alerts: 0 },
  { id: "s3", patient: "Noah", date: "Mar 7, 11:30", duration: "40m", status: "completed", alerts: 1 },
  { id: "s4", patient: "Aria", date: "Mar 3, 09:00", duration: "38m", status: "completed", alerts: 0 },
];

const ANXIETY_TREND = [
  { day: "Mon", score: 4 }, { day: "Tue", score: 3 }, { day: "Wed", score: 5 },
  { day: "Thu", score: 2 }, { day: "Fri", score: 3 }, { day: "Sat", score: 2 }, { day: "Sun", score: 2 },
];

const ENGAGEMENT_DATA = [
  { session: "S1", engagement: 65 }, { session: "S2", engagement: 72 },
  { session: "S3", engagement: 68 }, { session: "S4", engagement: 80 },
  { session: "S5", engagement: 85 }, { session: "S6", engagement: 78 },
];

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

/* ── Stat card ── */
function StatCard({ icon, label, value, trend, accent = "#4F46E5" }: {
  icon: React.ReactNode; label: string; value: string; trend?: string; accent?: string;
}) {
  return (
    <div
      style={{
        background: "#fff",
        borderRadius: 16,
        border: "1px solid #E2E8F0",
        padding: "1.25rem",
        display: "flex",
        flexDirection: "column",
        gap: 8,
        boxShadow: "0 1px 4px rgba(0,0,0,.04)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: "0.8125rem", color: "#64748B", fontWeight: 500 }}>{label}</span>
        <div
          style={{
            width: 34,
            height: 34,
            borderRadius: 10,
            background: `${accent}18`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: accent,
          }}
        >
          {icon}
        </div>
      </div>
      <div
        style={{
          fontFamily: "var(--font-display)",
          fontSize: "2rem",
          fontWeight: 700,
          color: "#1E1B4B",
          lineHeight: 1,
        }}
      >
        {value}
      </div>
      {trend && (
        <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: "0.75rem", color: "#16A34A", fontWeight: 600 }}>
          <TrendingUp size={12} />
          {trend}
        </div>
      )}
    </div>
  );
}

/* ── Main ── */
export default function TherapistDashboard() {
  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "#F8FAFC", fontFamily: "var(--font-body)" }}>
      {/* Sidebar */}
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
          <span style={{ fontFamily: "var(--font-display)", fontSize: "1.125rem", fontWeight: 700, color: "#1E1B4B" }}>
            DoodleSoul
          </span>
        </div>

        <NavItem icon={<LayoutDashboard size={18} />} label="Dashboard" to="/therapist" active />
        <NavItem icon={<Users size={18} />} label="Patients" to="/therapist/patients" />
        <NavItem icon={<CalendarDays size={18} />} label="Sessions" to="/therapist/live" />
        <NavItem icon={<BarChart2 size={18} />} label="Reports" to="/therapist/reports" />
        <NavItem icon={<Settings size={18} />} label="Settings" to="/therapist/settings" />

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

      {/* Main */}
      <main style={{ flex: 1, overflow: "auto" }}>
        {/* Header */}
        <header
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "1rem 1.5rem",
            background: "#fff",
            borderBottom: "1px solid #E2E8F0",
          }}
        >
          <div>
            <h1
              style={{
                fontFamily: "var(--font-display)",
                fontSize: "1.375rem",
                fontWeight: 700,
                color: "#1E1B4B",
              }}
            >
              Dashboard
            </h1>
            <p style={{ fontSize: "0.875rem", color: "#64748B" }}>Good morning, Dr. Sarah</p>
          </div>
          <Link
            to="/therapist/live"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "0.5rem 1rem",
              borderRadius: 9999,
              background: "linear-gradient(135deg, #FB923C, #F97316)",
              color: "#fff",
              textDecoration: "none",
              fontWeight: 700,
              fontSize: "0.875rem",
            }}
          >
            <Play size={14} fill="#fff" />
            Live Session
          </Link>
        </header>

        <div style={{ padding: "1.5rem", display: "flex", flexDirection: "column", gap: 20 }}>
          {/* Stats row */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 16 }}>
            <StatCard icon={<Users size={18} />} label="Active Patients" value="4" trend="+1 this week" accent="#4F46E5" />
            <StatCard icon={<CalendarDays size={18} />} label="Sessions Today" value="3" trend="On track" accent="#F97316" />
            <StatCard icon={<AlertCircle size={18} />} label="Pending Alerts" value="2" accent="#DC2626" />
            <StatCard icon={<Clock size={18} />} label="Avg. Duration" value="39m" trend="+4m vs last week" accent="#16A34A" />
          </div>

          {/* Charts row */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            {/* Anxiety trend */}
            <div
              style={{
                background: "#fff",
                borderRadius: 16,
                border: "1px solid #E2E8F0",
                padding: "1.25rem",
                boxShadow: "0 1px 4px rgba(0,0,0,.04)",
              }}
            >
              <h2 style={{ fontFamily: "var(--font-display)", fontSize: "0.9375rem", fontWeight: 700, color: "#1E1B4B", marginBottom: 16 }}>
                Anxiety Trend — Leo (This Week)
              </h2>
              <ResponsiveContainer width="100%" height={160}>
                <AreaChart data={ANXIETY_TREND}>
                  <defs>
                    <linearGradient id="anxietyGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#F97316" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="#F97316" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                  <XAxis dataKey="day" tick={{ fontSize: 11, fill: "#94A3B8" }} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 10]} tick={{ fontSize: 11, fill: "#94A3B8" }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid #E2E8F0", fontSize: 12 }} />
                  <Area type="monotone" dataKey="score" stroke="#F97316" strokeWidth={2.5} fill="url(#anxietyGrad)" dot={{ fill: "#F97316", r: 3 }} />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* Engagement trend */}
            <div
              style={{
                background: "#fff",
                borderRadius: 16,
                border: "1px solid #E2E8F0",
                padding: "1.25rem",
                boxShadow: "0 1px 4px rgba(0,0,0,.04)",
              }}
            >
              <h2 style={{ fontFamily: "var(--font-display)", fontSize: "0.9375rem", fontWeight: 700, color: "#1E1B4B", marginBottom: 16 }}>
                Engagement — Last 6 Sessions
              </h2>
              <ResponsiveContainer width="100%" height={160}>
                <LineChart data={ENGAGEMENT_DATA}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                  <XAxis dataKey="session" tick={{ fontSize: 11, fill: "#94A3B8" }} axisLine={false} tickLine={false} />
                  <YAxis domain={[50, 100]} tick={{ fontSize: 11, fill: "#94A3B8" }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid #E2E8F0", fontSize: 12 }} />
                  <Line type="monotone" dataKey="engagement" stroke="#4F46E5" strokeWidth={2.5} dot={{ fill: "#4F46E5", r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Bottom row */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            {/* Recent sessions */}
            <div
              style={{
                background: "#fff",
                borderRadius: 16,
                border: "1px solid #E2E8F0",
                padding: "1.25rem",
                boxShadow: "0 1px 4px rgba(0,0,0,.04)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
                <h2 style={{ fontFamily: "var(--font-display)", fontSize: "0.9375rem", fontWeight: 700, color: "#1E1B4B" }}>
                  Recent Sessions
                </h2>
                <Link to="/therapist/live" style={{ fontSize: "0.8125rem", color: "#4F46E5", fontWeight: 600, textDecoration: "none" }}>
                  View all
                </Link>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {MOCK_SESSIONS.map((s) => (
                  <div
                    key={s.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "0.75rem",
                      borderRadius: 10,
                      background: s.status === "active" ? "#EEF2FF" : "#F8FAFC",
                      border: `1px solid ${s.status === "active" ? "#C7D2FE" : "#E2E8F0"}`,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <div
                        style={{
                          width: 32,
                          height: 32,
                          borderRadius: "50%",
                          background: s.status === "active"
                            ? "linear-gradient(135deg, #818CF8, #4F46E5)"
                            : "linear-gradient(135deg, #CBD5E1, #94A3B8)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          color: "#fff",
                          fontFamily: "var(--font-display)",
                          fontWeight: 700,
                          fontSize: "0.8rem",
                        }}
                      >
                        {s.patient[0]}
                      </div>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: "0.875rem", color: "#1E1B4B" }}>{s.patient}</div>
                        <div style={{ fontSize: "0.75rem", color: "#64748B" }}>{s.date} · {s.duration}</div>
                      </div>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      {s.alerts > 0 && (
                        <span
                          style={{
                            fontSize: "0.6875rem",
                            fontWeight: 700,
                            padding: "2px 7px",
                            borderRadius: 99,
                            background: "#FEF2F2",
                            color: "#DC2626",
                            border: "1px solid #FECACA",
                          }}
                        >
                          {s.alerts} alert{s.alerts > 1 ? "s" : ""}
                        </span>
                      )}
                      {s.status === "active" && (
                        <Link
                          to="/therapist/live"
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            width: 26,
                            height: 26,
                            borderRadius: "50%",
                            background: "#4F46E5",
                            color: "#fff",
                          }}
                        >
                          <ChevronRight size={14} />
                        </Link>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Patients */}
            <div
              style={{
                background: "#fff",
                borderRadius: 16,
                border: "1px solid #E2E8F0",
                padding: "1.25rem",
                boxShadow: "0 1px 4px rgba(0,0,0,.04)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
                <h2 style={{ fontFamily: "var(--font-display)", fontSize: "0.9375rem", fontWeight: 700, color: "#1E1B4B" }}>
                  Patients
                </h2>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {MOCK_PATIENTS.map((p) => {
                  const riskColor = p.risk === "high" ? "#DC2626" : p.risk === "medium" ? "#D97706" : "#16A34A";
                  const riskBg = p.risk === "high" ? "#FEF2F2" : p.risk === "medium" ? "#FFFBEB" : "#F0FDF4";
                  return (
                    <div
                      key={p.id}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        padding: "0.75rem",
                        borderRadius: 10,
                        background: "#F8FAFC",
                        border: "1px solid #E2E8F0",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <div
                          style={{
                            width: 36,
                            height: 36,
                            borderRadius: "50%",
                            background: "linear-gradient(135deg, #A5B4FC, #818CF8)",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            color: "#fff",
                            fontFamily: "var(--font-display)",
                            fontWeight: 700,
                            fontSize: "0.9rem",
                          }}
                        >
                          {p.name[0]}
                        </div>
                        <div>
                          <div style={{ fontWeight: 700, fontSize: "0.875rem", color: "#1E1B4B" }}>
                            {p.name}, Age {p.age}
                          </div>
                          <div style={{ fontSize: "0.75rem", color: "#64748B" }}>Last: {p.lastSession}</div>
                        </div>
                      </div>
                      <span
                        style={{
                          fontSize: "0.6875rem",
                          fontWeight: 700,
                          padding: "3px 8px",
                          borderRadius: 99,
                          background: riskBg,
                          color: riskColor,
                          textTransform: "capitalize",
                          border: `1px solid ${riskColor}30`,
                        }}
                      >
                        {p.risk} risk
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
