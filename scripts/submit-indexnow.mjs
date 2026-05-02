/**
 * IndexNow submission script.
 * Reads dist/sitemap-index.xml, extracts all URLs, submits them to IndexNow.
 * Runs on every production deploy — IndexNow tolerates resubmissions without penalty.
 *
 * Only fires on Cloudflare production deploys (CF_PAGES=1 + CF_PAGES_BRANCH=main).
 * Missing INDEXNOW_KEY: warns and exits 0.
 * API errors: logs and exits 0 — IndexNow is best-effort, never blocks builds.
 */

import { readFileSync, existsSync } from 'fs'
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
    const path = sitemapUrl.replace(siteUrl, DIST)
    if (!existsSync(path)) {
      console.warn(`IndexNow: child sitemap not found on disk: ${path}`)
      continue
    }
    urls.push(...extractTags(readFileSync(path, 'utf8'), 'loc'))
  }

  return urls
}

// ── IndexNow API ──────────────────────────────────────────────────────────────
async function submitBatch(urlBatch) {
  const res = await fetch('https://api.indexnow.org/IndexNow', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify({
      host,
      key: KEY,
      keyLocation: `${siteUrl}/${KEY}.txt`,
      urlList: urlBatch,
    }),
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
  const urls = loadSitemapUrls()
  if (urls.length === 0) {
    console.log('IndexNow: no URLs found in sitemap — nothing to submit.')
    return
  }

  console.log(`IndexNow: submitting ${urls.length} URL(s) to ${host} …`)

  for (let i = 0; i < urls.length; i += BATCH_SIZE) {
    const batch = urls.slice(i, i + BATCH_SIZE)
    console.log(`  Batch ${Math.floor(i / BATCH_SIZE) + 1}: ${batch.length} URL(s)`)
    const ok = await submitBatch(batch)
    if (!ok) break
  }

  console.log('IndexNow: ✓ done.')
}

main().catch(err => {
  console.warn(`IndexNow: unexpected error — ${err.message}`)
  process.exit(0)
})
