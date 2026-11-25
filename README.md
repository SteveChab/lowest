# Lowest Hallowed site (folder: lowest)

Plain HTML, CSS and JS, no framework. Built for GitHub Pages with a custom domain. Strategy and copy live in the ambient-pedal repo (`docs/WEBSITE-PLAN.md`, `docs/WEBSITE-COPY.md`).

## Preview
Open `index.html` in a browser and click through. Paths are relative and point at folders (`about/`), so on a local file the folder links may show a listing: open its `index.html`. Or run `python3 -m http.server 8000` in this folder for folder links that work.

`404.html` is the one page with root paths, because GitHub Pages serves it at any depth. It looks right only on the published site, or under the local server.

## Monthly update (a new release is scheduled)
1. Add the release to `data/releases.json`, either by hand (copy the existing entry) or from the release doc:
   `python3 tools/update.py --add ../ambient-pedal/docs/releases/02-ii-chased-by-the-miraculous.md`
2. In `data/releases.json`, fill the new entry's `line` (one line on the music). Add `watch` (`2027-01-07T22:00`) only if the Prayer Watch is not the night before the release at 10pm Eastern.
3. `python3 tools/update.py`
4. Review in GitHub Desktop, commit, push.

The data file is public once pushed, so add a release only when its title can be public.

The script rewrites only the marked regions (`<!-- gen:NAME -->`): the This month block, the Event JSON-LD, `calendar/prayer-watch.ics`, the `llms.txt` lines, and `sitemap.xml`. It also stamps the header, footer, icon links, signup, the canonical and share tags (built from each page's own `<title>` and meta description) and MusicGroup JSON-LD into every page, so those are edited in one place (nav and links in `data/releases.json`, signup in `partials/signup.html`). Edit the copy anywhere outside the markers.

"Next" is the first gathering that has not ended. "Latest album" is the newest release on or before today (Eastern). If a date passes before you run the script, `js/site.js` hides the old "next" and shows a short note.

`python3 tools/update.py --check` changes nothing, exits 1 if anything is stale, and lists open placeholders. `--today 2027-01-08` previews another date.

Release data comes from the ambient-pedal release docs through `--add` (title, numeral, release date, Bandcamp URL). There is no structured export there, so the `line` is written by hand.

## Placeholders to replace before launch
- Domain: `https://lowesthallowed.example` everywhere. `python3 tools/update.py --domain yourdomain.com` swaps it in all files and writes `CNAME`. Then GitHub, Settings, Pages, custom domain, enforce HTTPS.
- Mailchimp form: done. It is the embed from the Steve Chab list, restyled, in `partials/signup.html`, with the "Love Jesus? Yes" group as a hidden field. After a signup, Mailchimp shows its own confirmation page; its thank-you page URL can be pointed back at the site in Mailchimp.
- Icon links: only Bandcamp and YouTube are live. Add `spotify` and `apple_music` under `links` in `data/releases.json` when they exist, then run the script. An empty link shows no icon.
- Share card: `assets/share-card.jpg` (1200 by 630), set once in `data/releases.json` (`share_image`, `share_alt`) and used by every page. It is an image, so redo it if the headline changes. Test them with the Facebook Sharing Debugger and the LinkedIn Post Inspector after launch.
- Photos are the footage placeholders from the mockups. Replace the files in `assets/img/` (a 2000 and a 1000 px WebP each).
- Check the Jackie Baker link on `/similar/`, and run `voice-lint` on the copy.

## Files
- `index.html`, `prayer-watch/`, `about/`, `similar/`, `404.html`
- `css/site.css`, `js/reveal.js`, `js/site.js`
- `data/releases.json`, `partials/signup.html`, `tools/update.py`
- `sitemap.xml`, `robots.txt`, `llms.txt`, `calendar/prayer-watch.ics`
- `assets/`: fonts, images, wordmark, icons. Brand masters stay in ambient-pedal (`brand/masters/`).

## Publish
GitHub Desktop: Add Local Repository (or Create), Publish repository. Repo Settings, Pages, deploy from the `main` branch root. `.nojekyll` is included.
