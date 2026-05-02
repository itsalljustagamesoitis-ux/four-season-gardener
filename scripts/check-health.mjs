/**
 * Fleet health check — verifies every registered site is up and sane.
 *
 * Checks per site:
 *   1. Homepage returns HTTP 200
 *   2. Response is not empty (>= 500 bytes)
 *   3. Sitemap is accessible (/sitemap-index.xml returns 200)
 *   4. Affiliate tag is present in HTML (catches AMAZON_TAG misconfiguration)
 *   5. No untagged Amazon links (catches broken rehype plugin)
 *
 * Usage:
 *   node scripts/check-health.mjs [--concurrency=N] [--timeout=N]
 *
 * Exit codes: 0 = all healthy, 1 = one or more failures
 */

import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __dir = dirname(fileURLToPath(import.meta.url))
const SITES_FILE = join(__dir, 'sites.txt')

const CONCURRENCY = parseInt(process.argv.find(a => a.startsWith('--concurrency='))?.split('=')[1] ?? '10')
const TIMEOUT_MS  = parseInt(process.argv.find(a => a.startsWith('--timeout='))?.split('=')[1] ?? '15000')

// ── Load sites ────────────────────────────────────────────────────────────────
const domains = readFileSync(SITES_FILE, 'utf8')
  .split('\n')
  .map(l => l.trim())
  .filter(l => l && !l.startsWith('#'))

if (domains.length === 0) {
  console.log('No sites in scripts/sites.txt — add domains and rerun.')
  process.exit(0)
}

console.log(`\nChecking ${domains.length} site(s) (concurrency=${CONCURRENCY}, timeout=${TIMEOUT_MS}ms)\n`)

// ── Results ───────────────────────────────────────────────────────────────────
const results = { ok: [], warn: [], fail: [] }

function ok(domain)           { results.ok.push({ domain }); process.stdout.write('.') }
function warn(domain, reason) { results.warn.push({ domain, reason }); process.stdout.write('?') }
function fail(domain, reason) { results.fail.push({ domain, reason }); process.stdout.write('✗') }

// ── Per-site check ────────────────────────────────────────────────────────────
async function fetchWithTimeout(url) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    const res = await fetch(url, { signal: controller.signal, redirect: 'follow' })
    clearTimeout(timer)
    return res
  } catch (err) {
    clearTimeout(timer)
    throw err
  }
}

async function checkSite(domain) {
  const base = `https://${domain}`

  // ── 1. Homepage ─────────────────────────────────────────────────────────────
  let body
  try {
    const res = await fetchWithTimeout(`${base}/`)
    if (res.status !== 200) {
      fail(domain, `Homepage HTTP ${res.status}`)
      return
    }
    body = await res.text()
  } catch (err) {
    fail(domain, err.name === 'AbortError' ? `Homepage timed out after ${TIMEOUT_MS}ms` : `Homepage fetch error: ${err.message}`)
    return
  }

  // ── 2. Empty page ────────────────────────────────────────────────────────────
  if (body.length < 500) {
    fail(domain, `Homepage only ${body.length} bytes (empty page?)`)
    return
  }

  // ── 3. Sitemap ───────────────────────────────────────────────────────────────
  try {
    const smap = await fetchWithTimeout(`${base}/sitemap-index.xml`)
    if (smap.status !== 200) {
      warn(domain, `Sitemap HTTP ${smap.status}`)
    }
  } catch (err) {
    warn(domain, `Sitemap unreachable: ${err.message}`)
  }

  // ── 4. Affiliate tag present ─────────────────────────────────────────────────
  const hasAmazonLinks = body.includes('amazon.com')
  const hasTag = body.includes('tag=')
  if (hasAmazonLinks && !hasTag) {
    warn(domain, 'Amazon links found but no affiliate tag — check AMAZON_TAG env var')
  }

  // ── 5. Untagged sponsored links ───────────────────────────────────────────────
  const anchorRe = /<a\s[^>]*href="[^"]*amazon\.com[^"]*"[^>]*>/gi
  let m
  let untagged = 0
  while ((m = anchorRe.exec(body)) !== null) {
    if (!/rel="[^"]*sponsored/.test(m[0])) untagged++
  }
  if (untagged > 0) {
    warn(domain, `${untagged} untagged Amazon link(s) on homepage`)
  }

  ok(domain)
}

// ── Run with concurrency limit ────────────────────────────────────────────────
async function runWithConcurrency(tasks, limit) {
  const queue = [...tasks]
  const workers = Array.from({ length: Math.min(limit, queue.length) }, async () => {
    while (queue.length) await checkSite(queue.shift())
  })
  await Promise.all(workers)
}

await runWithConcurrency(domains, CONCURRENCY)
console.log('\n')

// ── Report ────────────────────────────────────────────────────────────────────
console.log(`Results:`)
console.log(`  ✓ Healthy:   ${results.ok.length}`)
console.log(`  ? Warnings:  ${results.warn.length}`)
console.log(`  ✗ Failed:    ${results.fail.length}`)
console.log()

if (results.warn.length) {
  console.warn('WARNINGS (investigate when convenient):')
  for (const w of results.warn) console.warn(`  [${w.domain}]  ${w.reason}`)
  console.warn()
}

if (results.fail.length) {
  console.error('FAILURES (action required):')
  for (const f of results.fail) console.error(`  [${f.domain}]  ${f.reason}`)
  console.error()
  process.exit(1)
}

if (results.warn.length === 0 && results.fail.length === 0) {
  console.log(`✓ All ${results.ok.length} site(s) healthy.\n`)
}
