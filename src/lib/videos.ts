/**
 * The videos the owner ticked "Show on the site" on /videos/ (backend api/videos_views.py). The backend makes a
 * web copy of each upload (H.264 MP4 with a poster frame) and serves it from /site-videos/ on this domain.
 */

export type SiteVideo = { id: string; title: string; url: string; poster: string | null; duration: number | null };

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
