// frontend/src/api/client.ts
import createClient, { type ClientOptions, type Middleware } from "openapi-fetch";
import type { paths } from "./schema.ts";

const WRITE_METHODS: ReadonlySet<string> = new Set(["POST", "PUT", "DELETE"]);

export class ApiRequestError extends Error {
  readonly route: string;
  readonly status: number;

  constructor(route: string, status: number) {
    super(`API request failed: ${route} (${String(status)})`);
    this.name = "ApiRequestError";
    this.route = route;
    this.status = status;
  }
}

export function formatApiFailure(route: string, status: number): string {
  return `API request failed: ${route} (status ${String(status)})`;
}

export const jsonWriteHeadersMiddleware: Middleware = {
  onRequest({ request }) {
    if (WRITE_METHODS.has(request.method.toUpperCase())) {
      if (!request.headers.has("Content-Type")) {
        request.headers.set("Content-Type", "application/json");
      }
    }
    return request;
  },
};

export function createApiClient(options?: ClientOptions) {
  const client = createClient<paths>({
    baseUrl: "",
    ...options,
  });
  client.use(jsonWriteHeadersMiddleware);
  return client;
}

export const apiClient = createApiClient();
