import { createKintanaClient } from "@kintana/sdk";
import type { KintanaPublicArtistEmbed, KintanaPublicEvent } from "@kintana/sdk";

import { eventCitySlug, sortEventsAscending, todayInCancun } from "./events";
import { createLocalizedKintanaClient, getKintanaEnv } from "./kintana-env";
import { logKintanaError, logKintanaSuccess } from "./kintana-error";
import { isOpenMic, nextBookableOpenMics } from "./open-mics";

/** Cards on the home page: two rows of two on a wide screen. */
const HOME_EVENT_SLOTS = 4;
import type { Locale } from "../i18n/locale";

export type HomePageData = {
  hasCredentials: boolean;
  eventsPool: KintanaPublicEvent[];
  artistsPool: KintanaPublicArtistEmbed[];
  eventsCatalogFailed: boolean;
  performersCatalogFailed: boolean;
  trimmedEvents: KintanaPublicEvent[];
  wallArtists: KintanaPublicArtistEmbed[];
};

export async function loadHomePageData(citySlug?: string, locale?: Locale): Promise<HomePageData> {
  const { apiKey, baseUrl, hasCredentials } = getKintanaEnv();

  let eventsPool: KintanaPublicEvent[] = [];
  let artistsPool: KintanaPublicArtistEmbed[] = [];
  let eventsCatalogFailed = false;
  let performersCatalogFailed = false;

  if (hasCredentials) {
    const client = createLocalizedKintanaClient(locale ?? "en");

    try {
      eventsPool = await client.listEvents({ limit: 40, from: todayInCancun() });
      logKintanaSuccess("listEvents", eventsPool.length);
    } catch (err) {
      logKintanaError("listEvents", err);
      eventsCatalogFailed = true;
      eventsPool = [];
    }

    try {
      artistsPool = await client.listArtists({ limit: 36 });
      logKintanaSuccess("listArtists", artistsPool.length);
    } catch (err) {
      logKintanaError("listArtists", err);
      performersCatalogFailed = true;
      artistsPool = [];
    }
  }

  const slug = citySlug?.trim() ?? "";
  // The API marks a show "past" once its day has ended in Cancún, so this holds whatever timezone the server runs in.
  // Weekly open mics would crowd out the ticketed shows, so they are held back here and topped up at the end.
  let cityFiltered = sortEventsAscending(
    eventsPool.filter((evt) => evt.status !== "cancelled" && evt.status !== "past" && !isOpenMic(evt)),
  );
  if (slug.length) {
    cityFiltered = cityFiltered.filter((evt) => eventCitySlug(evt) === slug);
  }

  // Each language's visitors see their own shows first: the next open mic in the page's language joins the list, and
  // shows in that language come before the rest (date order within each group), so /es/ leads with Spanish nights
  // and /en/ with English ones while both still list everything.
  const nextOpenMic = locale ? nextBookableOpenMics(eventsPool)[locale] : undefined;
  const withOpenMic = sortEventsAscending(
    nextOpenMic && (!slug.length || eventCitySlug(nextOpenMic) === slug) ? [...cityFiltered, nextOpenMic] : cityFiltered,
  );
  const byLanguage = locale
    ? [...withOpenMic.filter((evt) => evt.language === locale), ...withOpenMic.filter((evt) => evt.language !== locale)]
    : withOpenMic;
  const prioritized = [
    ...byLanguage.filter((evt) => evt.status === "on-sale"),
    ...byLanguage.filter((evt) => evt.status !== "on-sale"),
  ];

  // Most weeks the only shows are the two open mics, and holding all but one of them back left the grid with a
  // single card. Top the row up with the open mics that come next, soonest first, so the home page always offers
  // a full set of nights to pick from.
  const chosen = new Set(prioritized.map((evt) => evt.id));
  const spare = sortEventsAscending(
    eventsPool.filter(
      (evt) =>
        isOpenMic(evt) &&
        evt.status !== "cancelled" &&
        evt.status !== "past" &&
        !chosen.has(evt.id) &&
        (!slug.length || eventCitySlug(evt) === slug),
    ),
  );
  // The language and on-sale order above decides WHICH nights get a slot; the grid itself reads by date, sold-out
  // nights in their place, because a calendar that runs next Tuesday before tonight reads as broken (owner, 2026-10-20).
  const filled = sortEventsAscending([...prioritized, ...spare].slice(0, HOME_EVENT_SLOTS));

  return {
    hasCredentials,
    eventsPool,
    artistsPool,
    eventsCatalogFailed,
    performersCatalogFailed,
    trimmedEvents: filled,
    wallArtists: artistsPool.slice(0, 3),
  };
}
