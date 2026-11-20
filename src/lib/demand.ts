import type { KintanaPublicEvent } from "@kintana/sdk";

import type { Locale } from "../i18n/locale";
import { t } from "../i18n/ui";

/**
 * How full a night is, and how fast it is filling. The API sends this on every event (see
 * `backend/sales/demand.py`), and the checkout iframe already prints the same three sentences from the same
 * numbers. This is the site's copy of that, so a person sees one consistent story from the home page hero to
 * the reserve button.
 *
 * Urgency is only persuasive while it is true, so every rule that keeps it honest lives in the backend and is
 * reproduced here rather than loosened: the window is the tightest one that genuinely holds the bookings, a
 * count below two is not shown at all, and an empty room says nothing rather than something weak.
 */
export type EventDemand = {
  capacity: number;
  taken: number;
  left: number;
  showBar: boolean;
  recent: number;
  /** The English window key the backend chose; both languages map it through `WINDOW_KEYS`. */
  recentWindow: string;
  /** Every window's count, so several nights can be added up over the SAME window. */
  recentByWindow: Record<string, number>;
  /** The show is today in Playa (the backend decides, by the Cancun calendar). */
  tonight: boolean;
};

/** The SDK's event type is fixed and does not know about this field, so read it off the payload by hand. */
export function eventDemand(evt: KintanaPublicEvent): EventDemand | null {
  const raw = (evt as unknown as { demand?: unknown }).demand;
  if (!raw || typeof raw !== "object") return null;
  const d = raw as Partial<EventDemand>;
  if (!d.capacity || typeof d.capacity !== "number") return null;
  return {
    capacity: d.capacity,
    taken: Number(d.taken ?? 0),
    left: Number(d.left ?? 0),
    showBar: Boolean(d.showBar),
    recent: Number(d.recent ?? 0),
    recentWindow: String(d.recentWindow ?? ""),
    recentByWindow: (d.recentByWindow && typeof d.recentByWindow === "object" ? d.recentByWindow : {}) as Record<string, number>,
    tonight: Boolean(d.tonight),
  };
}

/** Matches MIN_RECENT in `backend/sales/demand.py`. Below this a count is not social proof, it is an admission. */
const MIN_RECENT = 2;

const WINDOW_KEYS = {
  "in the last hour": "demand.window.hour",
  "in the last few hours": "demand.window.hours",
  "in the last day": "demand.window.day",
} as const;

export type DemandLine = {
  /**
   * The state of the room: sold out, nearly gone, over half, or a plain count. This is the limited-space fact,
   * and it belongs with the bar because it is what the bar is drawing.
   */
  room: string;
  /** Other people booking. Social proof, and empty below two, where a count is an admission rather than proof. */
  momentum: string;
  /**
   * The single best line, for somewhere that only has room for one (the home hero badge).
   *
   * 🚨 `room` and `momentum` are DIFFERENT KINDS of fact and must not compete for the same slot. They used to:
   * one ladder produced one sentence, momentum outranked half a room, and since almost every night here has
   * two or more recent bookings the room's own state was never said out loud anywhere. Measured 2026-09-25,
   * with Privilegio at 40 of 80 and the Tuesday open mic at 37 of 60, four surfaces printed "N people
   * reserved in the last day" and not one of them mentioned that half the seats had gone.
   */
  text: string;
  /** Genuinely nearly gone, so the line is worth colouring. */
  tight: boolean;
  /** 0-100, or null when the room is too empty for a bar to be anything but discouraging. */
  fill: number | null;
};

/**
 * The one sentence worth saying about this night, or null when there is nothing honest to say.
 *
 * Order matters: seats running out beats somebody else booking, which beats a plain count. Each rung is a
 * weaker argument than the one above it, and the bottom rung is silence.
 */
