// Loads the built bundle in jsdom and hits the game replay route to surface
// runtime errors. Run after `npx vite build`.
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const distDir = resolve(process.cwd(), "dist");
const html = readFileSync(resolve(distDir, "index.html"), "utf8");

const dom = new JSDOM(html, {
  url: "http://localhost/r/replay-ui-fixture/g/4eb193d9-fc43-487b-868b-54851df77f7a",
  runScripts: "outside-only",
  pretendToBeVisual: true,
});

dom.window.console = console;
dom.window.addEventListener("error", (e) => {
  console.error("window.error:", e.error?.stack || e.message);
});
dom.window.addEventListener("unhandledrejection", (e) => {
  console.error("unhandledrejection:", e.reason?.stack || e.reason);
});

const dataRoot = resolve(process.cwd(), "public/data");
dom.window.fetch = async (url) => {
  const u = String(url).replace(/^https?:\/\/localhost/, "");
  if (!u.startsWith("/data/")) {
    return { ok: false, status: 404, json: async () => ({}) };
  }
  const p = resolve(dataRoot, u.slice("/data/".length));
  try {
    const text = readFileSync(p, "utf8");
    return {
      ok: true,
      status: 200,
      json: async () => JSON.parse(text),
    };
  } catch (e) {
    return { ok: false, status: 404, json: async () => ({}) };
  }
};

const scriptMatch = html.match(/src="([^"]+\.js)"/);
if (!scriptMatch) {
  console.error("could not find bundle in index.html");
  process.exit(1);
}
const bundlePath = resolve(distDir, scriptMatch[1].replace(/^\//, ""));
const bundle = readFileSync(bundlePath, "utf8");

dom.window.eval(bundle);

await new Promise((r) => setTimeout(r, 1500));

const root = dom.window.document.getElementById("root");
console.log("--- root innerHTML head ---");
console.log(root?.innerHTML?.slice(0, 2000));
