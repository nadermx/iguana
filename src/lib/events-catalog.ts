import { createKintanaClient } from "@kintana/sdk";
import type { KintanaPublicEvent } from "@kintana/sdk";

import { partitionEventsBySchedule, todayInCancun } from "./events";

/** Inclusive UTC `YYYY-MM-DD` for API `from`/`to`. */
export function utcDateIso(d = new Date()): string {
  return d.toISOString().slice(0, 10);
}

type Client = ReturnType<typeof createKintanaClient>;

/**
 * Loads calendar sections using API filters (`from` / `status: past`), then reunifies rows
 * and applies {@link partitionEventsBySchedule} for edge cases (stale statuses vs the Cancun day).
 */
export async function loadEventsForCalendarPages(client: Client): Promise<{ upcoming: KintanaPublicEvent[]; past: KintanaPublicEvent[] }> {
  // The Cancun day, not UTC's: from 19:00 Playa time UTC is already tomorrow and tonight's show fell out.
  const from = todayInCancun();

  const [fromTodayRows, pastStatusRows] = await Promise.all([
    client.listEvents({ limit: 100, from }),
    client.listEvents({ limit: 100, status: "past" }),
  ]);

  const byId = new Map<string, KintanaPublicEvent>();
  for (const evt of pastStatusRows) {
    if (evt.status !== "cancelled") byId.set(evt.id, evt);
  }
  for (const evt of fromTodayRows) {
    if (evt.status === "cancelled") continue;
    byId.set(evt.id, evt);
  }

  return partitionEventsBySchedule([...byId.values()]);
}