export function demandLine(evt: KintanaPublicEvent, locale: Locale): DemandLine | null {
  const d = eventDemand(evt);
  if (!d) return null;

  /**
   * 🚨 A night marked sold out IS sold out, whatever the seat count says. The two disagree all the time and
   * the status is the one that is true: a guest promoter sells a block we never see, so a show can be full at
   * 40 of 80 on our own rows. Reading only the count printed "AGOTADO" next to "over half reserved, worth
   * booking early" and a price, on the same card, for a show nobody could buy (Privilegio, 2026-09-25).
   * Momentum is silenced too: how fast it sold is not an argument for a thing you cannot have.
   */
  if ((evt as unknown as { status?: string }).status === "sold-out") {
    return { room: t(locale, "demand.soldOut"), momentum: "", text: t(locale, "demand.soldOut"),
             tight: true, fill: 100 };
  }

  const gone = d.left === 0;
  // A fifth of the room, capped at ten. A flat "ten left" is nonsense on a small night: a room of three with
  // nothing sold has three left, and announcing "Only 3 seats left of 3" to an empty house is worse than
  // saying nothing, because it is a lie anybody can check by looking at the room.
  const nearlyGone = Math.min(10, Math.max(1, Math.floor(d.capacity * 0.2)));
  const tight = gone || (d.left > 0 && d.left <= nearlyGone);
  // Half a room is a quieter fact than a burst of bookings, but it stays true for longer, so it sits under
  // the recent line and above the plain count. Nothing is said about an empty room: that is not an argument
  // for coming, and a weak number reads as an admission.
  const half = d.capacity > 0 && d.taken / d.capacity >= 0.5;
  let room = "";
  if (gone) {
    room = t(locale, "demand.soldOut");
  } else if (tight) {
    // On the night itself "for tonight" is the stronger fact than "of 60": the seats are going and the show is
    // hours away. Mirrored in the checkout iframe's renderDemand.
    room = d.tonight
      ? t(locale, "demand.leftTonight", { count: String(d.left) })
      : t(locale, "demand.left", { count: String(d.left), total: String(d.capacity) });
  } else if (half) {
    room = t(locale, "demand.half");
  } else if (d.showBar) {
    room = t(locale, "demand.taken", { taken: String(d.taken), total: String(d.capacity) });
  }

  // The owner's own urgency line replaces the counter and its bar (Event.demand_note, ours, not in the SDK's
  // types). Sold out above still wins. Mirrored in the checkout iframe's renderDemand.
  const note = !gone ? (evt as unknown as { demandNote?: string | null }).demandNote?.trim() || "" : "";
  if (note) room = note;

  let momentum = "";
  if (!gone && d.recent >= MIN_RECENT && d.recentWindow in WINDOW_KEYS) {
    const when = t(locale, WINDOW_KEYS[d.recentWindow as keyof typeof WINDOW_KEYS]);
    momentum = t(locale, "demand.recent", { count: String(d.recent), window: when });
  }

  // For one slot only: running out beats somebody else booking, which beats a plain count. Unchanged, so the
  // hero badge reads exactly as it did.
  const text = gone || tight || note ? room : momentum || room;
  if (!text) return null;

  return { room, momentum, text, tight: tight || Boolean(note),
           fill: d.showBar && !note ? Math.min(100, Math.round((d.taken / d.capacity) * 100)) : null };
}

/** Tightest first, matching WINDOWS in `backend/sales/demand.py`; also the tie-break order. */
const WINDOW_ORDER = ["in the last hour", "in the last few hours", "in the last day"];

/**
 * One sentence about the open mics as a whole, rather than one per night.
 *
 * The hero offers two nights side by side, and a line under each of them ("Tue · 2 people reserved in the last
 * few hours", "Wed · 3 people reserved in the last few hours") says the same thing twice and reads as filler.
 * Added together it is a bigger number, one line, and the same fact.
 *
 * The nights are added up over the SAME window, which is the whole reason the API sends every window's count.
 * Summing each night's own chosen window instead and labelling the total with the widest of them undercounts:
 * four Tuesday seats and three Wednesday ones came out as "5 in the last few hours" because Tuesday's own
 * window had narrowed to the hour. It was 7.
 */
export function combinedRecentLine(events: KintanaPublicEvent[], locale: Locale): string | null {
  const counted = events.map(eventDemand).filter((d): d is EventDemand => Boolean(d));
  if (!counted.length) return null;

  // Same rule as one night: the window holding the most bookings, ties to the tighter one.
  let best = 0;
  let window = "";
  for (const candidate of WINDOW_ORDER) {
    const total = counted.reduce((sum, d) => sum + (Number(d.recentByWindow[candidate]) || 0), 0);
    if (total >= MIN_RECENT && total > best) {
      best = total;
      window = candidate;
    }
  }
  if (!window) return null;

  const when = t(locale, WINDOW_KEYS[window as keyof typeof WINDOW_KEYS]);
  return t(locale, "demand.recent", { count: String(best), window: when });
}
