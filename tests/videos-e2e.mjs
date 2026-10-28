// /upload/ in pieces and /videos/ on a phone (390px), end to end against production or a local pair.
//   node tests/videos-e2e.mjs --file <video> --pin <drop pin> --pass <owner password> [--base https://iguanacomedy.com] [--keep]
// Uploads the file "For the site", waits for its web copy on /videos/, checks the page fits the screen, then
// deletes it (unless --keep). The upload sends one "/upload/: 1 item(s) received" mail to hello@.
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const args = process.argv.slice(2);
const arg = (name, fallback) => { const i = args.indexOf(`--${name}`); return i >= 0 ? args[i + 1] : fallback; };
const base = arg("base", "https://iguanacomedy.com").replace(/\/$/, "");
const file = arg("file"), pin = arg("pin"), pass = arg("pass"), out = arg("out", "/tmp");
if (!file || !pin || !pass) { console.error("need --file --pin --pass"); process.exit(2); }
const name = path.basename(file);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
const fits = async (label) => {
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  if (over > 1) throw new Error(`${label}: page is ${over}px wider than the phone`);
};
let failed = false;
try {
  await page.goto(`${base}/upload/?lang=en`);
  await page.fill("#pin", pin);
  await Promise.all([page.waitForNavigation(), page.click("button[type=submit]")]);
  await fits("/upload/");
  await page.selectOption("#kind", "site");
  await page.setInputFiles("#files", file);
  await page.fill("#note", "e2e test, delete me");
  const started = Date.now();
  await Promise.all([page.waitForURL(/sent=site/, { timeout: 600000 }), page.click("#send")]);
  console.log(`upload ok in ${((Date.now() - started) / 1000).toFixed(1)}s`);
  await page.screenshot({ path: `${out}/videos-e2e-upload.png`, fullPage: true });

  await page.goto(`${base}/admin/login/?next=/videos/`);
  await page.fill("#id_username", "iguana");
  await page.fill("#id_password", pass);
  await Promise.all([page.waitForNavigation(), page.click("input[type=submit]")]);
  const card = page.locator("section.vid", { hasText: name }).first();
  for (let i = 0; i < 60; i++) {
    await page.goto(`${base}/videos/?lang=en`);
    if (await card.locator("video").count()) break;
    if (await card.locator(".bad").count()) throw new Error("conversion failed: " + (await card.locator(".bad").innerText()));
    await page.waitForTimeout(5000);
  }
  const src = await card.locator("video").getAttribute("src");
  if (!src) throw new Error("no web copy after 5 minutes");
  const head = await page.request.get(base + src, { headers: { Range: "bytes=0-99" } });
  if (head.status() !== 206) throw new Error(`web copy answered ${head.status()} to a range request`);
  console.log("web copy ok", src);
  await fits("/videos/");
  await page.screenshot({ path: `${out}/videos-e2e-list.png`, fullPage: true });
  await page.goto(`${base}/es/videos/`);
  await fits("/es/videos/");
  if (!args.includes("--keep")) {
    await page.goto(`${base}/videos/?lang=en`);
    page.once("dialog", (d) => d.accept());
    await card.locator("summary", { hasText: "More" }).click();
    await Promise.all([page.waitForNavigation(), card.locator("button.danger").click()]);
    if (await page.locator("section.vid", { hasText: name }).count()) throw new Error("delete did not remove it");
    console.log("deleted");
  }
} catch (e) {
  failed = true;
  console.error("FAIL", e.message);
  await page.screenshot({ path: `${out}/videos-e2e-fail.png`, fullPage: true }).catch(() => {});
} finally {
  await browser.close();
}
process.exit(failed ? 1 : 0);
