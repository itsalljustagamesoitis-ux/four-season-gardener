# IndexNow Integration

## What it does

IndexNow is a protocol supported by Bing, Yandex, Naver, and Seznam. When you submit URLs to `api.indexnow.org`, participating search engines are notified immediately rather than waiting for their crawlers to find the pages.

For affiliate sites with hundreds of product pages, this means new content is discoverable in Bing within hours of a deploy instead of days.

## How it works in this template

1. Each clone gets its own unique 32-character hex key, stored as `public/<key>.txt`.
2. On every production deploy (Cloudflare Pages, `CF_PAGES=1`, branch `main`), the `postbuild` script runs `scripts/submit-indexnow.mjs`.
3. The script reads `dist/sitemap-index.xml`, extracts all `<loc>` URLs, and compares them against `.indexnow-state.json` to find new URLs only.
4. New URLs are POSTed to `https://api.indexnow.org/IndexNow` in batches of up to 10,000.
5. On success, `.indexnow-state.json` is updated with the full submitted URL list.

Local dev builds and PR/preview builds are silently skipped (the `CF_PAGES` gate).

## Key generation

`scripts/clone-site.sh` generates the key automatically:

```bash
openssl rand -hex 16   # → 32-char lowercase hex
```

The key is written to two places:
- `public/<key>.txt` — served at `https://yourdomain.com/<key>.txt`, proves domain ownership to IndexNow
- `.env` — local reference (also set as a Cloudflare Pages Secret for builds)

Idempotent: if `INDEXNOW_KEY` is already set in the environment when `clone-site.sh` runs, the existing value is reused rather than generating a new one.

## Verifying a clone is submitting

1. Open **Bing Webmaster Tools** → your site → **IndexNow**.
2. After the next production deploy, you should see a submission entry with the URLs and a timestamp.
3. First submission after setup may take up to 24 hours to appear in Webmaster Tools, though Bing typically processes it within minutes.

## Delta detection and state persistence

`.indexnow-state.json` lives in the repo. It records which URLs have already been submitted.

- **Local deploys** (`wrangler pages deploy`): the state file is updated in place. Commit and push it so the next build sees the updated delta.
- **GitHub-triggered builds**: Cloudflare's build environment doesn't persist filesystem state between runs. The build reads the last committed state, submits only new URLs, but the updated state is discarded after the build. This is fine — resubmitting known URLs is harmless and IndexNow is idempotent.

## Manually triggering a re-submit

To force a full re-submission of all URLs (e.g. after a domain migration or bulk content update):

```bash
# Reset the state file
echo '{"submittedUrls":[],"lastSubmission":null,"totalSubmitted":0}' > .indexnow-state.json

# Build and deploy — all URLs will be submitted as "new"
npm run build
npx wrangler pages deploy dist --project-name your-site-name

# Commit the updated state
git add .indexnow-state.json
git commit -m "Reset IndexNow state — full re-submission triggered"
git push
```

## If the key is suspected leaked

An IndexNow key controls which domain you can submit URLs for. If yours is compromised:

1. Generate a new key: `openssl rand -hex 16`
2. Delete the old `public/<oldkey>.txt`
3. Add `public/<newkey>.txt` with the new key as its contents
4. Update the `INDEXNOW_KEY` Secret in Cloudflare Pages dashboard
5. Reset `.indexnow-state.json` (optional — a re-submit after rotation is harmless)
6. Deploy

The old key file will 404 immediately after deploy, invalidating it for submissions.

## Build validator

`scripts/build-validator.mjs` checks:
- If `INDEXNOW_KEY` is set: `dist/<key>.txt` must exist and its contents must exactly match the env var value.
- If `INDEXNOW_KEY` is not set in a production build: emits a warning (non-blocking).
