import { NextResponse } from "next/server";
import { analyticsSummary } from "@/lib/mock-data";

// TODO: derive from a real analytics store and respect query-string ranges.

export async function GET() {
  return NextResponse.json(analyticsSummary);
}
