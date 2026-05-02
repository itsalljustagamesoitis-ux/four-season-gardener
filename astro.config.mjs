// @ts-check
import { defineConfig } from 'astro/config'
import sitemap from '@astrojs/sitemap'
import rehypeExternalLinks from 'rehype-external-links'
import { readFileSync } from 'fs'
import yaml from 'js-yaml'

const _cfg = yaml.load(readFileSync('./site.config.yaml', 'utf8'))
const siteUrl = process.env.SITE_URL ?? `https://${_cfg.site.domain}`

export default defineConfig({
  site: siteUrl,
  integrations: [
    sitemap({
      filter: (page) => !page.endsWith('/privacy/'),
      serialize(item) {
        // Set lastmod to build time for all pages (article pages will be overridden by their frontmatter date when available)
        item.lastmod = new Date().toISOString()
        // Prioritise homepage and category pages
        if (item.url === `${siteUrl}/`) {
          item.changefreq = 'weekly'
          item.priority = 1.0
        } else if (!item.url.includes('.')) {
          item.changefreq = 'monthly'
          item.priority = 0.8
        }
        return item
      },
    }),
  ],
  markdown: {
    rehypePlugins: [
      [rehypeExternalLinks, {
        rel: ['nofollow', 'sponsored'],
        target: '_blank',
        test: (node) => {
          const href = node.properties?.href ?? ''
          return typeof href === 'string' && href.includes('amazon.com')
        },
      }],
    ],
  },
  image: {
    service: {
      entrypoint: 'astro/assets/services/sharp',
    },
  },
  build: {
    inlineStylesheets: 'auto',
  },
  vite: {
    optimizeDeps: {
      exclude: ['sharp'],
    },
  },
})
