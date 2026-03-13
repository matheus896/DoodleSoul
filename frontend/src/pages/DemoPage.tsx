export default function DemoPage() {
  return (
    <main
      style={{
        height: "100vh",
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: "0.75rem",
        padding: "0.75rem",
        background: "#F8FAFC",
      }}
    >
      <iframe
        title="Child Session"
        src="/session"
        allow="microphone"
        style={{
          width: "100%",
          height: "100%",
          border: "1px solid #E2E8F0",
          borderRadius: "12px",
          background: "#FFFFFF",
        }}
      />
      <iframe
        title="Therapist Live Insights"
        src="/therapist/live"
        style={{
          width: "100%",
          height: "100%",
          border: "1px solid #E2E8F0",
          borderRadius: "12px",
          background: "#FFFFFF",
        }}
      />
    </main>
  );
}
