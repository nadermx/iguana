/**
 * The videos the owner ticked "Show on the site" on /videos/ (backend api/videos_views.py). The backend makes a
 * web copy of each upload (H.264 MP4 with a poster frame) and serves it from /site-videos/ on this domain.
 */

export type SiteVideo = {
  id: string;
  title: string;
  url: string;
  poster: string | null;
  duration: number | null;
  /** Who is on stage, from the AI clip finder or typed on /videos/. Empty for a general video. */
  comedian: string;
  /** A short cut for phones (1080x1920). */
  vertical: boolean;
};

/** Videos in their order, grouped by comedian; the group with no name (general videos) comes first. */
export function byComedian(videos: SiteVideo[]): { comedian: string; videos: SiteVideo[] }[] {
  const groups = new Map<string, SiteVideo[]>();
  for (const video of videos) {
    const key = video.comedian || "";
    groups.set(key, [...(groups.get(key) ?? []), video]);
  }
  return [...groups.entries()].map(([comedian, items]) => ({ comedian, videos: items }));
}

export async function loadVideos(baseUrl: string, apiKey: string, locale: "en" | "es"): Promise<SiteVideo[] | null> {
  try {
    const response = await fetch(`${baseUrl.replace(/\/$/, "")}/api/public/v1/videos?locale=${locale}`, {
      headers: { Authorization: `Bearer ${apiKey}` },
    });
    if (!response.ok) return null;
    return ((await response.json()) as { videos: SiteVideo[] }).videos;
  } catch {
    return null;
  }
}
