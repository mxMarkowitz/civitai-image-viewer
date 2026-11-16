import http.server
import urllib.request
import urllib.parse
import urllib.error
import json
import webbrowser

PORT = 8080
DEFAULT_API_KEY = ""

# Civitai's browsingLevel is a bitmask (None/PG=1, Soft/PG13=2, Mature/R=4, X=8).
# The legacy `nsfw` enum filter is documented as not strictly enforced, so we
# OR together exactly the levels the user checked and send that as
# browsingLevel instead -- browsingLevel takes precedence over nsfw. Each
# level is independent (checking only "X" returns X-rated content only, not
# X-and-everything-milder).
NSFW_LEVEL_BITS = {
    "None": 1,
    "Soft": 2,
    "Mature": 4,
    "X": 8,
}

def browsing_level_for(selected_levels):
    """Bitmask OR of exactly the selected level names (unrecognized names ignored)."""
    mask = 0
    for name in selected_levels:
        mask |= NSFW_LEVEL_BITS.get(name, 0)
    return mask or NSFW_LEVEL_BITS["None"]

SAVED_TAGS = {
    "anime": "4",
    "portrait": "5193",
    "woman": "5163",
    "man": "5164",
    "cyberpunk": "111768",
    "landscape": "5201",
    "fantasy": "5198",
    "sci-fi": "5204",
    "realistic": "111754",
    "illustration": "5194",
    "concept art": "5207",
    "dark": "5218",
    "neon": "111773"
}

