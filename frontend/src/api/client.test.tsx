// frontend/src/api/client.test.tsx
import { describe, expect, it, vi } from "vitest";
import {
  ApiRequestError,
  createApiClient,
  formatApiFailure,
} from "./client.ts";

describe("apiClient write headers and error formatting", () => {
  it("attaches Content-Type: application/json to POST and PUT write requests even without a body", async () => {
    const seenRequests: Request[] = [];
    const customFetch: typeof fetch = vi.fn((input: RequestInfo | URL) => {
      if (input instanceof Request) {
        seenRequests.push(input);
      }
      return Promise.resolve(
        new Response(JSON.stringify({}), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    });

    const client = createApiClient({
      baseUrl: "http://127.0.0.1:8765",
      fetch: customFetch,
    });

    await client.POST("/api/cycles", { body: {} });
    await client.POST("/api/notifications/test", { body: {} });
    await client.PUT("/api/locations/evacuation", {
      body: { location: "Miami-Dade", on: true },
    });
    await client.GET("/api/health");

    expect(seenRequests).toHaveLength(4);
    expect(seenRequests[0]!.method).toBe("POST");
    expect(seenRequests[0]!.headers.get("Content-Type")).toBe(
      "application/json",
    );
    expect(seenRequests[1]!.method).toBe("POST");
    expect(seenRequests[1]!.headers.get("Content-Type")).toBe(
      "application/json",
    );
    expect(seenRequests[2]!.method).toBe("PUT");
    expect(seenRequests[2]!.headers.get("Content-Type")).toBe(
      "application/json",
    );
    expect(seenRequests[3]!.method).toBe("GET");
  });

  it("formats failed API requests with only the route and status code", () => {
    const err = new ApiRequestError("/api/locations", 422);
    expect(err.route).toBe("/api/locations");
    expect(err.status).toBe(422);
    expect(err.message).toBe("API request failed: /api/locations (422)");
    expect(formatApiFailure("/api/cycles", 429)).toBe(
      "API request failed: /api/cycles (status 429)",
    );
  });
});
