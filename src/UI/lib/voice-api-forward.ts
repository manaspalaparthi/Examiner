import { NextResponse } from "next/server";
import { voiceApiUrl } from "@/lib/voice-api";

export async function forward(path: string, init?: RequestInit) {
  try {
    const res = await fetch(voiceApiUrl(path), init);
    const hasBody = ![204, 205, 304].includes(res.status);
    const body = hasBody ? await res.text() : null;
    const headers = new Headers();
    const contentType = res.headers.get("Content-Type");
    if (contentType && hasBody) {
      headers.set("Content-Type", contentType);
    }

    return new NextResponse(body, {
      status: res.status,
      headers,
    });
  } catch {
    return NextResponse.json(
      { error: "Voice API is unavailable" },
      { status: 502 },
    );
  }
}
