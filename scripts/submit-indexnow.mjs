/**
 * IndexNow submission script.
 * Reads dist/sitemap-index.xml, extracts all URLs, submits new ones to IndexNow.
 * Delta detection via .indexnow-state.json — only new URLs are submitted each run.
 *
 * Only fires on Cloudflare production deploys (CF_PAGES=1 + CF_PAGES_BRANCH=main).
 * Missing INDEXNOW_KEY: warns and exits 0.
 * API errors: logs and exits 0 — IndexNow is best-effort, never blocks builds.
 *
 * State file (.indexnow-state.json): committed to repo so delta works across builds.
 * CI builds read last committed state; local deploys should commit the updated state.
 */

import { readFileSync, writeFileSync, existsSync } from 'fs'
import { createRequire } from 'module'

const require = createRequire(import.meta.url)
const yaml = require('js-yaml')

// ── Environment gate ──────────────────────────────────────────────────────────
const isCloudflareProduction =
  process.env.CF_PAGES === '1' && process.env.CF_PAGES_BRANCH === 'main'

if (!isCloudflareProduction) {
  console.log('IndexNow: skipping — not a Cloudflare production build.')
  process.exit(0)
}

// ── Config ────────────────────────────────────────────────────────────────────
const KEY = process.env.INDEXNOW_KEY
if (!KEY) {
  console.warn('IndexNow: INDEXNOW_KEY not set — skipping submission.')
  console.warn('  Set INDEXNOW_KEY in Cloudflare Pages → Settings → Environment Variables.')
  process.exit(0)
}

const _cfg = yaml.load(
  readFileSync(new URL('../site.config.yaml', import.meta.url).pathname, 'utf8')
)
const siteUrl = (process.env.SITE_URL ?? `https://${_cfg.site.domain}`).replace(/\/$/, '')
const host = new URL(siteUrl).hostname

const DIST = new URL('../dist', import.meta.url).pathname
const STATE_FILE = new URL('../.indexnow-state.json', import.meta.url).pathname
const BATCH_SIZE = 10_000

// ── Parse sitemaps ────────────────────────────────────────────────────────────
function extractTags(xml, tag) {
  const re = new RegExp(`<${tag}>([^<]+)</${tag}>`, 'g')
  const results = []
  let m
  while ((m = re.exec(xml)) !== null) results.push(m[1].trim())
  return results
}

function loadSitemapUrls() {
  const indexPath = `${DIST}/sitemap-index.xml`
  if (!existsSync(indexPath)) {
    console.warn('IndexNow: dist/sitemap-index.xml not found — skipping.')
    return []
  }

  const indexXml = readFileSync(indexPath, 'utf8')
  const childSitemaps = extractTags(indexXml, 'loc')

  const urls = []
  for (const sitemapUrl of childSitemaps) {
    // Convert absolute URL to local dist path
    const path = sitemapUrl.replace(siteUrl, DIST)
    if (!existsSync(path)) {
      console.warn(`IndexNow: child sitemap not found on disk: ${path}`)
      continue
    }
    const xml = readFileSync(path, 'utf8')
    urls.push(...extractTags(xml, 'loc'))
  }

  return urls
}

// ── Delta detection ───────────────────────────────────────────────────────────
function loadState() {
  if (!existsSync(STATE_FILE)) return { submittedUrls: [], lastSubmission: null }
  try {
    return JSON.parse(readFileSync(STATE_FILE, 'utf8'))
  } catch {
    return { submittedUrls: [], lastSubmission: null }
  }
}

function saveState(state) {
  writeFileSync(STATE_FILE, JSON.stringify(state, null, 2) + '\n', 'utf8')
}

// ── IndexNow API ──────────────────────────────────────────────────────────────
async function submitBatch(urlBatch) {
  const body = {
    host,
    key: KEY,
    keyLocation: `${siteUrl}/${KEY}.txt`,
    urlList: urlBatch,
  }

  const res = await fetch('https://api.indexnow.org/IndexNow', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify(body),
  })

  if (res.status !== 200 && res.status !== 202) {
    const text = await res.text().catch(() => '(no body)')
    console.warn(`IndexNow: API returned ${res.status} — ${text.slice(0, 200)}`)
    return false
  }

  return true
}

// ── Main ──────────────────────────────────────────────────────────────────────
async function main() {
  const allUrls = loadSitemapUrls()
  if (allUrls.length === 0) {
    console.log('IndexNow: no URLs found in sitemap — nothing to submit.')
    return
  }

  const state = loadState()
  const submitted = new Set(state.submittedUrls)
  const newUrls = allUrls.filter(u => !submitted.has(u))

  if (newUrls.length === 0) {
    console.log(`IndexNow: no new URLs since last submission (${allUrls.length} total, all already submitted).`)
    return
  }

  console.log(`IndexNow: submitting ${newUrls.length} new URL(s) of ${allUrls.length} total to ${host} …`)

  // Submit in batches
  let success = true
  for (let i = 0; i < newUrls.length; i += BATCH_SIZE) {
    const batch = newUrls.slice(i, i + BATCH_SIZE)
    console.log(`  Batch ${Math.floor(i / BATCH_SIZE) + 1}: ${batch.length} URL(s)`)
    const ok = await submitBatch(batch)
    if (!ok) {
      success = false
      console.warn(`  Batch failed — state will not be updated for this run.`)
      break
    }
  }

  if (success) {
    state.submittedUrls = [...new Set([...state.submittedUrls, ...newUrls])].sort()
    state.lastSubmission = new Date().toISOString()
    state.totalSubmitted = state.submittedUrls.length
    saveState(state)
    console.log(`IndexNow: ✓ submitted ${newUrls.length} URL(s). State updated — commit .indexnow-state.json to persist delta for future builds.`)
  }
}

main().catch(err => {
  console.warn(`IndexNow: unexpected error — ${err.message}`)
  process.exit(0)
})
