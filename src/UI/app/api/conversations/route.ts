import { forward } from "@/lib/voice-api-forward";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const query = url.search || "";
  return forward(`/api/conversations${query}`, { cache: "no-store" });
}
