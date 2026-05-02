/**
 * Post-build validator — fails the build if critical issues are found in dist/.
 * Checks: empty pages, untagged Amazon affiliate links, doubled brand names in H3s.
 * Run via: node scripts/build-validator.mjs
 */

import { readFileSync, readdirSync, statSync } from 'fs'
import { join, relative } from 'path'

const DIST = new URL('../dist', import.meta.url).pathname
const MIN_HTML_BYTES = 500

let failures = 0
const errors = []

function fail(check, file, msg) {
  errors.push(`  FAIL [${check}] ${file}\n       ${msg}`)
  failures++
}

function checkFile(fullPath) {
  const rel = relative(DIST, fullPath)
  const raw = readFileSync(fullPath, 'utf8')
  const size = Buffer.byteLength(raw, 'utf8')

  // ── 1. Empty page ────────────────────────────────────────────────────────
  // Skip intentional Astro redirect pages (they're tiny but valid)
  if (raw.includes('http-equiv="refresh"')) return

  if (size < MIN_HTML_BYTES) {
    fail('empty-page', rel, `${size} bytes — minimum is ${MIN_HTML_BYTES}`)
    return // Nothing else to check on a near-empty file
  }

  // ── 2. Untagged Amazon affiliate links ───────────────────────────────────
  // Match <a ...> tags that contain amazon.com in href
  const anchorRe = /<a\s[^>]*href="[^"]*amazon\.com[^"]*"[^>]*>/gi
  let m
  while ((m = anchorRe.exec(raw)) !== null) {
    const tag = m[0]
    if (!/rel="[^"]*sponsored[^"]*"/.test(tag)) {
      const snippet = tag.replace(/\s+/g, ' ').slice(0, 120)
      fail('untagged-affiliate', rel, `Amazon link missing rel="sponsored": ${snippet}`)
    }
  }

  // ── 3. Doubled brand names in H3 ─────────────────────────────────────────
  // Catches "Perky-Pet Perky-Pet …", "EGO Power+ EGO POWER+ …" etc.
  const h3Re = /<h3[^>]*>([\s\S]*?)<\/h3>/gi
  while ((m = h3Re.exec(raw)) !== null) {
    // Strip inner HTML tags to get visible text
    const text = m[1].replace(/<[^>]+>/g, '').trim()
    // A word (or hyphenated word) repeated immediately after itself, case-insensitive
    if (/(\b[\w-]+\b)\s+\1\b/i.test(text)) {
      fail('doubled-brand', rel, `H3 contains repeated word: "${text.slice(0, 100)}"`)
    }
  }
}

function walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) walk(full)
    else if (entry.name.endsWith('.html')) checkFile(full)
  }
}

// ── Run ───────────────────────────────────────────────────────────────────
console.log(`\nValidating build output in ${DIST} …\n`)
walk(DIST)

if (failures === 0) {
  console.log('✓ Build validation passed — no issues found.\n')
  process.exit(0)
} else {
  console.error(`✗ Build validation failed — ${failures} issue(s):\n`)
  for (const e of errors) console.error(e)
  console.error(`\nFix the issues above and rebuild.\n`)
  process.exit(1)
}
