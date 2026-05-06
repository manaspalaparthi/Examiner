import { NextResponse } from "next/server";
import { voices } from "@/lib/mock-data";

// TODO: proxy to a real voice provider (ElevenLabs, OpenAI, etc.) once integrated.

export async function GET() {
  return NextResponse.json(voices);
}
