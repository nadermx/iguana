/**
 * The owner's agent chat, /chat/, in a real browser (docs/chat-agent.md).
 *
 *   node tests/chat-e2e.mjs --pass "$(cat ~/.credentials/vpsorg/iguanacomedy/owner_password)"
 *   node tests/chat-e2e.mjs --pass ... --send "Reply with the word pong and nothing else."   one real round trip
 *   node tests/chat-e2e.mjs --base http://127.0.0.1:8000 --user admin --pass ...              a local runserver
 *
 * Always: signed out, /chat/ goes to the admin login and the JSON endpoints answer 403; the floor account
 * (`mesero`, with --floor-pass) is turned away; signed in as the owner, both languages render at 320 and 1280
 * wide without horizontal overflow. --send also posts one message and waits up to 5 minutes for a finished
 * reply (it uses the club's Claude subscription, so only when the agent itself is being checked).
 * Screenshots land in build/e2e/.
 */

import { mkdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const args = process.argv.slice(2);
const argOf = (name, fallback) => {
  const i = args.indexOf(name);
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback;
};
const BASE = argOf("--base", "https://iguanacomedy.com").replace(/\/$/, "");
const OUT = path.resolve(argOf("--out", "build/e2e"));
const USER = argOf("--user", "iguana");
const PASS = argOf("--pass", "");
const FLOOR_PASS = argOf("--floor-pass", "");
const SEND = argOf("--send", "");
if (!PASS) {
  console.error("--pass <owner password> is required");
  process.exit(2);
}

const failures = [];
const fail = (msg) => {
  failures.push(msg);
  console.log(`FAIL ${msg}`);
};

async function signIn(context, user, pass) {
  const page = await context.newPage();
  await page.goto(`${BASE}/chat/`);
  if (!page.url().includes("/admin/login/")) fail(`signed out, /chat/ did not go to the login (${page.url()})`);
  await page.fill("#id_username", user);
  await page.fill("#id_password", pass);
  await Promise.all([page.waitForLoadState("load"), page.click("input[type=submit]")]);
  return page;
}

await mkdir(OUT, { recursive: true });
const browser = await chromium.launch();

// Signed out: the JSON endpoints refuse outright rather than redirect.
{
  const context = await browser.newContext();
  const res = await context.request.post(`${BASE}/chat/send/`, { data: { prompt: "x" } });
  if (res.status() !== 403) fail(`signed out, /chat/send/ answered ${res.status()}`);
  await context.close();
}

if (FLOOR_PASS) {
  const context = await browser.newContext();
  const page = await signIn(context, "mesero", FLOOR_PASS);
  await page.goto(`${BASE}/chat/`);
  if (!page.url().includes("/admin/login/")) fail("the floor account reached /chat/");
  await context.close();
}

const context = await browser.newContext();
const page = await signIn(context, USER, PASS);
if (!page.url().endsWith("/chat/")) fail(`owner sign-in landed on ${page.url()}`);

for (const [lang, header, words] of [["en", "en-US", "New conversation"], ["es", "es-MX", "Conversación nueva"]]) {
  await context.setExtraHTTPHeaders({ "Accept-Language": header });
  for (const width of [320, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    const res = await page.goto(`${BASE}/chat/?new=1`);
    if (res.status() !== 200) fail(`${lang} ${width}: status ${res.status()}`);
    const text = (await page.textContent("body")) || "";
    if (!text.includes(words)) fail(`${lang} ${width}: "${words}" missing`);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    if (overflow > 0) fail(`${lang} ${width}: page overflows by ${overflow}px`);
    if (!(await page.isVisible("#prompt"))) fail(`${lang} ${width}: no message box`);
    await page.screenshot({ path: path.join(OUT, `chat-${lang}-${width}.png`), fullPage: true });
  }
}

if (SEND) {
  await context.setExtraHTTPHeaders({ "Accept-Language": "en-US" });
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto(`${BASE}/chat/?new=1`);
  await page.fill("#prompt", SEND);
  await page.click("#send");
  const started = Date.now();
  let state = null;
  while (Date.now() - started < 5 * 60 * 1000) {
    await page.waitForTimeout(3000);
    const conversation = new URL(page.url()).searchParams.get("c");
    if (!conversation) continue;
    const res = await context.request.get(`${BASE}/chat/${conversation}/turns/`);
    const turns = (await res.json()).turns;
    state = turns[turns.length - 1];
    if (state && state.finished) break;
  }
  await page.screenshot({ path: path.join(OUT, "chat-round-trip.png"), fullPage: true });
  if (!state || !state.finished) fail("no finished reply within 5 minutes");
  else if (state.status !== "done") fail(`the turn ${state.status}: ${state.error}`);
  else console.log(`reply: ${state.reply.slice(0, 200)}`);
}

await browser.close();
console.log(failures.length ? `${failures.length} failure(s)` : "chat e2e: all checks passed");
process.exit(failures.length ? 1 : 0);
