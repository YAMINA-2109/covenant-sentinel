// Automated UI screenshots for design QA and README assets.
// Usage: node scripts/screenshot.mjs <url> <outPath> [waitSelector]
//   FULLPAGE=1  -> capture the full page height
// Example:
//   node scripts/screenshot.mjs "http://localhost:5173/?run=<id>" ../docs/final.png "text=Audit complete"
import { chromium } from "playwright";

const [url, outPath, waitSelector] = process.argv.slice(2);
if (!url || !outPath) {
  console.error("usage: node scripts/screenshot.mjs <url> <outPath> [waitSelector]");
  process.exit(1);
}

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1720, height: 960 },
  deviceScaleFactor: 2,
  colorScheme: "dark",
});
await page.goto(url, { waitUntil: "networkidle" });
if (waitSelector) {
  await page.waitForSelector(waitSelector, { timeout: 45000 }).catch(() => {
    console.warn(`waitSelector not found in time: ${waitSelector}`);
  });
}
await page.waitForTimeout(1500);
await page.screenshot({ path: outPath, fullPage: process.env.FULLPAGE === "1" });
await browser.close();
console.log("saved", outPath);
