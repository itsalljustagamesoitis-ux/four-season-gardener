#!/usr/bin/env node
/**
 * clone-site.js — copy this template to a new site directory
 *
 * Usage:
 *   node scripts/clone-site.js --dest ~/my-new-site --name "My Garden Site" --domain mygardensite.com
 *
 * What it does:
 *   1. Copies all template files to dest (excluding dist/, node_modules/, content/articles/, config/personas/)
 *   2. Updates site.config.yaml with the provided name/domain
 *   3. Runs npm install in the new directory
 *   4. Prints next steps
 */

import { cpSync, mkdirSync, readFileSync, writeFileSync, existsSync } from 'fs'
import { resolve, join } from 'path'
import { execSync } from 'child_process'

const args = process.argv.slice(2)
const get = (flag) => { const i = args.indexOf(flag); return i !== -1 ? args[i + 1] : null }

const dest = get('--dest')
const name = get('--name')
const domain = get('--domain')

if (!dest || !name || !domain) {
  console.error('Usage: node scripts/clone-site.js --dest <path> --name "<Site Name>" --domain <domain.com>')
  process.exit(1)
}

const src = resolve(import.meta.dirname, '..')
const destAbs = resolve(dest)

if (existsSync(destAbs)) {
  console.error(`Destination already exists: ${destAbs}`)
  process.exit(1)
}

const EXCLUDE = new Set([
  'dist', 'node_modules', '.git', 'content/articles',
  'config/personas', 'scripts/clone-site.js',
])

console.log(`Cloning template → ${destAbs}`)

cpSync(src, destAbs, {
  recursive: true,
  filter: (src) => {
    const rel = src.replace(resolve(import.meta.dirname, '..') + '/', '')
    return !EXCLUDE.has(rel) && ![...EXCLUDE].some(ex => rel.startsWith(ex + '/'))
  },
})

// Update site.config.yaml
const configPath = join(destAbs, 'site.config.yaml')
let config = readFileSync(configPath, 'utf8')
config = config
  .replace(/brand_name:.*/, `brand_name: "${name}"`)
  .replace(/domain:.*/, `domain: "https://www.${domain}"`)
  .replace(/cloudflare_pages_project:.*/, `cloudflare_pages_project: "${domain.replace(/\./g, '-')}"`)
writeFileSync(configPath, config)

// Clear content placeholder
mkdirSync(join(destAbs, 'content/articles'), { recursive: true })
mkdirSync(join(destAbs, 'config/personas'), { recursive: true })

// npm install
console.log('Running npm install...')
execSync('npm install', { cwd: destAbs, stdio: 'inherit' })

console.log(`
Done! New site at: ${destAbs}

Next steps:
  1. Update site.config.yaml — fill in affiliate IDs, GA4 ID, logo paths
  2. Create config/personas/<name>.yaml — persona profile
  3. Update content/products/products.yaml — your product catalogue
  4. Add content/articles/*.md — your articles
  5. Replace placeholder logo files in public/
  6. npm run build — verify it builds
  7. Deploy to Cloudflare Pages
`)
