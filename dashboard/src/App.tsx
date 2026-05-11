import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";

type EventType =
  | { type: "status"; message: string }
  | { type: "thinking"; message: string }
  | { type: "tool_call"; tool: string; input: Record<string, unknown> }
  | { type: "tool_result"; tool: string; preview: string }
  | { type: "complete"; message: string; review: string }
  | { type: "error"; message: string };

const TOOLS = ["get_pr_diff", "run_linter", "get_test_coverage", "search_related_issues"];

const TOOL_LABELS: Record<string, string> = {
  get_pr_diff: "Fetch diff",
  run_linter: "Run linter",
  get_test_coverage: "Check coverage",
  search_related_issues: "Search issues",
};

const css = `
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: #f0ede8;
    font-family: 'IBM Plex Sans', sans-serif;
    color: #1a1a1a;
  }

  .page {
    min-height: 100vh;
    padding: 0;
    display: flex;
    flex-direction: column;
  }

  .topbar {
    border-bottom: 1px solid #c8c4bc;
    padding: 0 32px;
    height: 44px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: #f0ede8;
    position: sticky;
    top: 0;
    z-index: 10;
  }

  .topbar-left {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .logo-mark {
    width: 20px;
    height: 20px;
    background: #1a1a1a;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .logo-inner {
    width: 8px;
    height: 8px;
    background: #f0ede8;
  }

  .app-name {
    font-size: 13px;
    font-weight: 500;
    letter-spacing: 0.02em;
    color: #1a1a1a;
  }

  .status-chip {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: #6b6560;
    font-family: 'IBM Plex Mono', monospace;
  }

  .status-dot {
    width: 6px;
    height: 6px;
    background: #6b6560;
    transition: background 0.2s;
  }

  .status-dot.connected {
    background: #2d6a2d;
  }

  .main {
    flex: 1;
    display: grid;
    grid-template-columns: 220px 1fr;
    grid-template-rows: auto 1fr;
    max-width: 1200px;
    width: 100%;
    margin: 0 auto;
    padding: 32px 32px 32px 32px;
    gap: 0;
  }

  /* Connect bar spans full width */
  .connect-bar {
    grid-column: 1 / -1;
    display: flex;
    gap: 0;
    margin-bottom: 24px;
    border: 1px solid #c8c4bc;
    background: #fff;
  }

  .connect-bar input {
    flex: 1;
    border: none;
    outline: none;
    padding: 10px 14px;
    font-size: 13px;
    font-family: 'IBM Plex Mono', monospace;
    background: transparent;
    color: #1a1a1a;
  }

  .connect-bar input::placeholder {
    color: #a09a93;
  }

  .connect-bar input:disabled {
    color: #a09a93;
  }

  .connect-btn {
    border: none;
    border-left: 1px solid #c8c4bc;
    background: #1a1a1a;
    color: #f0ede8;
    padding: 10px 20px;
    font-size: 12px;
    font-family: 'IBM Plex Mono', monospace;
    letter-spacing: 0.05em;
    cursor: pointer;
    transition: background 0.15s;
    white-space: nowrap;
  }

  .connect-btn:hover {
    background: #2d2d2d;
  }

  .connect-btn.disconnect {
    background: #f0ede8;
    color: #6b6560;
  }

  .connect-btn.disconnect:hover {
    background: #e8e4df;
  }

  /* Sidebar */
  .sidebar {
    border-right: 1px solid #c8c4bc;
    padding-right: 24px;
    margin-right: 24px;
  }

  .section-label {
    font-size: 10px;
    font-family: 'IBM Plex Mono', monospace;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #a09a93;
    margin-bottom: 14px;
  }

  .tool-list {
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .tool-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 9px 0;
    border-bottom: 1px solid #e8e4df;
  }

  .tool-item:last-child {
    border-bottom: none;
  }

  .tool-name {
    font-size: 12px;
    color: #3d3830;
    font-family: 'IBM Plex Mono', monospace;
  }

  .tool-state {
    font-size: 11px;
    font-family: 'IBM Plex Mono', monospace;
    color: #a09a93;
  }

  .tool-state.running {
    color: #7a6030;
  }

  .tool-state.done {
    color: #2d6a2d;
  }

  /* Stream panel */
  .stream-panel {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .stream-scroll {
    height: 320px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    line-height: 1.7;
    background: #fff;
    border: 1px solid #c8c4bc;
    padding: 14px;
  }

  .stream-scroll::-webkit-scrollbar {
    width: 4px;
  }

  .stream-scroll::-webkit-scrollbar-track {
    background: transparent;
  }

  .stream-scroll::-webkit-scrollbar-thumb {
    background: #c8c4bc;
  }

  .stream-empty {
    color: #c8c4bc;
    font-size: 12px;
    margin: auto;
    text-align: center;
    padding: 40px 0;
  }

  .event-row {
    display: flex;
    gap: 12px;
  }

  .event-time {
    color: #c8c4bc;
    flex-shrink: 0;
    user-select: none;
  }

  .event-text {
    color: #3d3830;
  }

  .event-text.tool-call {
    color: #1a1a1a;
  }

  .event-text.tool-result {
    color: #3d5a3d;
  }

  .event-text.complete {
    color: #2d6a2d;
    font-weight: 500;
  }

  .event-text.error {
    color: #8b2020;
  }

  .event-text.thinking {
    color: #a09a93;
  }

  /* Review output */
  .review-section {
    grid-column: 1 / -1;
    margin-top: 24px;
    border-top: 1px solid #c8c4bc;
    padding-top: 24px;
  }

  .review-body {
    margin-top: 14px;
    background: #fff;
    border: 1px solid #c8c4bc;
    padding: 24px;
    font-size: 13px;
    line-height: 1.8;
    color: #3d3830;
  }

  .review-body h2 {
    font-size: 14px;
    font-weight: 500;
    color: #1a1a1a;
    margin: 20px 0 8px;
    font-family: 'IBM Plex Sans', sans-serif;
  }

  .review-body h2:first-child {
    margin-top: 0;
  }

  .review-body h3 {
    font-size: 13px;
    font-weight: 500;
    color: #1a1a1a;
    margin: 16px 0 6px;
  }

  .review-body ul {
    padding-left: 20px;
  }

  .review-body li {
    margin-bottom: 4px;
  }

  .review-body code {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    background: #f0ede8;
    padding: 1px 5px;
    color: #1a1a1a;
  }

  .review-body pre {
    background: #f0ede8;
    padding: 12px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    overflow-x: auto;
    margin: 10px 0;
  }

  .review-body hr {
    border: none;
    border-top: 1px solid #e8e4df;
    margin: 16px 0;
  }

  .review-body p {
    margin-bottom: 8px;
  }
`;

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
    <>
      <style>{css}</style>
      <div className="page">
        <div className="topbar">
          <div className="topbar-left">
            <div className="logo-mark"><div className="logo-inner" /></div>
            <span className="app-name">PR Review Agent</span>
          </div>
          <div className="status-chip">
            <div className={`status-dot ${connected ? "connected" : ""}`} />
            {connected ? "connected" : "idle"}
          </div>
        </div>

        <div className="main">
          {/* Connect bar */}
          <div className="connect-bar">
            <input
              placeholder="Enter PR number"
              value={prNumber}
              onChange={(e) => setPrNumber(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && connect()}
              disabled={connected}
            />
            {!connected ? (
              <button className="connect-btn" onClick={connect}>CONNECT</button>
            ) : (
              <button className="connect-btn disconnect" onClick={disconnect}>DISCONNECT</button>
            )}
          </div>

          {/* Sidebar: tool tracker */}
          <div className="sidebar">
            <div className="section-label">Tools</div>
            <div className="tool-list">
              {TOOLS.map((tool) => {
                const isDone = toolsDone.has(tool);
                const isRunning = activeTools.has(tool);
                return (
                  <div key={tool} className="tool-item">
                    <span className="tool-name">{TOOL_LABELS[tool]}</span>
                    <span className={`tool-state ${isDone ? "done" : isRunning ? "running" : ""}`}>
                      {isDone ? "done" : isRunning ? "running" : "—"}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Stream panel */}
          <div className="stream-panel">
            <div className="section-label">Agent log</div>
            <div className="stream-scroll">
              {events.length === 0 && (
                <div className="stream-empty">waiting for events</div>
              )}
              {events.map((e, i) => (
                <div key={i} className="event-row">
                  <span className="event-time">
                    {new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                  </span>
                  <span className={`event-text ${e.type === "tool_call" ? "tool-call" : e.type === "tool_result" ? "tool-result" : e.type === "complete" ? "complete" : e.type === "error" ? "error" : e.type === "thinking" ? "thinking" : ""}`}>
                    {renderEvent(e)}
                  </span>
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
          </div>

          {/* Review output */}
          {review && (
            <div className="review-section">
              <div className="section-label">Review output</div>
              <div className="review-body">
                <ReactMarkdown>{review}</ReactMarkdown>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function renderEvent(e: EventType): string {
  switch (e.type) {
    case "status":      return e.message;
    case "thinking":    return e.message;
    case "tool_call":   return `> ${e.tool}(${JSON.stringify(e.input).slice(0, 70)})`;
    case "tool_result": return `< ${e.tool}: ${e.preview.slice(0, 90)}`;
    case "complete":    return e.message;
    case "error":       return `error: ${e.message}`;
  }
}

export default App;