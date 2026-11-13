"""
Welcome Card — naye member ki DP ko welcome background ke gol circle mein laga kar
automatic photo banata hai (agar photo mein neeche patti ho to usme group ka naam).
 
- Backgrounds: images/welcome_bg1.jpg ... welcome_bg5.jpg (GitHub images folder)
  Pehle local file dhoondhta hai, nahi mili to GitHub raw URL se leta hai.
- Photo kisi bhi size ki ho sakti hai (square ya 16:9). Circle photo mein KAHIN BHI ho (left, beech, right),
  bot khud sabse bada khaali safed gol hissa dhoondh leta hai. Circle bilkul safed (khaali) hona chahiye.
- Neeche safed khaali patti ho to usme group ka naam likhta hai. Patti NAHI ho to naam nahi likhta.
- Member ki DP nahi hai / hide hai to images/no_profile.jpg ("no profile picture" wali photo) circle mein lagti hai.
- no_profile.jpg bhi na mile / circle nahi mila / koi bhi error aaye -> False return hota hai
  aur welcome.py purani 5 photos wala welcome bhej deta hai (welcome kabhi miss nahi hota).
- Env: WELCOME_CARD_ENABLED=0 se band, WELCOME_BG_COUNT (default 5).
"""
 
import asyncio
import io
import logging
import os
import random
 
from PIL import Image, ImageDraw, ImageFont
 
from config import GROUP_ADDED_IMAGE
 
log = logging.getLogger(__name__)
 
