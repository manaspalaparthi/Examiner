import { NextResponse } from "next/server";
import { ADMIN_USER, AUTH_COOKIE, verifyCredentials } from "@/lib/auth";

export async function POST(req: Request) {
  const body = await req.json().catch(() => null);
  const username = String(body?.username ?? "");
  const password = String(body?.password ?? "");

  if (!verifyCredentials(username, password)) {
    return NextResponse.json({ error: "Invalid username or password" }, { status: 401 });
  }

  const res = NextResponse.json({
    user: {
      id: ADMIN_USER.id,
      username: ADMIN_USER.username,
      name: ADMIN_USER.name,
      email: ADMIN_USER.email,
    },
  });
  res.cookies.set(AUTH_COOKIE, ADMIN_USER.id, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 7,
  });
  return res;
}
