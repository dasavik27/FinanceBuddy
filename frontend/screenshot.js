const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({ headless: "new" });
  const page = await browser.newPage();
  await page.setViewport({ width: 1200, height: 800 });
  await page.goto('http://localhost:5173', { waitUntil: 'networkidle2' });
  await page.screenshot({ path: '/Users/avikdas/.gemini/antigravity-ide/brain/3e3bdb23-99af-40e5-a1e1-62550f3094a6/screenshot.png' });
  await browser.close();
})();
