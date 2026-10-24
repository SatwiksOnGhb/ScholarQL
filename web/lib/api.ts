/**
 * Typed API client. Paths, params and response types come from lib/api-types.ts, which is
 * generated from the FastAPI spec. After changing anything in api/app/models or a router:
 *
 *   cd api && uv run python scripts/export_openapi.py   # FastAPI -> web/lib/openapi.json
 *   cd web && pnpm gen:api                              # openapi.json -> web/lib/api-types.ts
 *
 * Usage with React Query:
 *   useQuery({
 *     queryKey: ["paper", id],
 *     queryFn: () => unwrap(api.GET("/papers/{paper_id}", { params: { path: { paper_id: id } } })),
 *   })
 */
import createClient from "openapi-fetch";

import type { components, paths } from "./api-types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const api = createClient<paths>({ baseUrl: API_URL });

/** Every request/response model, e.g. Schemas["Paper"] */
export type Schemas = components["schemas"];

/** Thrown by unwrap(); mirrors the API's {"error": {code, message, details}} body. */
export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

/** Return the response data, or throw an ApiError (so React Query's `error` is typed). */
export async function unwrap<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let result;
  try {
    result = await request;
  } catch {
    throw new ApiError(0, "network_error", `Can't reach the API at ${API_URL}. Is it running?`);
  }
  const { data, error, response } = result;
  if (error !== undefined || !response.ok) {
    const body = (error as Partial<Schemas["ErrorResponse"]> | undefined)?.error;
    throw new ApiError(
      response.status,
      body?.code ?? "http_error",
      body?.message ?? `Request failed with status ${response.status}`,
      body?.details,
    );
  }
  return data as T;
}
