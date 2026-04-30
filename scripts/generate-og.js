#!/usr/bin/env node
/**
 * Generates a branded OG fallback image (1200×630 PNG) from site.config.yaml.
 * Run once per site setup: node scripts/generate-og.js
 * Output: public/images/og-default.jpg
 */

import { readFileSync, mkdirSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'
import yaml from 'js-yaml'
import sharp from 'sharp'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = resolve(__dirname, '..')

const cfg = yaml.load(readFileSync(resolve(root, 'site.config.yaml'), 'utf8'))

const WIDTH = 1200
const HEIGHT = 630
const primary = cfg.visual.primary_color   // e.g. #2D5016
const accent  = cfg.visual.accent_color    // e.g. #8B9D52
const bg      = '#FAFAF7'

const brandName = cfg.site.brand_name      // "The Four Season Gardener"
const tagline   = cfg.site.tagline         // "Honest garden product reviews..."

// Build an SVG with proper text — sharp will rasterise it via librsvg
const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg width="${WIDTH}" height="${HEIGHT}" viewBox="0 0 ${WIDTH} ${HEIGHT}"
     xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="${primary}"/>
      <stop offset="100%" stop-color="${primary}dd"/>
    </linearGradient>
  </defs>

  <!-- Background -->
  <rect width="${WIDTH}" height="${HEIGHT}" fill="url(#bg)"/>

  <!-- Subtle texture grid -->
  <rect width="${WIDTH}" height="${HEIGHT}" fill="none"
        stroke="${accent}" stroke-width="0.5" stroke-opacity="0.15"
        stroke-dasharray="4 12"/>

  <!-- Left accent bar -->
  <rect x="0" y="0" width="10" height="${HEIGHT}" fill="${accent}"/>

  <!-- Brand name -->
  <text x="80" y="260"
        font-family="Georgia, 'Times New Roman', serif"
        font-size="72" font-weight="700"
        fill="white" opacity="1"
        letter-spacing="-1">${brandName}</text>

  <!-- Tagline -->
  <text x="80" y="340"
        font-family="system-ui, -apple-system, sans-serif"
        font-size="32" font-weight="400"
        fill="white" opacity="0.85">${tagline.length > 55 ? tagline.slice(0, 52) + '…' : tagline}</text>

  <!-- Domain -->
  <text x="80" y="${HEIGHT - 60}"
        font-family="system-ui, -apple-system, sans-serif"
        font-size="24" font-weight="500"
        fill="${accent}" opacity="0.9">${cfg.site.domain.replace(/^https?:\/\//, '')}</text>
</svg>`

const outDir = resolve(root, 'public/images')
mkdirSync(outDir, { recursive: true })
const outPath = resolve(outDir, 'og-default.jpg')

await sharp(Buffer.from(svg))
  .jpeg({ quality: 90 })
  .toFile(outPath)

console.log(`✓ OG image written to public/images/og-default.jpg`)
