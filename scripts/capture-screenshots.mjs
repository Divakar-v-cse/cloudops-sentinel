/**
 * Capture real screenshots of every page with Playwright.
 *
 * Prerequisites (not committed to the repo to keep installs small):
 *   npm install --no-save playwright
 *   npx playwright install chromium
 *
 * Usage (both servers must be running):
 *   node scripts/capture-screenshots.mjs
 *   BASE_URL=http://localhost:5173 EMAIL=admin@cloudops.local PASSWORD=Admin@12345 \
 *     node scripts/capture-screenshots.mjs
 *
 * Output: screenshots/<slug>.png plus screenshots/manifest.json containing the
 * title, console errors and HTTP failures observed for each page.
 */
import { chromium } from 'playwright'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'

const BASE_URL = process.env.BASE_URL || 'http://localhost:5173'
const EMAIL = process.env.EMAIL || 'admin@cloudops.local'
const PASSWORD = process.env.PASSWORD || 'Admin@12345'
const OUT_DIR = process.env.OUT_DIR || 'screenshots'

const PAGES = [
  ['overview', '/'],
  ['infrastructure', '/instances'],
  ['instance-detail', null], // resolved after inventory loads
  ['monitoring', '/monitoring'],
  ['security', '/security'],
  ['cost-optimization', '/costs'],
  ['log-intelligence', '/logs'],
  ['incidents', '/incidents'],
  ['remediation', '/remediation'],
  ['pipelines', '/pipelines'],
  ['aws-integrations', '/aws'],
  ['audit-logs', '/audit'],
  ['settings', '/settings'],
]

const manifest = []

function slugify(value) {
  return value.replace(/[^a-z0-9-]+/gi, '-').replace(/^-|-$/g, '').toLowerCase()
}

async function settle(page) {
  await page.waitForLoadState('domcontentloaded')
  await page.waitForTimeout(1800) // let API responses render
}

const browser = await chromium.launch()
const context = await browser.newContext({ viewport: { width: 1600, height: 960 }, deviceScaleFactor: 1 })
const page = await context.newPage()

const consoleErrors = []
const failedRequests = []
page.on('console', (message) => {
  if (message.type() === 'error') consoleErrors.push(message.text())
})
page.on('requestfailed', (request) => {
  failedRequests.push(`${request.url()} :: ${request.failure()?.errorText}`)
})
page.on('response', (response) => {
  if (response.status() >= 500) failedRequests.push(`${response.url()} :: HTTP ${response.status()}`)
})

await mkdir(OUT_DIR, { recursive: true })

console.log(`→ ${BASE_URL}/login`)
await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' })
await page.screenshot({ path: path.join(OUT_DIR, '00-login.png'), fullPage: true })
manifest.push({ slug: '00-login', route: '/login', title: await page.title(), consoleErrors: [], failedRequests: [] })

await page.fill('input[type="email"]', EMAIL)
await page.fill('input[type="password"]', PASSWORD)
await page.click('button[type="submit"]')
await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 20000 })
await settle(page)
console.log('→ signed in')

for (const [name, route] of PAGES) {
  let target = route
  if (target === null) {
    // open the first simulated instance from the inventory table
    await page.goto(`${BASE_URL}/instances`, { waitUntil: 'domcontentloaded' })
    await settle(page)
    const link = page.locator('table tbody tr a').first()
    target = await link.getAttribute('href')
    if (!target) {
      console.warn('! no instance link found, skipping detail page')
      continue
    }
  }

  const before = consoleErrors.length
  const beforeFailed = failedRequests.length
  await page.goto(`${BASE_URL}${target}`, { waitUntil: 'domcontentloaded' })
  await settle(page)
  const file = path.join(OUT_DIR, `${slugify(name)}.png`)
  await page.screenshot({ path: file, fullPage: true })
  const entry = {
    slug: slugify(name),
    route: target,
    title: await page.title(),
    consoleErrors: consoleErrors.slice(before),
    failedRequests: failedRequests.slice(beforeFailed),
  }
  manifest.push(entry)
  console.log(`✓ ${name.padEnd(20)} ${target}  errors=${entry.consoleErrors.length}`)
}

// alternate theme variant of the overview (whichever theme is not current)
await page.goto(`${BASE_URL}/`, { waitUntil: 'domcontentloaded' })
await settle(page)
const themeButton = page.locator('header button[aria-label="Toggle theme"]')
if (await themeButton.count()) {
  await themeButton.first().click()
  await page.waitForTimeout(600)
  await page.screenshot({ path: path.join(OUT_DIR, 'overview-alt-theme.png'), fullPage: true })
  console.log('✓ light theme captured')
  await themeButton.first().click()
}

await writeFile(
  path.join(OUT_DIR, 'manifest.json'),
  JSON.stringify({ capturedAt: new Date().toISOString(), baseUrl: BASE_URL, pages: manifest }, null, 2),
  'utf8',
)

console.log(`\nCaptured ${manifest.length} screenshots into ${OUT_DIR}/`)
const errorPages = manifest.filter((entry) => entry.consoleErrors.length > 0)
if (errorPages.length) {
  console.warn(`Pages with console errors: ${errorPages.map((entry) => entry.slug).join(', ')}`)
}

await browser.close()
process.exit(0)
