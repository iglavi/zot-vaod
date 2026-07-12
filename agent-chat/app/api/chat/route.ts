import Anthropic from "@anthropic-ai/sdk";
import { NextRequest, NextResponse } from "next/server";
import { isAuthenticated } from "@/lib/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
// Agent turns can take a while (tool use etc.) — allow the function to run long.
export const maxDuration = 300;

type ClientEvent =
  | { type: "session"; sessionId: string }
  | { type: "status"; status: "thinking" | "tool" | "responding"; tool?: string }
  | { type: "text"; text: string }
  | { type: "done" }
  | { type: "error"; message: string };

export async function POST(req: NextRequest) {
  if (!isAuthenticated(req)) {
    return NextResponse.json({ error: "נדרשת הזדהות" }, { status: 401 });
  }
  if (!process.env.ANTHROPIC_API_KEY || !process.env.AGENT_ID || !process.env.ENVIRONMENT_ID) {
    return NextResponse.json(
      { error: "השרת לא מוגדר — חסרים משתני סביבה (ANTHROPIC_API_KEY / AGENT_ID / ENVIRONMENT_ID)" },
      { status: 500 },
    );
  }

  let message = "";
  let existingSessionId: string | null = null;
  try {
    const body = await req.json();
    message = typeof body?.message === "string" ? body.message.trim() : "";
    existingSessionId = typeof body?.sessionId === "string" && body.sessionId ? body.sessionId : null;
  } catch {
    return NextResponse.json({ error: "בקשה לא תקינה" }, { status: 400 });
  }
  if (!message) {
    return NextResponse.json({ error: "הודעה ריקה" }, { status: 400 });
  }

  const client = new Anthropic();

  // Reuse an existing session if the client passed one; otherwise create a new
  // session that references the pre-created agent (AGENT_ID) and environment.
  let sessionId = existingSessionId;
  if (!sessionId) {
    const session = await client.beta.sessions.create({
      agent: process.env.AGENT_ID,
      environment_id: process.env.ENVIRONMENT_ID,
      title: "שיחת צ'אט מהאתר",
    });
    sessionId = session.id;
  }

  // Stream-first: open the SSE stream from Anthropic BEFORE sending the message,
  // so no early events are missed.
  const agentStream = await client.beta.sessions.events.stream(sessionId);
  await client.beta.sessions.events.send(sessionId, {
    events: [{ type: "user.message", content: [{ type: "text", text: message }] }],
  });

  const encoder = new TextEncoder();

  const body = new ReadableStream<Uint8Array>({
    async start(controller) {
      const emit = (event: ClientEvent) => {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
      };

      emit({ type: "session", sessionId: sessionId! });

      try {
        for await (const event of agentStream) {
          if (req.signal.aborted) break;

          if (event.type === "span.model_request_start") {
            emit({ type: "status", status: "thinking" });
          } else if (event.type === "agent.tool_use" || event.type === "agent.mcp_tool_use") {
            emit({ type: "status", status: "tool", tool: (event as { name?: string }).name });
          } else if (event.type === "agent.message") {
            for (const block of event.content) {
              if (block.type === "text") emit({ type: "text", text: block.text });
            }
          } else if (event.type === "session.error") {
            const err = event as { error?: { message?: string } };
            emit({ type: "error", message: err.error?.message ?? "אירעה שגיאה בעיבוד הבקשה" });
          } else if (event.type === "session.status_idle") {
            // Transient idle (waiting for a tool confirmation / custom tool result)
            // is not something this UI supports — surface it instead of hanging.
            const stop = (event as { stop_reason?: { type?: string } }).stop_reason;
            if (stop?.type === "requires_action") {
              emit({
                type: "error",
                message: "הסוכן ממתין לאישור או לכלי חיצוני שהממשק הזה לא תומך בו",
              });
            }
            emit({ type: "done" });
            break;
          } else if (event.type === "session.status_terminated") {
            emit({ type: "error", message: "השיחה הסתיימה בצד השרת — התחילו שיחה חדשה" });
            emit({ type: "done" });
            break;
          }
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : "שגיאה לא צפויה";
        try {
          emit({ type: "error", message: msg });
          emit({ type: "done" });
        } catch {
          // controller already closed
        }
      } finally {
        try {
          controller.close();
        } catch {
          // already closed
        }
      }
    },
  });

  return new Response(body, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
