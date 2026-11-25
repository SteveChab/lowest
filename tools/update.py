#!/usr/bin/env python3
"""Regenerates every dated or shared part of the site from data/releases.json.

Standard library only (Python 3.9 or newer). Run from anywhere:

    python3 tools/update.py                  regenerate, then print what the site shows now
    python3 tools/update.py --check          change nothing; exit 1 if anything is stale; list open placeholders
    python3 tools/update.py --add PATH       add a release from an ambient-pedal release doc (docs/releases/NN-*.md)
    python3 tools/update.py --domain HOST    set the real domain everywhere (also writes CNAME)
    python3 tools/update.py --today 2027-01-08[THH:MM]   pretend it is that Eastern time (for testing)

What it writes:
    marked regions in the pages  <!-- gen:NAME --> ... <!-- /gen:NAME -->   (header, icons, signup, footer, social tags,
                                  this-month, Event JSON-LD, MusicGroup JSON-LD)
    calendar/prayer-watch.ics    the next gathering
    llms.txt                     the marked lines (this month, links)
    sitemap.xml                  all pages, with lastmod

Nothing outside a marked region is touched, so hand edits to the copy are safe.
"""
import argparse
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "releases.json"
PLACEHOLDER_URL = "https://lowesthallowed.example"
PAGES = [
    ("/", "index.html"),
    ("/prayer-watch/", "prayer-watch/index.html"),
    ("/about/", "about/index.html"),
    ("/similar/", "similar/index.html"),
]
HTML_FILES = [p for _, p in PAGES] + ["404.html"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

ICONS = {
    "bandcamp": ("Bandcamp", '<path fill="currentColor" d="M0 18.75l7.437-13.5H24l-7.438 13.5H0z"/>'),
    "youtube": ("YouTube", '<path fill="currentColor" d="M23.5 6.2a3 3 0 0 0-2.1-2.1C19.5 3.6 12 3.6 12 3.6s-7.5 0-9.4.5A3 3 0 0 0 .5 6.2 31 31 0 0 0 0 12a31 31 0 0 0 .5 5.8 3 3 0 0 0 2.1 2.1c1.9.5 9.4.5 9.4.5s7.5 0 9.4-.5a3 3 0 0 0 2.1-2.1A31 31 0 0 0 24 12a31 31 0 0 0-.5-5.8zM9.6 15.6V8.4l6.2 3.6-6.2 3.6z"/>'),
    "spotify": ("Spotify", '<circle cx="12" cy="12" r="11" fill="currentColor"/><path d="M6 9.3c4.4-1.2 9.2-.8 12.6 1.3M6.8 12.9c3.6-.9 7.1-.6 9.9 1.1M7.5 16.3c2.8-.7 5.4-.4 7.6.9" fill="none" stroke="#0b0c0d" stroke-width="1.8" stroke-linecap="round"/>'),
    "apple_music": ("Apple Music", '<path d="M9 18V6l10-2v12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><circle cx="6.5" cy="18" r="2.7" fill="currentColor"/><circle cx="16.5" cy="16" r="2.7" fill="currentColor"/>'),
}
SOCIAL = ["bandcamp", "youtube", "spotify", "apple_music"]
GENRES = ["Christian dark ambient", "Dungeon synth", "Unblack", "Neoclassical ambient"]


def esc(s):
    return html.escape(s, quote=True)


def fail(msg):
    print("error: " + msg, file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------- data

def load_data():
    try:
        return json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        fail("cannot read data/releases.json: %s" % e)


def time_label(d, tzlabel):
    h = d.hour % 12 or 12
    mins = ":%02d" % d.minute if d.minute else ""
    return "%d%s%s %s" % (h, mins, "am" if d.hour < 12 else "pm", tzlabel)


class Release:
    def __init__(self, raw, site, tz):
        for key in ("numeral", "title", "release", "bandcamp"):
            if not raw.get(key):
                fail("a release is missing '%s': %r" % (key, raw))
        self.raw = raw
        self.numeral = raw["numeral"]
        self.title = raw["title"]
        self.name = "%s. %s" % (self.numeral, self.title)
        self.event_name = raw.get("event_name") or "Prayer Watch"
        self.bandcamp = raw["bandcamp"]
        self.line = (raw.get("line") or "").strip()
        try:
            self.release = dt.date.fromisoformat(raw["release"])
            if raw.get("watch"):
                start = dt.datetime.strptime(raw["watch"], "%Y-%m-%dT%H:%M").replace(tzinfo=tz)
            else:
                hh, mm = [int(x) for x in site["watch_time"].split(":")]
                start = dt.datetime.combine(self.release - dt.timedelta(days=1), dt.time(hh, mm), tz)
        except ValueError as e:
            fail("bad date in release %s: %s" % (self.name, e))
        self.start = start
        self.end = start + dt.timedelta(minutes=int(raw.get("minutes", 60)))
        self.tzlabel = site["timezone_label"]

    @property
    def event_title(self):
        return "%s: %s" % (self.event_name, self.name)

    @property
    def full_title(self):
        return "Lowest Hallowed %s: %s" % (self.event_name, self.name)

    @property
    def weekday(self):
        return WEEKDAYS[self.start.weekday()]

    def date_text(self, now_year):
        s = "%s %d" % (MONTHS[self.start.month - 1], self.start.day)
        return s if self.start.year == now_year else "%s, %d" % (s, self.start.year)

    def time_text(self):
        return time_label(self.start, self.tzlabel)


def pick(releases, now):
    nxt = None
    for r in sorted(releases, key=lambda r: r.start):
        if r.end > now:
            nxt = r
            break
    out = [r for r in releases if r.release <= now.date()]
    latest = max(out, key=lambda r: r.release) if out else None
    return nxt, latest


# ---------------------------------------------------------------- html pieces

def link_for(data, key):
    return (data["links"].get(key) or "").strip()


def render_icons(data, variant):
    """One icon per link that is set in data/releases.json. Empty links are left out until they exist."""
    items = []
    for key in SOCIAL:
        href = link_for(data, key)
        if href:
            label, svg = ICONS[key]
            items.append('<li><a href="%s" aria-label="%s"><svg viewBox="0 0 24 24" aria-hidden="true">%s</svg></a></li>'
                         % (esc(href), label, svg))
    cls = "icons icons--hero" if variant == "hero" else "icons"
    return '<ul class="%s" role="list" aria-label="Listen and follow">\n%s\n</ul>' % (cls, "\n".join(items))


def render_head(data, params):
    current = params.get("current", "")
    root = params.get("root", "")
    static = " site-head--static" if params.get("variant") == "static" else ""
    links = []
    for item in data["nav"]:
        cur = ' aria-current="page"' if item["href"].strip("/") == current else ""
        links.append('<a href="%s"%s>%s</a>' % (esc(root + item["href"].lstrip("/")), cur, esc(item["label"])))
    return ('<header class="site-head%s"><div class="wrap grid">\n'
            '<a class="brand" href="%s"><img src="%sassets/pairing-color.svg" alt="Lowest Hallowed, home" width="3994" height="1016"></a>\n'
            '<nav class="nav" aria-label="Main">\n%s\n</nav></div></header>' % (static, root or "./", root, "\n".join(links)))


def render_footer(data, params):
    return ('<footer class="site-foot"><div class="wrap grid">\n%s\n</div></footer>' % render_icons(data, "foot"))


def render_signup(data, params):
    return (ROOT / "partials" / "signup.html").read_text(encoding="utf-8").rstrip("\n")


def render_social(data, params, text):
    """canonical, Open Graph and Twitter tags, built from the page's own <title> and meta description."""
    site = data["site"]
    title = re.search(r"<title>(.*?)</title>", text, re.S).group(1)
    desc = re.search(r'<meta name="description" content="(.*?)">', text, re.S).group(1)
    page = site["url"] + params["path"]
    image = "%s/%s" % (site["url"], site["share_image"])
    return "\n".join([
        '<link rel="canonical" href="%s">' % page,
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="%s">' % esc(site["name"]),
        '<meta property="og:title" content="%s">' % title,
        '<meta property="og:description" content="%s">' % desc,
        '<meta property="og:url" content="%s">' % page,
        '<meta property="og:image" content="%s">' % image,
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        '<meta property="og:image:alt" content="%s">' % esc(site["share_alt"]),
        '<meta name="twitter:card" content="summary_large_image">',
    ])


def render_this_month(data, params, ctx):
    nxt, latest, now = ctx["next"], ctx["latest"], ctx["now"]
    parts = []
    if nxt:
        iso = nxt.start.isoformat()
        cal = '<a class="btn" href="%scalendar/prayer-watch.ics">Add to calendar</a>' % params.get("root", "")
        parts.append(
            '<div class="block" data-ends="%s">\n'
            '<p class="label label--gold tagline">Next</p>\n'
            '<p class="name big">%s</p>\n'
            '<p class="date-big big"><time datetime="%s"><span>%s,</span> <span class="nb">%s</span> <span class="when">%s</span></time></p>\n'
            '<div class="btns"><a class="btn" href="%s">RSVP on Bandcamp</a>%s</div>\n'
            '</div>\n'
            '<div class="block" data-passed hidden>\n'
            '<p class="name big">This Prayer Watch has passed.</p>\n'
            '<p class="fine">The next one will be posted here and sent by email.</p>\n'
            '</div>'
            % (esc(nxt.end.isoformat()), esc(nxt.event_title), esc(iso), nxt.weekday,
               esc(nxt.date_text(now.year)), esc(nxt.time_text()), esc(nxt.bandcamp), cal))
    else:
        parts.append('<div class="block">\n'
                     '<p class="label label--gold tagline">Next</p>\n'
                     '<p class="name big">The next Prayer Watch will be announced here and by email.</p>\n'
                     '</div>')
    if latest:
        line = '\n<p class="fine">%s</p>' % esc(latest.line) if latest.line else ""
        parts.append(
            '<div class="block latest">\n'
            '<p class="label label--gold tagline">Latest album</p>\n'
            '<p class="name big">%s</p>%s\n'
            '<div class="btns"><a class="btn" href="%s">Listen on Bandcamp</a></div>\n'
            '</div>' % (esc(latest.name), line, esc(latest.bandcamp)))
    return "\n".join(parts)


def ld(obj):
    return ('<script type="application/ld+json">\n%s\n</script>'
            % json.dumps(obj, indent=2, ensure_ascii=False).replace("</", "<\\/"))


def render_event_ld(data, params, ctx):
    nxt = ctx["next"]
    if not nxt:
        return "<!-- no upcoming Prayer Watch -->"
    url = data["site"]["url"]
    return ld({
        "@context": "https://schema.org",
        "@type": "Event",
        "name": nxt.full_title,
        "description": ("Listeners press play on %s at the same time and pray on their own, each from where they are. "
                        "Prayers and requests go in the chat." % nxt.name),
        "startDate": nxt.start.isoformat(),
        "endDate": nxt.end.isoformat(),
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OnlineEventAttendanceMode",
        "location": {"@type": "VirtualLocation", "url": nxt.bandcamp},
        "url": url + "/prayer-watch/",
        "image": [url + "/" + data["site"]["share_image"]],
        "performer": {"@type": "MusicGroup", "name": data["site"]["name"], "url": url + "/"},
        "inLanguage": "en",
        "organizer": {"@type": "MusicGroup", "name": data["site"]["name"], "url": url + "/"},
    })


def render_group_ld(data, params, ctx=None):
    url = data["site"]["url"]
    return ld({
        "@context": "https://schema.org",
        "@type": "MusicGroup",
        "name": data["site"]["name"],
        "url": url + "/",
        "description": data["site"]["answer_line"],
        "genre": GENRES,
        "image": url + "/" + data["site"]["share_image"],
        "founder": {"@type": "Person", "name": "Steve Chab"},
        "sameAs": [link_for(data, k) for k in SOCIAL if link_for(data, k)],
    })


MARK = re.compile(r"(<!-- gen:([\w-]+)([^>]*?)-->)(.*?)(<!-- /gen:\2 -->)", re.S)


def fill(text, renderers):
    def sub(m):
        name = m.group(2)
        params = dict(re.findall(r"(\w+)=(\S+)", m.group(3)))
        if name not in renderers:
            fail("unknown region gen:%s" % name)
        return "%s\n%s\n%s" % (m.group(1), renderers[name](params), m.group(5))
    return MARK.sub(sub, text)


# ---------------------------------------------------------------- calendar, llms, sitemap

def ics_escape(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics_fold(line):
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    out, cur = [], ""
    for ch in line:
        limit = 75 if not out else 74
        if len((cur + ch).encode("utf-8")) > limit:
            out.append(cur)
            cur = ch
        else:
            cur += ch
    out.append(cur)
    return "\r\n ".join(out)


def render_ics(data, ctx):
    host = re.sub(r"^https?://", "", data["site"]["url"])
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Lowest Hallowed//Prayer Watch//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Lowest Hallowed Prayer Watch"]
    nxt = ctx["next"]
    if nxt:
        utc = ZoneInfo("UTC")
        fmt = "%Y%m%dT%H%M%SZ"
        desc = ("Press play on %s at the same time as everyone else and pray on your own. "
                "Prayers and requests go in the chat on Bandcamp. %s" % (nxt.name, nxt.bandcamp))
        lines += [
            "BEGIN:VEVENT",
            "UID:watch-%s@%s" % (nxt.start.strftime("%Y%m%d"), host),
            "DTSTAMP:" + nxt.start.astimezone(utc).strftime(fmt),
            "DTSTART:" + nxt.start.astimezone(utc).strftime(fmt),
            "DTEND:" + nxt.end.astimezone(utc).strftime(fmt),
            "SUMMARY:" + ics_escape(nxt.full_title),
            "DESCRIPTION:" + ics_escape(desc),
            "LOCATION:" + ics_escape("Online, on Bandcamp"),
            "URL:" + nxt.bandcamp,
            "BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:-PT15M",
            "DESCRIPTION:" + ics_escape(nxt.event_title), "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(ics_fold(l) for l in lines) + "\r\n"


def render_llms_this_month(data, params, ctx):
    nxt, latest, now = ctx["next"], ctx["latest"], ctx["now"]
    out = []
    if nxt:
        out.append("- Next: %s. %s, %s, %s. RSVP on Bandcamp: %s"
                   % (nxt.event_title, nxt.weekday, nxt.date_text(now.year), nxt.time_text(), nxt.bandcamp))
    else:
        out.append("- Next: to be announced on this site and by email.")
    if latest:
        tail = " " + latest.line if latest.line else ""
        out.append("- Latest album: %s.%s Listen on Bandcamp: %s" % (latest.name, tail, latest.bandcamp))
    return "\n".join(out)


def render_llms_links(data, params, ctx=None):
    out = []
    for key in SOCIAL:
        if link_for(data, key):
            out.append("- %s: %s" % (ICONS[key][0], link_for(data, key)))
    return "\n".join(out)


def render_sitemap(data, lastmods):
    url = data["site"]["url"]
    rows = []
    for path, _ in PAGES:
        rows.append("  <url>\n    <loc>%s%s</loc>\n    <lastmod>%s</lastmod>\n  </url>" % (url, path, lastmods[path]))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s\n</urlset>\n' % "\n".join(rows))


# ---------------------------------------------------------------- build

def build(data, now):
    tz = ZoneInfo(data["site"]["timezone"])
    releases = [Release(r, data["site"], tz) for r in data["releases"]]
    nxt, latest = pick(releases, now)
    ctx = {"next": nxt, "latest": latest, "now": now}

    outputs = {}
    for rel in HTML_FILES:
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        outputs[rel] = fill(text, {
            "head": lambda p: render_head(data, p),
            "footer": lambda p: render_footer(data, p),
            "signup": lambda p: render_signup(data, p),
            "icons": lambda p: render_icons(data, p.get("variant", "hero")),
            "social": lambda p, text=text: render_social(data, p, text),
            "this-month": lambda p: render_this_month(data, p, ctx),
            "event-ld": lambda p: render_event_ld(data, p, ctx),
            "group-ld": lambda p: render_group_ld(data, p),
        })

    outputs["calendar/prayer-watch.ics"] = render_ics(data, ctx)

    llms = ROOT / "llms.txt"
    if llms.exists():
        outputs["llms.txt"] = fill(llms.read_text(encoding="utf-8"), {
            "llms-this-month": lambda p: render_llms_this_month(data, p, ctx),
            "llms-links": lambda p: render_llms_links(data, p),
        })

    # sitemap: keep the old lastmod, bump it when the page content changed or the file was edited since
    sitemap = ROOT / "sitemap.xml"
    old = {}
    if sitemap.exists():
        for loc, mod in re.findall(r"<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>", sitemap.read_text(encoding="utf-8")):
            old[re.sub(r"^https?://[^/]+", "", loc)] = mod
    today = now.date().isoformat()
    lastmods = {}
    for path, rel in PAGES:
        f = ROOT / rel
        disk = f.read_text(encoding="utf-8") if f.exists() else None
        changed = rel in outputs and outputs[rel] != disk
        mtime = dt.date.fromtimestamp(f.stat().st_mtime).isoformat() if f.exists() else today
        base = old.get(path) or mtime
        lastmods[path] = today if changed else max(base, mtime) if path in old else base
    outputs["sitemap.xml"] = render_sitemap(data, lastmods)
    return outputs, ctx


def read_disk(rel):
    f = ROOT / rel
    return f.read_bytes().decode("utf-8") if f.exists() else None


def write_disk(rel, text):
    f = ROOT / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(text.encode("utf-8"))


def warnings(data):
    w = []
    if data["site"]["url"] == PLACEHOLDER_URL:
        w.append("domain is still the placeholder (%s). Run: python3 tools/update.py --domain YOURDOMAIN" % PLACEHOLDER_URL)
    for r in data["releases"]:
        if not (r.get("line") or "").strip():
            w.append("release %s has no one line on the music (line)" % r.get("numeral"))
    return w


def summary(ctx):
    nxt, latest, now = ctx["next"], ctx["latest"], ctx["now"]
    print("As of %s Eastern:" % now.strftime("%Y-%m-%d %H:%M"))
    if nxt:
        print("  Next:   %s, %s %s, %s" % (nxt.event_title, nxt.weekday, nxt.date_text(now.year), nxt.time_text()))
    else:
        print("  Next:   none scheduled (the page says it will be announced)")
    print("  Latest: %s" % (latest.name if latest else "none yet"))


# ---------------------------------------------------------------- commands

def cmd_add(path):
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.exists():
        fail("no such file: %s" % p)
    text = p.read_text(encoding="utf-8")
    m = re.match(r"#\s+([IVXL]+)\.\s+(.+)", text)
    d = re.search(r"Release:\s+\w{3}\s+(\w{3})\s+(\d{1,2}),\s+(\d{4})", text)
    slug = re.sub(r"^\d+-", "", p.stem)
    if not (m and d):
        fail("expected a first line like '# II. Title' and a line like 'Release: Fri Jan 8, 2027' in %s" % p.name)
    month = [x[:3] for x in MONTHS].index(d.group(1)) + 1
    release = dt.date(int(d.group(3)), month, int(d.group(2))).isoformat()
    data = load_data()
    if any(r["numeral"] == m.group(1) for r in data["releases"]):
        fail("release %s is already in data/releases.json" % m.group(1))
    entry = {
        "numeral": m.group(1),
        "title": m.group(2).strip(),
        "release": release,
        "event_name": "Prayer Watch",
        "bandcamp": "%s/album/%s" % (data["links"]["bandcamp"].rstrip("/"), slug),
        "line": "",
    }
    data["releases"].append(entry)
    data["releases"].sort(key=lambda r: r["release"])
    DATA.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Added %s. %s (release %s). Prayer Watch defaults to the night before at %s."
          % (entry["numeral"], entry["title"], release, data["site"]["watch_time"]))
    print("Open data/releases.json and write its \"line\" (one line on the music), add \"watch\" if the time differs,")
    print("then run: python3 tools/update.py")


def cmd_domain(host):
    host = re.sub(r"^https?://", "", host.strip()).strip("/")
    if not host or " " in host or "." not in host:
        fail("give a bare domain, like lowesthallowed.com")
    new = "https://" + host
    data = load_data()
    old = data["site"]["url"]
    if old == new:
        print("Domain already %s" % new)
    else:
        n = 0
        for f in ROOT.rglob("*"):
            if f.is_dir() or ".git" in f.parts or "tools" in f.parts or f.name == "README.md":
                continue
            if f.suffix not in {".html", ".xml", ".txt", ".ics", ".json"}:
                continue
            raw = f.read_bytes().decode("utf-8")
            if old in raw:
                f.write_bytes(raw.replace(old, new).encode("utf-8"))
                n += 1
        old_host = re.sub(r"^https?://", "", old)
        for f in [ROOT / "calendar" / "prayer-watch.ics"]:
            if f.exists():
                raw = f.read_bytes().decode("utf-8")
                f.write_bytes(raw.replace("@" + old_host, "@" + host).encode("utf-8"))
        print("Replaced %s with %s in %d files." % (old, new, n))
    (ROOT / "CNAME").write_text(host + "\n", encoding="utf-8")
    print("Wrote CNAME. In GitHub: Settings, Pages, custom domain %s, then enforce HTTPS." % host)


def main():
    ap = argparse.ArgumentParser(description="Regenerate the dated parts of the site from data/releases.json.")
    ap.add_argument("--check", action="store_true", help="change nothing; exit 1 if anything is stale")
    ap.add_argument("--add", metavar="PATH", help="add a release from an ambient-pedal docs/releases/NN-*.md file")
    ap.add_argument("--domain", metavar="HOST", help="set the real domain everywhere and write CNAME")
    ap.add_argument("--today", metavar="DATE", help="pretend it is this Eastern date (YYYY-MM-DD or YYYY-MM-DDTHH:MM)")
    args = ap.parse_args()

    if args.add:
        cmd_add(args.add)
        return
    if args.domain:
        cmd_domain(args.domain)

    data = load_data()
    tz = ZoneInfo(data["site"]["timezone"])
    if args.today:
        fmt = "%Y-%m-%dT%H:%M" if "T" in args.today else "%Y-%m-%d"
        now = dt.datetime.strptime(args.today, fmt).replace(tzinfo=tz)
    else:
        now = dt.datetime.now(tz)

    outputs, ctx = build(data, now)
    stale = [rel for rel, text in outputs.items() if read_disk(rel) != text]
    if args.check:
        summary(ctx)
        if stale:
            print("Stale (run python3 tools/update.py): " + ", ".join(stale))
        else:
            print("Everything is up to date.")
        for w in warnings(data):
            print("Open: " + w)
        sys.exit(1 if stale else 0)

    for rel in stale:
        write_disk(rel, outputs[rel])
    print("Updated: " + (", ".join(stale) if stale else "nothing, already current"))
    summary(ctx)
    for w in warnings(data):
        print("Open: " + w)


if __name__ == "__main__":
    main()
