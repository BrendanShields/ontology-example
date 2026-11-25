// Proves that advancing the deck plays the motion between two holds instead of cutting.
// Usage: node tools/glide-check.mjs <present-url> <puppeteer-core-dir> <chrome-binary> [out-dir]
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const [url, puppeteerDir, chrome, outDir = "/tmp/deck-glide"] = process.argv.slice(2);
const puppeteer = createRequire(path.join(puppeteerDir, "package.json"))(puppeteerDir);
fs.mkdirSync(outDir, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: chrome,
  headless: true,
  args: ["--window-size=1280,720"],
  defaultViewport: { width: 1280, height: 720 },
});
const page = await browser.newPage();
const logs = [];
page.on("console", (m) => logs.push(m.text()));
page.on("pageerror", (e) => logs.push("pageerror: " + e.message));
await page.goto(url, { waitUntil: "networkidle0" });
await new Promise((r) => setTimeout(r, 2500));

const deckFrame = () => page.frames().find((f) => f.url().includes("/composition/"));
const masterTime = () => deckFrame().evaluate(() => window.__deck.master.time());
const snap = (target, file) =>
  Promise.race([
    target.screenshot({ path: path.join(outDir, file) }).catch(() => {}),
    new Promise((r) => setTimeout(r, 10000)),
  ]);
const assert = (ok, message) => {
  console.log((ok ? "ok   " : "FAIL ") + message);
  if (!ok) process.exitCode = 1;
};

assert(!!deckFrame(), "the composition loaded inside the presenter");
const step = await deckFrame().evaluate(() => window.__deck.step);
assert(Math.abs(await masterTime()) < 0.01, "the deck opens on the first hold");

await page.focus("hyperframes-slideshow");
const samples = [];
await page.keyboard.press("ArrowRight");
for (let i = 0; i < 8; i++) {
  await new Promise((r) => setTimeout(r, 120));
  samples.push(await masterTime());
  await snap(page, `advance-${i}.png`);
}
const moving = samples.filter((t) => t > 0.06 && t < step - 0.01);
assert(moving.length >= 3, `advancing plays through the step (sampled ${samples.map((t) => t.toFixed(2)).join(", ")})`);
assert(samples.every((t, i) => i === 0 || t >= samples[i - 1]), "the playhead only moves forward during an advance");

await new Promise((r) => setTimeout(r, 2600));
assert(Math.abs((await masterTime()) - step) < 0.03, "the advance settles exactly on the next hold");

const glances = new Set();
for (let i = 0; i < 18; i++) {
  await new Promise((r) => setTimeout(r, 300));
  glances.add(await deckFrame().evaluate(() => document.querySelector('[data-idle="look"]').getAttribute("transform")));
}
assert(glances.size > 1, "the agent keeps moving while the deck rests on a hold");

await page.keyboard.press("ArrowRight");
await new Promise((r) => setTimeout(r, 3400));
let lit = 0;
for (let i = 0; i < 8; i++) {
  await new Promise((r) => setTimeout(r, 200));
  lit += await deckFrame().evaluate(
    () => [...document.querySelectorAll('[data-idle="hop"] circle')].filter((c) => c.style.opacity === "1").length,
  );
}
assert(lit > 0, "candidate endpoints light up in turn on the many-paths hold");
await snap(page, "idle-paths.png");

for (let i = 0; i < 3; i++) await page.keyboard.press("ArrowRight");
await new Promise((r) => setTimeout(r, 3200));
const afterBurst = await masterTime();
assert(Math.abs(afterBurst / step - Math.round(afterBurst / step)) < 0.02, `a burst of presses settles on a hold (${afterBurst.toFixed(2)} s)`);
await snap(page, "after-burst.png");

await page.keyboard.press("ArrowLeft");
await new Promise((r) => setTimeout(r, 900));
const back = await masterTime();
assert(back < afterBurst, `stepping back lands on an earlier hold (${back.toFixed(2)} s)`);
await snap(page, "after-back.png");

await page.keyboard.press("p");
await new Promise((r) => setTimeout(r, 3000));
const audience = (await browser.pages()).find((p) => p.url().includes("mode=audience"));
assert(!!audience, "pressing P opens the audience window");
if (audience) {
  await page.bringToFront();
  await page.focus("hyperframes-slideshow");
  await page.keyboard.press("ArrowRight");
  await new Promise((r) => setTimeout(r, 5000));
  const presenterTime = await masterTime();
  const audienceTime = await audience
    .frames()
    .find((f) => f.url().includes("/composition/"))
    .evaluate(() => window.__deck.master.time());
  assert(Math.abs(presenterTime - audienceTime) < 0.03, `presenter and audience settle on the same hold (${presenterTime.toFixed(2)} s, ${audienceTime.toFixed(2)} s)`);
  assert(presenterTime > back, "the presenter advanced while the audience window was open");
  await snap(page, "two-window-presenter.png");
}