HTML_PAGE = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Civitai Multi-Tag Viewer</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #141517; color: #e9ecef; margin: 0; padding: 20px; }}
  .controls {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; background: #1a1b1e; padding: 15px; border-radius: 8px; }}
  input, select, button {{ padding: 8px 12px; border-radius: 6px; border: 1px solid #373a40; background: #25262b; color: #fff; font-size: 14px; }}
  #tagsInput {{ flex: 2; min-width: 240px; }}
  #apiKeyInput {{ flex: 1; min-width: 180px; }}
  button {{ background: #1971c2; border: none; cursor: pointer; font-weight: 600; }}
  button:hover {{ background: #1864ab; }}
  .saved-tags {{ margin-bottom: 16px; font-size: 12px; color: #909296; }}
  .tag-pill {{ display: inline-block; background: #25262b; border: 1px solid #373a40; padding: 3px 8px; border-radius: 12px; margin: 2px; cursor: pointer; color: #ced4da; }}
  .tag-pill:hover {{ border-color: #4dabf7; color: #fff; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }}
  .card {{ background: #1a1b1e; border-radius: 8px; overflow: hidden; border: 1px solid #2c2e33; display: flex; flex-direction: column; }}
  .card img, .card video {{ width: 100%; height: 320px; object-fit: cover; cursor: pointer; background: #000; }}
  .meta {{ padding: 10px; font-size: 12px; color: #adb5bd; max-height: 110px; overflow-y: auto; }}
  .meta a {{ color: #4dabf7; text-decoration: none; font-weight: bold; }}
  .status-bar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; font-size: 14px; color: #909296; }}
</style>
</head>
<body>

<div class="controls">
  <input id="tagsInput" type="text" placeholder="Tag names or IDs (e.g., anime, portrait, 111768)" />
  <input id="apiKeyInput" type="password" value="{DEFAULT_API_KEY}" placeholder="Civitai API Key" />
  <select id="sortSelect">
    <option value="Most Reactions">Most Reactions</option>
    <option value="Most Comments">Most Comments</option>
    <option value="Newest">Newest</option>
  </select>
  <select id="periodSelect">
    <option value="AllTime">All Time</option>
    <option value="Year">Year</option>
    <option value="Month">Month</option>
    <option value="Week">Week</option>
  </select>
  <span class="nsfw-checks" id="nsfwChecks" style="display:flex; align-items:center; gap:10px; background:#25262b; border:1px solid #373a40; border-radius:6px; padding:8px 12px;">
    <label style="display:flex; align-items:center; gap:4px; cursor:pointer;"><input type="checkbox" value="None" checked> SFW</label>
    <label style="display:flex; align-items:center; gap:4px; cursor:pointer;"><input type="checkbox" value="Soft" checked> Soft</label>
    <label style="display:flex; align-items:center; gap:4px; cursor:pointer;"><input type="checkbox" value="Mature" checked> Mature</label>
    <label style="display:flex; align-items:center; gap:4px; cursor:pointer;"><input type="checkbox" value="X" checked> X</label>
  </span>
  <select id="typeSelect">
    <option value="">All Media</option>
    <option value="image">Images Only</option>
    <option value="video">Videos Only</option>
  </select>
  <select id="limitSelect">
    <option value="20">20 per page</option>
    <option value="50">50 per page</option>
    <option value="100">100 per page</option>
    <option value="200" selected>200 per page</option>
  </select>
  <button onclick="searchImages()">Search Civitai</button>
</div>

<div class="saved-tags" id="savedTagsBar">Saved Tags (click to add): </div>

<div class="status-bar">
  <span id="status">Enter tag names or numeric IDs and click Search. Check your Python console for raw API logs.</span>
  <div>
    <button id="sortLenBtn" onclick="sortByLength()">Sort by Length ⬍</button>
    <button id="nextBtn" onclick="loadNextPage()" style="display:none;">Next Page ➔</button>
  </div>
</div>
<div id="grid" class="grid"></div>

<div class="status-bar" style="margin-top: 16px;">
  <span></span>
  <button id="nextBtnBottom" onclick="loadNextPage()" style="display:none;">Next Page ➔</button>
</div>

<script>
const SAVED_TAGS = {json.dumps(SAVED_TAGS)};
let nextCursor = null;

const bar = document.getElementById('savedTagsBar');
Object.keys(SAVED_TAGS).forEach(name => {{
  const pill = document.createElement('span');
  pill.className = 'tag-pill';
  pill.textContent = name + ' (' + SAVED_TAGS[name] + ')';
  pill.onclick = () => {{
    const input = document.getElementById('tagsInput');
    const current = input.value.trim();
    input.value = current ? current + ', ' + name : name;
  }};
  bar.appendChild(pill);
}});

async function searchImages(cursor = null) {{
  const tags = document.getElementById('tagsInput').value;
  const apiKey = document.getElementById('apiKeyInput').value.trim();
  const sort = document.getElementById('sortSelect').value;
  const period = document.getElementById('periodSelect').value;
  const nsfwLevels = Array.from(document.querySelectorAll('#nsfwChecks input[type=checkbox]:checked')).map(cb => cb.value);
  const mediaType = document.getElementById('typeSelect').value;
  const limit = document.getElementById('limitSelect').value;
  const status = document.getElementById('status');
  const grid = document.getElementById('grid');
  const nextBtn = document.getElementById('nextBtn');
  const nextBtnBottom = document.getElementById('nextBtnBottom');

  if (nsfwLevels.length === 0) {{
    status.textContent = 'Select at least one maturity level.';
    return;
  }}

  const params = new URLSearchParams({{ tags, sort, period, apiKey, limit }});
  params.set('nsfwLevels', nsfwLevels.join(','));
  if (mediaType) params.set('type', mediaType);
  if (cursor) params.set('cursor', cursor);

  status.textContent = 'Querying Civitai servers...';
  if (!cursor) {{
    grid.innerHTML = '';
    nextBtn.style.display = 'none';
    nextBtnBottom.style.display = 'none';
  }}

  try {{
    const res = await fetch('/api/search?' + params.toString());
    const data = await res.json();
    console.log('Civitai API Response:', data);
    if (data.error) throw new Error(data.error);

    nextCursor = data.metadata?.nextCursor || null;
    const displayVal = nextCursor ? 'inline-block' : 'none';
    nextBtn.style.display = displayVal;
    nextBtnBottom.style.display = displayVal;
    status.textContent = 'Showing ' + data.items.length + ' results.';

    data.items.forEach(item => {{
      const card = document.createElement('div');
      card.className = 'card';
      card.dataset.mediaType = item.type;
      const media = item.type === 'video'
        ? '<video src="' + item.url + '" muted loop playsinline preload="metadata" onmouseover="this.play()" onmouseout="this.pause()"></video>'
        : '<img src="' + item.url + '" loading="lazy" alt="Civitai Image ' + item.id + '">';
      const username = item.username || 'unknown';
      card.innerHTML =
        '<a href="https://civitai.red/images/' + item.id + '" target="_blank">' +
        media +
        '</a>' +
        '<div class="meta">' +
        '<a href="https://civitai.red/images/' + item.id + '" target="_blank">Open on Civitai ↗</a><br><br>' +
        'By <a href="https://civitai.red/user/' + encodeURIComponent(username) + '" target="_blank">' + username + '</a>' +
        '</div>';
      grid.appendChild(card);
    }});
  }} catch (err) {{
    console.error('Search Error:', err);
    status.textContent = 'Error: ' + err.message;
  }}
}}

function loadNextPage() {{
  if (nextCursor) searchImages(nextCursor);
}}

let lengthSortAscending = true;

function getVideoDuration(videoEl) {{
  return new Promise(resolve => {{
    if (videoEl.readyState >= 1 && !isNaN(videoEl.duration)) {{
      resolve(videoEl.duration);
      return;
    }}
    const onReady = () => {{
      videoEl.removeEventListener('loadedmetadata', onReady);
      resolve(isNaN(videoEl.duration) ? 0 : videoEl.duration);
    }};
    videoEl.addEventListener('loadedmetadata', onReady);
    // Fallback in case metadata never fires (broken/blocked source).
    setTimeout(() => {{ videoEl.removeEventListener('loadedmetadata', onReady); resolve(0); }}, 8000);
  }});
}}

async function sortByLength() {{
  const grid = document.getElementById('grid');
  const status = document.getElementById('status');
  const cards = Array.from(grid.children);
  const videoCards = cards.filter(c => c.dataset.mediaType === 'video');
  const otherCards = cards.filter(c => c.dataset.mediaType !== 'video');

  if (videoCards.length === 0) {{
    status.textContent = 'No videos currently loaded to sort. Set "Videos Only" and search/page first.';
    return;
  }}

  status.textContent = 'Reading durations for ' + videoCards.length + ' video(s)...';

  const withDurations = await Promise.all(videoCards.map(async card => {{
    const vid = card.querySelector('video');
    const duration = vid ? await getVideoDuration(vid) : 0;
    return {{ card, duration }};
  }}));

  withDurations.sort((a, b) => lengthSortAscending ? a.duration - b.duration : b.duration - a.duration);
  lengthSortAscending = !lengthSortAscending;

  grid.innerHTML = '';
  withDurations.forEach(({{ card }}) => grid.appendChild(card));
  otherCards.forEach(card => grid.appendChild(card));

  status.textContent = 'Sorted ' + withDurations.length + ' video(s) by length (' +
    (lengthSortAscending ? 'next: ascending' : 'next: descending') + ').';
}}
</script>
</body>
</html>"""

def resolve_tags(raw_tags):
    if not raw_tags:
        return ""
    resolved = []
    for part in raw_tags.split(","):
        cleaned = part.strip().lower()
        if not cleaned:
            continue
        if cleaned in SAVED_TAGS:
            resolved.append(SAVED_TAGS[cleaned])
        elif cleaned.isdigit():
            resolved.append(cleaned)
        else:
            print(f"[WARN] Unknown tag name '{cleaned}'", flush=True)
    return ",".join(resolved)

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif parsed.path == "/api/search":
            qs = urllib.parse.parse_qs(parsed.query)
            raw_tags = qs.get("tags", [""])[0]
            resolved_tags = resolve_tags(raw_tags)

            try:
                limit = int(qs.get("limit", ["200"])[0])
            except ValueError:
                limit = 200
            limit = max(1, min(limit, 200))

            selected_nsfw_levels = [lvl for lvl in qs.get("nsfwLevels", ["None"])[0].split(",") if lvl]
            api_params = {
                "limit": str(limit),
                "sort": qs.get("sort", ["Most Reactions"])[0],
                "period": qs.get("period", ["AllTime"])[0],
                # browsingLevel takes precedence over the legacy nsfw enum and
                # lets us OR together exactly the checked levels.
                "browsingLevel": str(browsing_level_for(selected_nsfw_levels)),
            }
            if resolved_tags:
                api_params["tags"] = resolved_tags
            cursor = qs.get("cursor", [""])[0]
            if cursor:
                api_params["cursor"] = cursor
            media_type = qs.get("type", [""])[0]
            if media_type:
                api_params["type"] = media_type

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept": "application/json",
            }
            api_key = qs.get("apiKey", [""])[0]
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            api_url = "https://civitai.com/api/v1/images?" + urllib.parse.urlencode(api_params)
            print("\n" + "=" * 60, flush=True)
            print(f"[REQUEST] GET {api_url}", flush=True)

            req = urllib.request.Request(api_url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    status_code = resp.getcode()
                    raw = resp.read().decode("utf-8", errors="replace")

                print(f"[RESPONSE] HTTP {status_code} | Length: {len(raw)} bytes", flush=True)
                if raw.lstrip().startswith("<"):
                    print("[RESPONSE BODY PREVIEW (HTML)]:", raw[:400], flush=True)
                    raise ValueError("Civitai returned HTML instead of JSON (API may be down for maintenance).")

                parsed_json = json.loads(raw)
                items_count = len(parsed_json.get("items", []))
                print(f"[RESPONSE DATA] Returned {items_count} items. Metadata: {parsed_json.get('metadata')}", flush=True)
                if items_count > 0:
                    print("[FIRST ITEM PREVIEW]:", json.dumps(parsed_json["items"][0], indent=2)[:500], flush=True)

                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(raw.encode("utf-8"))
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                print(f"[HTTP ERROR] {e.code} {e.reason}: {err_body[:500]}", flush=True)
                self.send_response(e.code)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"HTTP {e.code}: {e.reason}"}).encode("utf-8"))
            except Exception as e:
                print(f"[ERROR] {e}", flush=True)
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.end_headers()

                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
assigned_port = server.server_address[1]
server_url = f"http://127.0.0.1:{assigned_port}"
print(f"Server running at {server_url}", flush=True)
webbrowser.open(server_url)
server.serve_forever()