ENABLED = os.environ.get("WELCOME_CARD_ENABLED", "1") != "0"
BG_COUNT = int(os.environ.get("WELCOME_BG_COUNT", "5") or 5)
OUTPUT_SIZE = 1080
NO_PROFILE_ZOOM = 1.04   # no_profile photo itna andar se kaati jati hai (circle ke kinare par kaala hissa na dikhe)
TEXT_COLOR = (70, 25, 110)
 
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_IMAGE_DIRS = [
    os.path.join(_ROOT, "images"),
    os.path.join(os.path.dirname(_ROOT), "images"),
    os.path.join(os.getcwd(), "images"),
]
_FONT_PATHS = [
    os.path.join(_ROOT, "fonts", "DejaVuSans-Bold.ttf"),
    os.path.join(os.getcwd(), "fonts", "DejaVuSans-Bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
_RAW_BASE = GROUP_ADDED_IMAGE.rsplit("/", 1)[0] if GROUP_ADDED_IMAGE else ""
 
_bg_cache = {}   # n -> (Image, circle, strip)
_bags = {}       # chat_id -> bachi hui background numbers
 
 
# ---------------------------------------------------------------- background load
def _local_bg(n):
    for d in _IMAGE_DIRS:
        for ext in ("jpg", "jpeg", "png"):
            p = os.path.join(d, f"welcome_bg{n}.{ext}")
            if os.path.isfile(p):
                return p
    return None
 
 
async def _download_bg(n):
    if not _RAW_BASE:
        return None
    import httpx
    for ext in ("jpg", "png"):
        url = f"{_RAW_BASE}/welcome_bg{n}.{ext}"
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                r = await c.get(url)
            if r.status_code == 200 and r.content:
                return r.content
        except Exception as e:
            log.warning("welcome_bg%s download failed (%s): %s", n, url, e)
    return None
 
 
def _is_white(p):
    return p[0] >= 232 and p[1] >= 232 and p[2] >= 232
 
 
def _run(px, w, h, x, y, dx, dy):
    """(x,y) se (dx,dy) disha mein jab tak safed hai chalta hai; aakhri safed pixel ka index deta hai."""
    while 0 <= x + dx < w and 0 <= y + dy < h and _is_white(px[x + dx, y + dy]):
        x += dx
        y += dy
    return x, y
 
 
def _find_white_circles(img):
    """
    Photo ko chhota karke saare bade safed hisse (connected) dhoondhta hai aur wo chunta hai jo gol (square bbox,
    circle jitna bhara hua) ho. Sabse bada gol hissa wapas deta hai: (cx, cy, r) poori photo ke naap mein, ya None.
    """
    w, h = img.size
    sw = 300
    sh = max(1, round(h * sw / w))
    small = img.resize((sw, sh), Image.BILINEAR)
    spx = small.load()
    mask = bytearray(sw * sh)
    for y in range(sh):
        for x in range(sw):
            if _is_white(spx[x, y]):
                mask[y * sw + x] = 1
 
    seen = bytearray(sw * sh)
    best = None
    for start in range(sw * sh):
        if not mask[start] or seen[start]:
            continue
        stack = [start]
        seen[start] = 1
        area = 0
        x0 = y0 = 10 ** 9
        x1 = y1 = -1
        while stack:
            i = stack.pop()
            y, x = divmod(i, sw)
            area += 1
            if x < x0: x0 = x
            if x > x1: x1 = x
            if y < y0: y0 = y
            if y > y1: y1 = y
            if x > 0 and mask[i - 1] and not seen[i - 1]:
                seen[i - 1] = 1; stack.append(i - 1)
            if x < sw - 1 and mask[i + 1] and not seen[i + 1]:
                seen[i + 1] = 1; stack.append(i + 1)
            if y > 0 and mask[i - sw] and not seen[i - sw]:
                seen[i - sw] = 1; stack.append(i - sw)
            if y < sh - 1 and mask[i + sw] and not seen[i + sw]:
                seen[i + sw] = 1; stack.append(i + sw)
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        if bw < 8 or bh < 8:
            continue
        aspect = bw / bh
        fill = area / (bw * bh)
        r_full = (bw + bh) / 4 * (w / sw)
        if 0.8 <= aspect <= 1.25 and 0.62 <= fill <= 0.95 and 0.12 * min(w, h) <= r_full <= 0.46 * min(w, h):
            if best is None or area > best[0]:
                best = (area, (x0 + x1 + 1) / 2 * (w / sw), (y0 + y1 + 1) / 2 * (h / sh), r_full)
    if best is None:
        return None
    return int(best[1]), int(best[2]), int(best[3])
 
 
def _detect_circle(img):
    """(cx, cy, r) — khaali safed gol circle, photo mein kahin bhi. Nahi mila to None."""
    w, h = img.size
    found = _find_white_circles(img)
    if not found:
        return None
    cx, cy, r0 = found
    px = img.load()
    if not (0 <= cx < w and 0 <= cy < h and _is_white(px[cx, cy])):
        return found
    # poore size par thoda sahi naap (kinare tak safed pixels naap kar)
    x0 = x1 = y0 = y1 = None
    for _ in range(2):
        x0, _y = _run(px, w, h, cx, cy, -1, 0)
        x1, _y = _run(px, w, h, cx, cy, 1, 0)
        cx = (x0 + x1) // 2
        _x, y0 = _run(px, w, h, cx, cy, 0, -1)
        _x, y1 = _run(px, w, h, cx, cy, 0, 1)
        cy = (y0 + y1) // 2
    r = min(x1 - x0, y1 - y0) // 2
    if abs(r - r0) > 0.15 * r0:
        return found  # naap bahut alag aaya, pehla andaza hi rakho
    return cx, cy, r
 
 
def _detect_strip(img):
    """Neeche ki safed khaali patti (x0, y0, x1, y1). Patti NAHI hai to None (tab naam nahi likhte)."""
    w, h = img.size
    px = img.load()
    sx, sy = w // 2, int(h * 0.93)
    if not _is_white(px[sx, sy]):
        return None
    _x, y0 = _run(px, w, h, sx, sy, 0, -1)
    _x, y1 = _run(px, w, h, sx, sy, 0, 1)
    ym = (y0 + y1) // 2
    x0, _y = _run(px, w, h, sx, ym, -1, 0)
    x1, _y = _run(px, w, h, sx, ym, 1, 0)
    if not (0.04 * h <= (y1 - y0) <= 0.25 * h) or (x1 - x0) < 0.5 * w:
        return None
    return x0, y0, x1, y1
 
 
async def _get_bg(n):
    if n in _bg_cache:
        return _bg_cache[n]
    path = _local_bg(n)
    data = None
    if path:
        with open(path, "rb") as f:
            data = f.read()
    else:
        data = await _download_bg(n)
    if not data:
        return None
    img = Image.open(io.BytesIO(data)).convert("RGB")
    circle = _detect_circle(img)
    if not circle:
        # khaali safed gol circle nahi mila -> is photo ko skip karo (DP galat jagah na lage)
        log.warning("welcome_bg%s: khaali safed circle nahi mila, ye photo skip ho rahi hai", n)
        _bg_cache[n] = None
        return None
    entry = (img, circle, _detect_strip(img))
    _bg_cache[n] = entry
    log.info("welcome_bg%s ready: size=%s circle=%s strip=%s", n, img.size, entry[1], entry[2])
    return entry
 
 
def _bg_order(chat_id):
    """Har chat mein agla background (5 me se, repeat tab tak nahi jab tak sab na aa jayein)."""
    bag = _bags.get(chat_id)
    if not bag:
        bag = list(range(1, BG_COUNT + 1))
        random.shuffle(bag)
        last = _bags.get(("last", chat_id))
        if last and len(bag) > 1 and bag[-1] == last:
            bag[0], bag[-1] = bag[-1], bag[0]
    _bags[chat_id] = bag
    return bag
 
 
# ---------------------------------------------------------------- drawing
def _load_font(size):
    for p in _FONT_PATHS:
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default()
 
 
def _clean_name(title):
    """Sirf Latin letters/numbers/punctuation rakhta hai (emoji, fancy/Hindi letters photo par toot jate hain)."""
    keep = []
    for c in title or "":
        if (ord(c) < 0x250 and c.isprintable()) or c in "–—’‘“”":
            keep.append(c)
    return " ".join("".join(keep).split())
 
 
def _compose(entry, dp_bytes, title, zoom=1.0):
    bg, (cx, cy, r), strip = entry
    img = bg.copy()
 
    # DP -> square -> gol
    d = 2 * r + 2
    dp = Image.open(io.BytesIO(dp_bytes)).convert("RGB")
    s = int(min(dp.size) / zoom)
    left, top = (dp.width - s) // 2, (dp.height - s) // 2
    dp = dp.crop((left, top, left + s, top + s)).resize((d, d), Image.LANCZOS)
    ss = 3
    mask = Image.new("L", (d * ss, d * ss), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d * ss - 1, d * ss - 1), fill=255)
    mask = mask.resize((d, d), Image.LANCZOS)
    img.paste(dp, (cx - d // 2, cy - d // 2), mask)
 
    # neeche patti mein group ka naam
    name = _clean_name(title) if strip else ""
    if name:
        sx0, sy0, sx1, sy1 = strip
        draw = ImageDraw.Draw(img)
        box_w, box_h = (sx1 - sx0) * 0.92, (sy1 - sy0) * 0.70
        size = int(box_h)
        font = _load_font(size)
        while size > 16:
            l, t, rr, b = draw.textbbox((0, 0), name, font=font)
            if (rr - l) <= box_w and (b - t) <= box_h:
                break
            size -= 2
            font = _load_font(size)
        draw.text(((sx0 + sx1) / 2, (sy0 + sy1) / 2), name, font=font, fill=TEXT_COLOR, anchor="mm")
 
    if img.width > OUTPUT_SIZE:
        img = img.resize((OUTPUT_SIZE, int(img.height * OUTPUT_SIZE / img.width)), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=90)
    return out.getvalue()
 
 
# ---------------------------------------------------------------- telegram
_default_dp = None   # no_profile photo ke bytes (ek baar load hoke yaad rehte hain)
 
 
async def _default_dp_bytes():
    """images/no_profile.jpg: jis member ki DP nahi (ya hide hai) uske circle mein ye photo lagti hai."""
    global _default_dp
    if _default_dp:
        return _default_dp
    data = None
    for d in _IMAGE_DIRS:
        for ext in ("jpg", "jpeg", "png", "jfif"):
            path = os.path.join(d, f"no_profile.{ext}")
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    data = f.read()
                break
        if data:
            break
    if not data and _RAW_BASE:
        import httpx
        for ext in ("jpg", "png"):
            url = f"{_RAW_BASE}/no_profile.{ext}"
            try:
                async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                    r = await c.get(url)
                if r.status_code == 200 and r.content:
                    data = r.content
                    break
            except Exception as e:
                log.warning("no_profile download failed (%s): %s", url, e)
    if data:
        _default_dp = data
    return data
 
 
async def _get_dp_bytes(context, user):
    photos = await context.bot.get_user_profile_photos(user.id, limit=1)
    if not photos or not photos.total_count or not photos.photos:
        return None
    f = await context.bot.get_file(photos.photos[0][-1].file_id)
    return bytes(await f.download_as_bytearray())
 
 
async def _build_card(context, chat, member):
    try:
        dp = await _get_dp_bytes(context, member)
    except Exception as e:
        log.warning("welcome card: DP read failed for user %s: %s", member.id, e)
        dp = None
    zoom = 1.0
    if not dp:
        dp = await _default_dp_bytes()   # DP nahi / hide hai -> "no profile picture" wali photo
        zoom = NO_PROFILE_ZOOM
        if not dp:
            log.info("welcome card: no DP and no no_profile image for user %s -> old photo", member.id)
            return None
    bag = _bg_order(chat.id)
    tried = 0
    while bag and tried < BG_COUNT:
        n = bag.pop()
        tried += 1
        entry = await _get_bg(n)
        if not entry:
            continue
        card = await asyncio.to_thread(_compose, entry, dp, chat.title, zoom)
        _bags[("last", chat.id)] = n
        return card
    return None
 
 
async def send_welcome_card(context, chat, member, text, reply_to=None, parse_mode=None):
    """Card bana kar caption (welcome text) ke saath bhejta hai. Bheja gaya to True, warna False."""
    if not ENABLED:
        return False
    try:
        card = await asyncio.wait_for(_build_card(context, chat, member), timeout=12)
    except Exception:
        log.exception("welcome card build failed in chat %s", chat.id)
        return False
    if not card:
        return False
 
    caption = text[:1024]
    for rt in ([reply_to, None] if reply_to is not None else [None]):
        try:
            await context.bot.send_photo(chat.id, photo=card, caption=caption,
                                         reply_to_message_id=rt, parse_mode=parse_mode)
            return True
        except Exception as e:
            log.warning("welcome card send failed (reply_to=%s): %s", rt, e)
    return False
 
