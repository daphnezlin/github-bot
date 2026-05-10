import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";

type EventType =
  | { type: "status"; message: string }
  | { type: "thinking"; message: string }
  | { type: "tool_call"; tool: string; input: Record<string, unknown> }
  | { type: "tool_result"; tool: string; preview: string }
  | { type: "complete"; message: string; review: string }
  | { type: "error"; message: string };

const TOOL_ICONS: Record<string, string> = {
  get_pr_diff: "📄",
  run_linter: "🔍",
  get_test_coverage: "🧪",
  search_related_issues: "🔗",
};

function App() {
  const [prNumber, setPrNumber] = useState("");
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<EventType[]>([]);
  const [review, setReview] = useState<string | null>(null);
  const [activeTools, setActiveTools] = useState<Set<string>>(new Set());
  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  function connect() {
    if (!prNumber) return;
    const ws = new WebSocket(`ws://localhost:8000/ws/${prNumber}`);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);

    ws.onmessage = (msg) => {
      const event: EventType = JSON.parse(msg.data);
      setEvents((prev) => [...prev, event]);

      if (event.type === "tool_call") {
        setActiveTools((prev) => new Set(prev).add(event.tool));
      }
      if (event.type === "tool_result") {
        setActiveTools((prev) => {
          const next = new Set(prev);
          next.delete(event.tool);
          return next;
        });
      }
      if (event.type === "complete") {
        setReview(event.review);
      }
    };
  }

  function disconnect() {
    wsRef.current?.close();
    setConnected(false);
    setEvents([]);
    setReview(null);
    setActiveTools(new Set());
  }

  const toolsDone = new Set(
    events
      .filter((e) => e.type === "tool_result")
      .map((e) => (e as { tool: string }).tool)
  );

  return (
    <div style={styles.page}>
      <div style={styles.container}>

        {/* Header */}
        <div style={styles.header}>
          <h1 style={styles.title}>🤖 GitHub Review Agent</h1>
          <div style={styles.statusRow}>
            <span style={{ ...styles.dot, background: connected ? "#22c55e" : "#6b7280" }} />
            <span style={styles.statusText}>{connected ? "Connected" : "Disconnected"}</span>
          </div>
        </div>

        {/* Connect bar */}
        <div style={styles.connectBar}>
          <input
            style={styles.input}
            placeholder="PR number"
            value={prNumber}
            onChange={(e) => setPrNumber(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && connect()}
            disabled={connected}
          />
          {!connected ? (
            <button style={styles.btn} onClick={connect}>Connect</button>
          ) : (
            <button style={{ ...styles.btn, background: "#374151" }} onClick={disconnect}>
              Disconnect
            </button>
          )}
        </div>

        <div style={styles.grid}>

          {/* Left: tool tracker */}
          <div style={styles.card}>
            <div style={styles.cardTitle}>Tool calls</div>
            {Object.entries(TOOL_ICONS).map(([tool, icon]) => {
              const isDone = toolsDone.has(tool);
              const isRunning = activeTools.has(tool);
              return (
                <div key={tool} style={styles.toolRow}>
                  <span style={styles.toolIcon}>{icon}</span>
                  <div>
                    <div style={styles.toolName}>{tool}</div>
                    <div style={{
                      ...styles.toolStatus,
                      color: isDone ? "#22c55e" : isRunning ? "#f59e0b" : "#6b7280"
                    }}>
                      {isDone ? "✓ done" : isRunning ? "⟳ running…" : "waiting"}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Right: event stream */}
          <div style={styles.card}>
            <div style={styles.cardTitle}>Agent stream</div>
            <div style={styles.stream}>
              {events.length === 0 && (
                <div style={styles.empty}>Connect to a PR to start…</div>
              )}
              {events.map((e, i) => (
                <div key={i} style={styles.eventRow}>
                  <span style={styles.timestamp}>
                    {new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                  </span>
                  <span style={{ color: eventColor(e.type) }}>
                    {renderEvent(e)}
                  </span>
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
          </div>
        </div>

        {/* Review output */}
        {review && (
          <div style={styles.card}>
            <div style={styles.cardTitle}>Review output</div>
            <div style={styles.reviewBody}>
              <ReactMarkdown>{review}</ReactMarkdown>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function renderEvent(e: EventType): string {
  switch (e.type) {
    case "status":    return `ℹ ${e.message}`;
    case "thinking":  return `💭 ${e.message}`;
    case "tool_call": return `→ ${e.tool}(${JSON.stringify(e.input).slice(0, 60)}…)`;
    case "tool_result": return `← ${e.tool}: ${e.preview.slice(0, 80)}`;
    case "complete":  return `✅ ${e.message}`;
    case "error":     return `❌ ${e.message}`;
  }
}

function eventColor(type: string): string {
  switch (type) {
    case "tool_call":   return "#60a5fa";
    case "tool_result": return "#34d399";
    case "complete":    return "#22c55e";
    case "error":       return "#f87171";
    default:            return "#9ca3af";
  }
}

const styles: Record<string, React.CSSProperties> = {
  page:        { minHeight: "100vh", background: "#0f172a", padding: "2rem", fontFamily: "monospace" },
  container:   { maxWidth: 1000, margin: "0 auto", display: "flex", flexDirection: "column", gap: 16 },
  header:      { display: "flex", justifyContent: "space-between", alignItems: "center" },
  title:       { color: "#f1f5f9", fontSize: 22, fontWeight: 500, margin: 0 },
  statusRow:   { display: "flex", alignItems: "center", gap: 8 },
  dot:         { width: 10, height: 10, borderRadius: "50%", display: "inline-block" },
  statusText:  { color: "#9ca3af", fontSize: 13 },
  connectBar:  { display: "flex", gap: 8 },
  input:       { flex: 1, background: "#1e293b", border: "1px solid #334155", borderRadius: 8, padding: "8px 12px", color: "#f1f5f9", fontSize: 14, outline: "none" },
  btn:         { background: "#2563eb", color: "#fff", border: "none", borderRadius: 8, padding: "8px 20px", fontSize: 14, cursor: "pointer", fontFamily: "monospace" },
  grid:        { display: "grid", gridTemplateColumns: "260px 1fr", gap: 16 },
  card:        { background: "#1e293b", border: "1px solid #334155", borderRadius: 12, padding: 16 },
  cardTitle:   { color: "#94a3b8", fontSize: 11, fontWeight: 500, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 12 },
  toolRow:     { display: "flex", alignItems: "center", gap: 10, marginBottom: 12 },
  toolIcon:    { fontSize: 20 },
  toolName:    { color: "#f1f5f9", fontSize: 13, fontWeight: 500 },
  toolStatus:  { fontSize: 11, marginTop: 2 },
  stream:      { height: 280, overflowY: "auto", display: "flex", flexDirection: "column", gap: 4 },
  eventRow:    { display: "flex", gap: 8, fontSize: 12, lineHeight: 1.6 },
  timestamp:   { color: "#475569", flexShrink: 0 },
  empty:       { color: "#475569", fontSize: 13, textAlign: "center", marginTop: 40 },
  reviewBody:  { color: "#cbd5e1", fontSize: 14, lineHeight: 1.7 },
};

export default App;