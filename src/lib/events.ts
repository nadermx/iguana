import type { KintanaPublicEvent } from "@kintana/sdk";
import { slugify } from "./slug";
import { localizePath } from "../i18n/routes";
import type { Locale } from "../i18n/locale";
import { t } from "../i18n/ui";

/** Best-effort city slug derived from ticketing rows. */
export function eventCitySlug(event: KintanaPublicEvent): string {
  return slugify(event.venue?.city ?? event.city);
}

/** On-site checkout route (hydrated by `data-kintana-widget` + `/_t/k.js`). */
export function eventTicketsPath(event: Pick<KintanaPublicEvent, "slug" | "id">, locale: Locale = "en"): string | null {
  const key = event.slug?.trim() || event.id?.trim();
  return key ? localizePath(locale, "eventTickets", { slug: key }) : null;
}

/** True when the event detail page can mount the embedded checkout widget.
 *
 * A guest promoter's show in our room sells on their own site: it is EXTERNAL, and mounting our checkout on it
 * both fails and hides the only link that can actually sell a ticket. */
export function eventSupportsOnSiteCheckout(
  event: Pick<KintanaPublicEvent, "id" | "status" | "ticketingType">
): boolean {
  if (event.ticketingType === "EXTERNAL") return false;
  // A show that has happened sells nothing: the checkout comes down the day after, not when somebody notices.
  return (
    Boolean(event.id?.trim()) && event.status !== "sold-out" && event.status !== "postponed" && event.status !== "past"
  );
}

/** Whether the checkout will draw a card form, which decides how much height the page reserves for it.
 *
 * Only the backend can answer it: it depends on Stripe keys being configured and on the ticket types being
 * paid online rather than at the door. The SDK's event type predates the field, hence the cast. */
export function eventCollectsPayment(event: KintanaPublicEvent): boolean {
  return (event as { collectsPayment?: boolean }).collectsPayment === true;
}

/** How many ticket rows the checkout will list; each one adds a row above the form. */
export function eventTicketTypeCount(event: KintanaPublicEvent): number {
  const n = (event as { ticketTypeCount?: number }).ticketTypeCount;
  return typeof n === "number" && n > 0 ? n : 1;
}

/** `YYYY-MM-DD` for today in Quintana Roo, where every show happens; the API's `from` filter and "past" use it. */
export function todayInCancun(now = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Cancun" }).format(now);
}

export function sortEventsAscending(events: KintanaPublicEvent[]): KintanaPublicEvent[] {
  return [...events].sort((a, b) => parseEventTs(a.date) - parseEventTs(b.date));
}

export function sortEventsDescending(events: KintanaPublicEvent[]): KintanaPublicEvent[] {
  return [...events].sort((a, b) => parseEventTs(b.date) - parseEventTs(a.date));
}

/** Local midnight today. Kept for callers outside the calendar; the calendar itself compares Cancun days. */
export function startOfTodayMs(now = new Date()): number {
  return new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
}

/**
 * Past or upcoming by the CANCUN calendar day, never the server clock. The server runs in UTC, so comparing a
 * show's `YYYY-MM-DD` against UTC midnight dropped every show from the upcoming list at 19:00 Playa time on its
 * own day, the two hours before doors when walk-up buyers look (found on Zach McGovern in Tulum, 2026-11-23).
 */
function eventDay(event: KintanaPublicEvent): string {
  return (event.date || "").slice(0, 10);
}

export function isPastEvent(event: KintanaPublicEvent, today = todayInCancun()): boolean {
  if (event.status === "cancelled") return false;
  if (event.status === "past") return true;
  const day = eventDay(event);
  return /^\d{4}-\d{2}-\d{2}$/.test(day) && day < today;
}

export function isUpcomingEvent(event: KintanaPublicEvent, today = todayInCancun()): boolean {
  if (event.status === "cancelled") return false;
  if (event.status === "past") return false;
  const day = eventDay(event);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return true;
  return day >= today;
}

export function partitionEventsBySchedule(events: readonly KintanaPublicEvent[]) {
  const today = todayInCancun();
  const upcoming: KintanaPublicEvent[] = [];
  const past: KintanaPublicEvent[] = [];
  for (const event of events) {
    if (isPastEvent(event, today)) past.push(event);
    else if (isUpcomingEvent(event, today)) upcoming.push(event);
  }
  return { upcoming, past };
}

export function parseEventTs(isoLike: string): number {
  const t = Date.parse(isoLike);
  return Number.isFinite(t) ? t : Number.POSITIVE_INFINITY;
}

