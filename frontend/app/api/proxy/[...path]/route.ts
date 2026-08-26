/**
 * Same-origin proxy for the Phase 5 FastAPI backend.
 *
 * The backend (Render) does not send Access-Control-Allow-Origin, so direct
 * browser fetches to it are blocked by CORS even though the server itself
 * responds correctly. This route forwards GET requests server-side (Next.js
 * server -> FastAPI), which is not subject to browser CORS rules, and
 * returns the untouched JSON body and status code to the client. No backend
 * code, data, or contract is modified — this only changes how the browser
 * reaches the existing endpoints.
 */
import { NextRequest, NextResponse } from "next/server";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export async function GET(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  if (!API_BASE_URL) {
    return NextResponse.json({ detail: "NEXT_PUBLIC_API_BASE_URL is not configured" }, { status: 503 });
  }

  const { path } = await params;
  const search = request.nextUrl.search;
  const upstreamUrl = `${API_BASE_URL}/${path.join("/")}${search}`;

  let upstreamResponse: Response;
  try {
    upstreamResponse = await fetch(upstreamUrl, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "Unable to reach the transit dashboard API" }, { status: 502 });
  }

  const body = await upstreamResponse.text();
  return new NextResponse(body, {
    status: upstreamResponse.status,
    headers: { "Content-Type": upstreamResponse.headers.get("Content-Type") ?? "application/json" },
  });
}
