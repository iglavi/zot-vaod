import { createHmac, timingSafeEqual } from "crypto";
import type { NextRequest } from "next/server";

export const AUTH_COOKIE = "zot_agent_auth";

// The cookie stores an HMAC derived from ACCESS_PASSWORD, never the password itself.
// Changing ACCESS_PASSWORD invalidates all existing cookies.
function derivedToken(): string {
  const password = process.env.ACCESS_PASSWORD ?? "";
  return createHmac("sha256", password).update("agent-chat-auth-v1").digest("hex");
}

function safeEqual(a: string, b: string): boolean {
  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  if (bufA.length !== bufB.length) return false;
  return timingSafeEqual(bufA, bufB);
}

export function checkPassword(candidate: string): boolean {
  const password = process.env.ACCESS_PASSWORD;
  if (!password) return false; // no password configured — deny everything
  // Compare HMACs of both values so lengths always match for timingSafeEqual
  const key = "agent-chat-pw-compare";
  const a = createHmac("sha256", key).update(candidate).digest();
  const b = createHmac("sha256", key).update(password).digest();
  return timingSafeEqual(a, b);
}

export function issueToken(): string {
  return derivedToken();
}

export function isAuthenticated(req: NextRequest): boolean {
  if (!process.env.ACCESS_PASSWORD) return false;
  const cookie = req.cookies.get(AUTH_COOKIE)?.value;
  if (!cookie) return false;
  return safeEqual(cookie, derivedToken());
}