function ordinalDay(day: number): string {
  const mod100 = day % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${day}th`;
  switch (day % 10) {
    case 1:
      return `${day}st`;
    case 2:
      return `${day}nd`;
    case 3:
      return `${day}rd`;
    default:
      return `${day}th`;
  }
}

/**
 * "Tue 23 Sep", for a row of choices rather than a heading.
 *
 * The full form carries the year, which four dates inside a month do not need, and it wrapped the night pills
 * onto a second row. That row pushed the reserve button further down a page whose whole job is that button.
 * The weekday earns its place: the choice being made is which night, not which date.
 */
export function formatEventDateShort(dateInput: string, locale: Locale = "en"): string {
  const parsed = eventCalendarDate(dateInput);
  if (!parsed) return formatEventDate(dateInput, locale);
  return new Intl.DateTimeFormat(locale === "es" ? "es-MX" : "en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
  }).format(parsed);
}

/** e.g. `2026-05-18` → `18th May, 2026` */
export function formatEventDate(dateInput: string, locale: Locale = "en"): string {
  const raw = dateInput.trim();
  const fmtLocale = locale === "es" ? "es-MX" : "en-GB";
  const isoDay = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
  if (isoDay) {
    const year = Number(isoDay[1]);
    const monthIndex = Number(isoDay[2]) - 1;
    const day = Number(isoDay[3]);
    const month = new Intl.DateTimeFormat(fmtLocale, { month: "short" }).format(new Date(year, monthIndex, day));
    return locale === "es" ? `${day} ${month}, ${year}` : `${ordinalDay(day)} ${month}, ${year}`;
  }

  const t = Date.parse(raw);
  if (!Number.isFinite(t)) return dateInput;
  const d = new Date(t);
  const month = new Intl.DateTimeFormat(fmtLocale, { month: "short" }).format(d);
  return locale === "es" ? `${d.getDate()} ${month}, ${d.getFullYear()}` : `${ordinalDay(d.getDate())} ${month}, ${d.getFullYear()}`;
}

function getTimeFormatter(locale: Locale) {
  return new Intl.DateTimeFormat(locale === "es" ? "es-MX" : "en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

/** e.g. `15:00` → `3:00 PM` */
export function formatEventTime(timeInput: string | null | undefined, locale: Locale = "en"): string | null {
  if (!timeInput?.trim()) return null;
  const raw = timeInput.trim();
  const timeFormatter = getTimeFormatter(locale);

  if (/\b(am|pm)\b/i.test(raw)) {
    const d = new Date(`1970-01-01 ${raw}`);
    if (!Number.isNaN(d.getTime())) return timeFormatter.format(d);
    return raw;
  }

  const clock = /^(\d{1,2}):(\d{2})(?::\d{2})?$/.exec(raw);
  if (clock) {
    const hours24 = Number(clock[1]);
    const minutes = Number(clock[2]);
    if (hours24 > 23 || minutes > 59) return raw;
    if (locale === "es") return timeFormatter.format(new Date(1970, 0, 1, hours24, minutes));
    const period = hours24 >= 12 ? "PM" : "AM";
    const hours12 = hours24 % 12 || 12;
    return `${hours12}:${String(minutes).padStart(2, "0")} ${period}`;
  }

  const parsed = Date.parse(raw);
  if (Number.isFinite(parsed)) return timeFormatter.format(new Date(parsed));

  return raw;
}

export function formatEventScheduleLine(
  event: Pick<KintanaPublicEvent, "date" | "doorsOpen" | "showTime">,
  locale: Locale = "en"
): string {
  const parts = [formatEventDate(event.date, locale)];
  const doors = formatEventTime(event.doorsOpen, locale);
  const show = formatEventTime(event.showTime, locale);
  if (doors) parts.push(locale === "es" ? `puertas ${doors}` : `doors ${doors}`);
  if (show) parts.push(locale === "es" ? `show ${show}` : `show ${show}`);
  return parts.join(" · ");
}

/** Human-readable show language for listings (defaults to English). */
export function eventLanguageLabel(
  event: Pick<KintanaPublicEvent, "language">,
  locale: Locale = "en"
): string {
  return event.language === "es"
    ? locale === "es"
      ? "Español"
      : "Spanish"
    : locale === "es"
      ? "Inglés"
      : "English";
}

/** Formatted money from ticketing minor units (`priceFrom`) when present on the event payload. */
export function formatMinorUnitsPrice(
  event: Pick<KintanaPublicEvent, "priceFrom" | "priceCurrency">,
  locale: Locale = "en"
): string | null {
  if (event.priceFrom == null) return null;
  const currency = (event.priceCurrency?.trim() || "USD").toUpperCase();
  const major = event.priceFrom / 100;
  const digits = major % 1 === 0 ? major.toFixed(0) : major.toFixed(2);
  try {
    const amount = new Intl.NumberFormat(locale === "es" ? "es-MX" : "en-US", {
      style: "currency",
      currency,
      maximumFractionDigits: major % 1 === 0 ? 0 : 2,
    }).format(major);
    // es-MX prints MXN as a bare "$50", which is ambiguous next to dollar prices, so name the currency. When the
    // formatter already spells it out ("USD 5", "MX$50") do not say it twice.
    return amount.includes(currency) || amount.includes(currency.slice(0, 2)) ? amount : `${amount} ${currency}`;
  } catch {
    return `$${digits} ${currency}`;
  }
}

/** Returns "Month YYYY" in locale. */
export function monthLabel(dateInput: string, locale: Locale = "en"): string {
  const d = Date.parse(dateInput);
  if (!Number.isFinite(d)) return locale === "es" ? "Pronto" : "Soon";
  return new Intl.DateTimeFormat(locale === "es" ? "es-MX" : "en-US", { month: "long", year: "numeric" }).format(new Date(d));
}

/** "YYYY-MM" for an event date. The API sends the Cancun calendar day, so a plain date is read as written: parsing
 * it as an instant would put it at UTC midnight, which is the day before in Cancun. */
export function eventMonthKey(dateInput: string): string {
  const raw = dateInput.trim();
  if (/^\d{4}-\d{2}-\d{2}/.test(raw)) return raw.slice(0, 7);
  const parsed = Date.parse(raw);
  if (!Number.isFinite(parsed)) return "";
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Cancun", year: "numeric", month: "2-digit" })
    .format(new Date(parsed))
    .slice(0, 7);
}

/** The event's own calendar day as a local Date, safe to format with weekday/day. */
export function eventCalendarDate(dateInput: string): Date | null {
  const raw = dateInput.trim();
  const parts = /^(\d{4})-(\d{2})-(\d{2})/.exec(raw);
  if (parts) return new Date(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3]));
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? new Date(parsed) : null;
}

export function currentMonthKey(now = new Date()): string {
  return todayInCancun(now).slice(0, 7);
}

/** This month's shows first, everything later behind the expandable calendar. */
export function splitByCurrentMonth(events: readonly KintanaPublicEvent[], now = new Date()) {
  const key = currentMonthKey(now);
  const sorted = sortEventsAscending([...events]);
  return {
    thisMonth: sorted.filter((event) => eventMonthKey(event.date) === key),
    later: sorted.filter((event) => eventMonthKey(event.date) !== key),
  };
}

export function groupEventsByMonth(
  events: KintanaPublicEvent[],
  order: "asc" | "desc" = "asc",
  locale: Locale = "en"
): Map<string, KintanaPublicEvent[]> {
  const sorted = order === "desc" ? sortEventsDescending(events) : sortEventsAscending(events);
  const map = new Map<string, KintanaPublicEvent[]>();
  for (const event of sorted) {
    const bucket = monthLabel(event.date, locale);
    const row = map.get(bucket) ?? [];
    row.push(event);
    map.set(bucket, row);
  }
  return map;
}

/** What happened at a show that is over (`past` from the API), or null while it is still to come. */
export interface PastSummary {
  soldOut: boolean;
  seats: number;
  capacity: number | null;
}

export function pastSummary(event: KintanaPublicEvent | null | undefined): PastSummary | null {
  if (!event || event.status !== "past") return null;
  const raw = (event as unknown as { past?: PastSummary | null }).past;
  return raw ?? { soldOut: false, seats: 0, capacity: null };
}

/** "76 of 80 tickets sold" / "16 lugares reservados", or null when we counted nothing (older imported shows). */
export function pastSeatsLine(summary: PastSummary, locale: Locale, free: boolean): string | null {
  if (!summary.seats) return null;
  const n = String(summary.seats);
  if (summary.capacity) {
    return t(locale, free ? "events.pastSeatsOf" : "events.pastTicketsOf", { n, capacity: String(summary.capacity) });
  }
  return t(locale, free ? "events.pastSeats" : "events.pastTickets", { n });
}
