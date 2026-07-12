"use client";

import { useEffect, useRef, useState } from "react";

type Message = { role: "user" | "assistant" | "error"; text: string };
type Status = null | { kind: "thinking" | "tool" | "responding"; tool?: string };

const LS_SESSION = "agent_chat_session_id";
const LS_MESSAGES = "agent_chat_messages";
const LS_AUTHED = "agent_chat_authed";

export default function ChatPage() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Restore local state on first load
  useEffect(() => {
    setAuthed(localStorage.getItem(LS_AUTHED) === "1");
    try {
      const saved = localStorage.getItem(LS_MESSAGES);
      if (saved) setMessages(JSON.parse(saved));
    } catch {
      /* ignore corrupt storage */
    }
  }, []);

  // Persist messages
  useEffect(() => {
    if (authed) localStorage.setItem(LS_MESSAGES, JSON.stringify(messages.slice(-200)));
  }, [messages, authed]);

  // Auto-scroll to the newest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, status]);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoggingIn(true);
    setLoginError("");
    try {
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (res.ok) {
        localStorage.setItem(LS_AUTHED, "1");
        setAuthed(true);
        setPassword("");
      } else {
        const data = await res.json().catch(() => null);
        setLoginError(data?.error ?? "סיסמה שגויה");
      }
    } catch {
      setLoginError("שגיאת רשת — נסו שוב");
    } finally {
      setLoggingIn(false);
    }
  }

  function newChat() {
    localStorage.removeItem(LS_SESSION);
    localStorage.removeItem(LS_MESSAGES);
    setMessages([]);
    setStatus(null);
  }

  function loggedOut() {
    localStorage.removeItem(LS_AUTHED);
    setAuthed(false);
  }

  async function sendMessage() {
    const text = input.trim();
    if (!text || busy) return;

    setInput("");
    setBusy(true);
    setStatus({ kind: "thinking" });
    setMessages((prev) => [...prev, { role: "user", text }]);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          sessionId: localStorage.getItem(LS_SESSION) || undefined,
        }),
      });

      if (res.status === 401) {
        loggedOut();
        return;
      }
      if (!res.ok || !res.body) {
        const data = await res.json().catch(() => null);
        setMessages((prev) => [
          ...prev,
          { role: "error", text: data?.error ?? "אירעה שגיאה — נסו שוב" },
        ]);
        return;
      }

      // Read the SSE stream: parse "data: {...}" frames separated by blank lines
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";

        for (const frame of frames) {
          const line = frame.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          let event: {
            type: string;
            sessionId?: string;
            status?: string;
            tool?: string;
            text?: string;
            message?: string;
          };
          try {
            event = JSON.parse(line.slice(6));
          } catch {
            continue;
          }

          if (event.type === "session" && event.sessionId) {
            localStorage.setItem(LS_SESSION, event.sessionId);
          } else if (event.type === "status") {
            setStatus({
              kind: (event.status as "thinking" | "tool" | "responding") ?? "thinking",
              tool: event.tool,
            });
          } else if (event.type === "text" && event.text) {
            const chunk = event.text;
            setStatus({ kind: "responding" });
            setMessages((prev) => [...prev, { role: "assistant", text: chunk }]);
          } else if (event.type === "error" && event.message) {
            const msg = event.message;
            setMessages((prev) => [...prev, { role: "error", text: msg }]);
          }
          // "done" — the stream will close on its own
        }
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "error", text: "החיבור נותק — נסו לשלוח שוב" },
      ]);
    } finally {
      setBusy(false);
      setStatus(null);
      textareaRef.current?.focus();
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  if (authed === null) return null; // avoid flash before localStorage is read

  if (!authed) {
    return (
      <div className="loginWrap">
        <form className="loginCard" onSubmit={handleLogin}>
          <h1>צ'אט עם הסוכן</h1>
          <p>הזינו את סיסמת הגישה כדי להמשיך</p>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="סיסמת גישה"
            autoFocus
            required
          />
          {loginError && <div className="loginError">{loginError}</div>}
          <button type="submit" disabled={loggingIn}>
            {loggingIn ? "בודק..." : "כניסה"}
          </button>
        </form>
      </div>
    );
  }

  const statusText =
    status?.kind === "tool"
      ? status.tool
        ? `מריץ כלי: ${status.tool}...`
        : "מריץ כלי..."
      : status?.kind === "responding"
        ? "כותב תשובה..."
        : "חושב...";

  return (
    <div className="app">
      <header className="header">
        <h1>צ'אט עם הסוכן</h1>
        <button className="newChatBtn" onClick={newChat} disabled={busy}>
          שיחה חדשה
        </button>
      </header>

      <main className="messages">
        {messages.length === 0 && (
          <div className="emptyHint">שלחו הודעה כדי להתחיל שיחה עם הסוכן</div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`bubble ${m.role === "user" ? "user" : m.role === "error" ? "error" : "assistant"}`}
          >
            {m.text}
          </div>
        ))}
        {busy && status && (
          <div className="status">
            <span className="dot" />
            {statusText}
          </div>
        )}
        <div ref={bottomRef} />
      </main>

      <footer className="composer">
        <textarea
          ref={textareaRef}
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="כתבו הודעה..."
          disabled={busy}
        />
        <button className="sendBtn" onClick={sendMessage} disabled={busy || !input.trim()}>
          שליחה
        </button>
      </footer>
    </div>
  );
}