const fresh = await browser.newPage();
await fresh.goto(url, { waitUntil: "networkidle0" });
await new Promise((r) => setTimeout(r, 3500));
const freshTime = () =>
  fresh
    .frames()
    .find((f) => f.url().includes("/composition/"))
    .evaluate(() => window.__deck.master.time());
const before = await freshTime();
await fresh.keyboard.press("Space");
await new Promise((r) => setTimeout(r, 2500));
const afterSpace = await freshTime();
console.log(`note Space on a fresh load, before any click: ${afterSpace > before ? "advances" : "does nothing"}`);
await fresh.mouse.click(640, 360);
await fresh.keyboard.press("Space");
await new Promise((r) => setTimeout(r, 2500));
assert((await freshTime()) > before, "Space advances once the deck has been clicked");

// Walk the whole deck forward, then back, and compare each slide's first hold both ways.
if (process.argv.includes("--walk")) {
  const walk = await browser.newPage();
  walk.on("console", (m) => logs.push(m.text()));
  await walk.goto(url, { waitUntil: "networkidle0" });
  await new Promise((r) => setTimeout(r, 3500));
  await walk.mouse.click(640, 300);
  const frame = () => walk.frames().find((f) => f.url().includes("/composition/"));
  const plan = await frame().evaluate(() => {
    let first = 0;
    return [...document.querySelectorAll("#deck .slide")].map((s) => {
      const entry = { id: s.id, first, holds: Number(s.dataset.holds) };
      first += entry.holds;
      return entry;
    });
  });
  const settle = async (hold) => {
    for (let i = 0; i < 80; i++) {
      const t = await frame().evaluate(() => window.__deck.master.time());
      if (Math.abs(t - hold * step) < 0.03) return true;
      await new Promise((r) => setTimeout(r, 100));
    }
    return false;
  };
  const state = (id) =>
    frame().evaluate((slideId) => {
      const round = (v) => Math.round(parseFloat(v) * 100) / 100;
      const rows = [];
      const slide = document.getElementById(slideId);
      slide.querySelectorAll("[data-b], [data-x], [data-shift-b], .in, .body, .ref").forEach((el) => {
        if (el.closest("[data-idle]") || el.classList.contains("mk")) return;
        const cs = getComputedStyle(el);
        // An element that is not showing has no state worth comparing.
        if (round(cs.opacity) === 0) return rows.push("hidden");
        rows.push([round(cs.opacity), cs.transform === "none" || cs.transform === "matrix(1, 0, 0, 1, 0, 0)" ? "" : cs.transform.replace(/-?[\d.]+/g, (n) => round(n)), round(cs.strokeDashoffset) || 0].join("|"));
      });
      const m = getComputedStyle(document.getElementById("marker")).transform.replace(/-?[\d.]+/g, (n) => round(n));
      return rows.join(";") + "#" + m + "#" + getComputedStyle(slide).visibility;
    }, id);
  const total = plan.reduce((n, s) => n + s.holds, 0);
  const forward = {};
  let stuck = null;
  for (let hold = 0; hold < total; hold++) {
    if (hold > 0) await walk.keyboard.press("ArrowRight");
    if (!(await settle(hold))) {
      stuck = hold;
      break;
    }
    const slide = plan.find((s) => s.first === hold);
    if (slide) forward[slide.id] = await state(slide.id);
  }
  assert(stuck === null, stuck === null ? `every one of the ${total} holds is reached going forward` : `hold ${stuck} was never reached`);
  const differs = [];
  for (let i = plan.length - 2; i >= 0 && stuck === null; i--) {
    await walk.keyboard.press("ArrowLeft");
    await settle(plan[i].first);
    await new Promise((r) => setTimeout(r, 500));
    if ((await state(plan[i].id)) !== forward[plan[i].id]) differs.push(plan[i].id);
  }
  assert(differs.length === 0, "stepping back restores every slide's first hold exactly" + (differs.length ? ": differs on " + differs.join(", ") : ""));
  await walk.close();
}

const bad = logs.filter((l) => /error|invalid|gsap|\[deck\]/i.test(l));
assert(bad.length === 0, "no console errors or deck warnings" + (bad.length ? ": " + bad.join(" | ") : ""));
await browser.close();
