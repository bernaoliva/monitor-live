# -*- coding: utf-8 -*-
"""
Monitor de Lives YouTube â€” CazÃ©TV
Coleta chat â†’ classifica via Cloud Run (DistilBERT) â†’ grava no Firestore
Dashboard: Vercel (Next.js)
"""

import os
import re
import json
import time
import traceback
import hashlib
import signal
import requests
import queue as _stdlib_queue
from threading import Thread, Lock, Event
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Optional, Set
from collections import deque

# Firestore â€” ativa se FIREBASE_CREDENTIALS estiver definido
try:
    import firebase_admin
    from firebase_admin import credentials as fb_credentials, firestore as fb_firestore
    _fb_app = None
    _fs     = None

    def _get_fs():
        global _fb_app, _fs
        if _fs is None:
            cred_path = os.environ.get("FIREBASE_CREDENTIALS", "firebase-credentials.json")
            db_id = os.environ.get("FIRESTORE_DATABASE", "(default)")
            abs_cred = os.path.abspath(cred_path)
            if os.path.exists(abs_cred) and not firebase_admin._apps:
                _fb_app = firebase_admin.initialize_app(fb_credentials.Certificate(abs_cred))
                _fs = fb_firestore.client(database_id=db_id)
            elif firebase_admin._apps:
                _fs = fb_firestore.client(database_id=db_id)
            else:
                print(f"[Firestore] AVISO: credenciais nao encontradas em {abs_cred!r}")
        return _fs

    FIRESTORE_ENABLED = True
except ImportError:
    FIRESTORE_ENABLED = False
    def _get_fs(): return None

import pytchat

# â”€â”€â”€ CONSTANTS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
MAX_COMMENT_LENGTH = 5000
OEMBED_CACHE_TTL   = 300

# â”€â”€â”€ CONFIG â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
CHANNELS = [
    {"display": "CAZETV", "name": "CazÃ©TV", "handle": "@CazeTV", "channel_id": ""},
]

SUPERVISOR_POLL_SECONDS        = 8
CHAT_RETRY_SECONDS             = 10
QUEUE_POLL_SECONDS             = 0.5
LIVE_MAX_RESULTS               = 20
MISS_TOLERANCE                 = 3

WATCH_VERIFY_TIMEOUT           = 10
SCRAPE_TIMEOUT                 = 15
DISCOVERY_TIMEOUT              = 8

CHAT_MAX_DRAIN_CYCLES          = 64
CHAT_MAX_BATCH_PER_DRAIN       = 500
CHAT_POLL_SLEEP_EMPTY          = 0.03
CHAT_POLL_SLEEP_BETWEEN_DRAINS = 0.0
CHAT_IDLE_WARN_SECONDS         = 8
CHAT_IDLE_RECREATE_SECONDS     = 20
CHAT_HARD_WATCHDOG_SECONDS     = 45
CHAT_DEDUP_WINDOW              = 5000

# IA â€” Cloud Run (DistilBERT fine-tuned)
SERVING_URL     = os.environ.get("SERVING_URL", "SUA_URL_CLOUD_RUN")
SERVING_TIMEOUT = int(os.environ.get("SERVING_TIMEOUT", "15"))
LLM_WORKERS     = max(1, int(os.environ.get("LLM_WORKERS", "4")))

# Batch de classificaÃ§Ã£o â€” GPU processa atÃ© 64 textos por chamada
BATCH_SIZE     = int(os.environ.get("BATCH_SIZE",   "64"))   # textos por request ao Cloud Run
BATCH_MAX_WAIT = float(os.environ.get("BATCH_MAX_WAIT", "0.1"))  # s â€” tempo mÃ¡x para montar batch
FS_FLUSH_SECS  = float(os.environ.get("FS_FLUSH_SECS",  "3.0"))  # s â€” flush contadores live doc

# AudiÃªncia â€” YouTube Data API v3
YOUTUBE_API_KEY      = os.environ.get("YOUTUBE_API_KEY", "SUA_YOUTUBE_API_KEY")
GPU_VIEWER_THRESHOLD = int(os.environ.get("GPU_VIEWER_THRESHOLD", "270000"))
VIEWER_POLL_SECS     = int(os.environ.get("VIEWER_POLL_SECS", "60"))

# HTTP
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}
COOKIE_CONSENT = {
    "CONSENT": "YES+cb.20240618-17-p0.pt+FX+123",
    "PREF": "f6=40000000&hl=pt-BR",
    "GPS": "1",
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
for k, v in COOKIE_CONSENT.items():
    SESSION.cookies.set(k, v, domain=".youtube.com")

DEFAULT_PARAMS = {"hl": "pt-BR", "gl": "BR"}

_oembed_cache: Dict[str, Tuple[float, str]] = {}
_oembed_lock = Lock()

# API v3 search cache — evita estourar quota (100 units/call, 10k/dia)
_api_cache: Dict[str, Tuple[float, List[Tuple[str, str]]]] = {}  # channel_id → (ts, results)
API_CACHE_TTL = 60  # segundos

# Chat-aware miss tolerance — rastreia última msg recebida por live
_last_chat_msg_ts: Dict[str, float] = {}  # video_id → timestamp da última msg
CHAT_ALIVE_GRACE = 30  # se recebeu msg nos últimos 30s, live está ativa

# â”€â”€â”€ LOGGING â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
os.makedirs("debug_logs", exist_ok=True)

def _log_debug(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{ts}] {msg}"
    print(log_msg)
    with open(os.path.join("debug_logs", f"debug_{datetime.now().strftime('%Y%m%d')}.log"), "a", encoding="utf-8") as f:
        f.write(log_msg + "\n")

# â”€â”€â”€ FIRESTORE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def fs_upsert_live(video_id: str, channel: str, title: str, url: str, status: str = "active"):
    if not FIRESTORE_ENABLED: return
    try:
        fs = _get_fs()
        if not fs: return
        fs.collection("lives").document(video_id).set({
            "channel":       channel,
            "title":         title,
            "url":           url,
            "status":        status,
            "last_seen_at":  now_iso(),
            "title_history": fb_firestore.ArrayUnion([title]),
        }, merge=True)
    except Exception as e:
        _log_debug(f"[Firestore] fs_upsert_live error: {e}")

def fs_touch_live(video_id: str, channel: str, url: str, status: str = "active"):
    """Atualiza heartbeat da live sem sobrescrever titulo."""
    if not FIRESTORE_ENABLED: return
    try:
        fs = _get_fs()
        if not fs: return
        fs.collection("lives").document(video_id).set({
            "channel":      channel,
            "url":          url,
            "status":       status,
            "last_seen_at": now_iso(),
        }, merge=True)
    except Exception as e:
        _log_debug(f"[Firestore] fs_touch_live error: {e}")

def fs_add_comment(video_id: str, comment_id: str, author: str, text: str,
                   ts: str, is_technical: bool, category, issue, severity: str):
    if not FIRESTORE_ENABLED: return
    try:
        fs = _get_fs()
        if not fs: return
        live_ref = fs.collection("lives").document(video_id)
        # Salva todos os comentÃ¡rios (tÃ©cnicos e normais) para o feed completo
        live_ref.collection("comments").document(comment_id).set({
            "author":       author,
            "text":         text,
            "ts":           ts,
            "is_technical": is_technical,
            "category":     category if is_technical else None,
            "issue":        issue    if is_technical else None,
            "severity":     severity if is_technical else "none",
        })
        # Incrementa contadores para todos os comentÃ¡rios
        live_ref.update({
            "total_comments":     fb_firestore.Increment(1),
            "technical_comments": fb_firestore.Increment(1 if is_technical else 0),
            **({"issue_counts": {f"{category}:{issue}": fb_firestore.Increment(1)}}
               if is_technical and category and issue else {}),
        })
        # Agrega por minuto para o grÃ¡fico (evita o browser baixar todos os comentÃ¡rios)
        try:
            # Extrai HH:mm de qualquer formato: ISO (2026-02-19T18:57:29) ou espaÃ§o (2026-02-19 18:57:29)
            time_part = ts.split("T")[-1] if "T" in ts else ts.split(" ")[-1] if " " in ts else ts
            minute_key = time_part[:5]  # HH:mm
            if minute_key and len(minute_key) == 5:
                live_ref.collection("minutes").document(minute_key).set({
                    "total":     fb_firestore.Increment(1),
                    "technical": fb_firestore.Increment(1 if is_technical else 0),
                }, merge=True)
        except Exception:
            pass  # nÃ£o falha se agregar der erro
    except Exception as e:
        _log_debug(f"[Firestore] fs_add_comment error: {e}")

def fs_mark_live_ended(video_id: str):
    if not FIRESTORE_ENABLED: return
    try:
        fs = _get_fs()
        if not fs: return
        fs.collection("lives").document(video_id).update({
            "status":   "ended",
            "ended_at": now_iso(),
        })
    except Exception as e:
        _log_debug(f"[Firestore] fs_mark_live_ended error: {e}")

# â”€â”€â”€ ESTADO (apenas controle de processos) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
running_monitors:    Dict[Tuple[str, str], Thread] = {}
_stop_events:        Dict[Tuple[str, str], Event]  = {}
last_start_attempt:  Dict[Tuple[str, str], float]  = {}
active_videos:       Dict[str, Set[str]]            = {}  # channel_display â†’ video_ids ativos
state_lock = Lock()

def stop_monitor(channel_display: str, video_id: str):
    """Sinaliza parada do thread de chat daquela live e remove do dict."""
    key = (channel_display, video_id)
    ev = _stop_events.pop(key, None)
    if ev:
        ev.set()
    thr = running_monitors.pop(key, None)
    if thr and thr.is_alive():
        thr.join(timeout=5)

# â”€â”€â”€ UTILS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def now_iso() -> str:
    br_tz = timezone(timedelta(hours=-3))
    return datetime.now(br_tz).isoformat()

def safe_get(url: str, params: Optional[dict] = None, timeout: int = SCRAPE_TIMEOUT,
             allow_redirects: bool = True) -> Optional[str]:
    try:
        p = dict(DEFAULT_PARAMS)
        if params: p.update(params)
        r = SESSION.get(url, params=p, timeout=timeout, allow_redirects=allow_redirects)
        r.raise_for_status()
        if "consent" in (r.url or "").lower() or "consent" in r.text[:600].lower():
            SESSION.cookies.set("CONSENT", COOKIE_CONSENT["CONSENT"], domain=".youtube.com")
            r = SESSION.get(url, params=p, timeout=timeout, allow_redirects=True)
            r.raise_for_status()
        return r.text
    except Exception as e:
        _log_debug(f"safe_get error for {url}: {e}")
        return None

def oembed_title(video_id: str) -> str:
    now_ts = time.time()
    with _oembed_lock:
        cached = _oembed_cache.get(video_id)
        if cached and (now_ts - cached[0]) < OEMBED_CACHE_TTL:
            return cached[1]
    try:
        o = SESSION.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=6,
        )
        if o.status_code == 200:
            title = o.json().get("title", video_id)
            with _oembed_lock:
                _oembed_cache[video_id] = (now_ts, title)
            return title
    except Exception:
        pass
    with _oembed_lock:
        _oembed_cache[video_id] = (now_ts, video_id)
    return video_id

# â”€â”€â”€ LIVE DISCOVERY â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def resolve_channel_id_by_handle(handle: str) -> str:
    """Resolve o channel_id (UC...) a partir do @handle."""
    h = (handle or "").strip().lstrip("@")
    if not h:
        return ""
    tried = []
    for suffix in ["/about", "/featured", "/streams", "/videos", "/live", ""]:
        url = f"https://www.youtube.com/@{h}{suffix}"
        tried.append(url)
        html = safe_get(url)
        if not html:
            continue
        for pat in [
            r'"channelId"\s*:\s*"(UC[0-9A-Za-z_-]{22})"',
            r'"externalId"\s*:\s*"(UC[0-9A-Za-z_-]{22})"',
            r'channel/(UC[0-9A-Za-z_-]{22})',
            r'"browseId"\s*:\s*"(UC[0-9A-Za-z_-]{22})"',
        ]:
            m = re.search(pat, html)
            if m:
                return m.group(1)
    _log_debug(f"[resolve_channel_id_by_handle] nÃ£o achou UC para @{h} â€” tentativas: {tried}")
    return ""

def extract_json_blob(html, patterns):
    if not html: return None
    for pat in patterns:
        m = re.search(pat, html, flags=re.DOTALL)
        if not m: continue
        blob = m.group(1)
        depth = 0; end = 0
        for i, ch in enumerate(blob):
            if ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0: end = i + 1; break
        if end:
            try: return json.loads(blob[:end])
            except Exception: pass
    return None

def is_live_now(video_id: str):
    """Verifica se um video_id estÃ¡ AO VIVO. Retorna (bool_is_live, title)."""
    html = safe_get("https://www.youtube.com/watch", params={"v": video_id}, timeout=WATCH_VERIFY_TIMEOUT)
    if not html:
        return (False, None)

    player = extract_json_blob(
        html,
        [
            r'ytInitialPlayerResponse\s*=\s*(\{.*?\})\s*;',
            r'"ytInitialPlayerResponse"\s*:\s*(\{.*?\})\s*,\s*"ytInitialData"',
        ],
    )

    def jget(d, path, default=None):
        cur = d
        try:
            for k in path:
                cur = cur[k] if isinstance(cur, dict) else cur[k]
            return cur
        except Exception:
            return default

    title = None
    if player:
        title = jget(player, ["videoDetails", "title"], None)

        # Descarta de imediato qualquer live ainda nÃ£o iniciada
        is_upcoming  = jget(player, ["videoDetails", "isUpcoming"], False) is True
        pb_status    = jget(player, ["playabilityStatus", "status"], "") or ""
        upcoming_evt = jget(
            player, ["playabilityStatus", "liveStreamability", "liveStreamabilityRenderer", "upcomingEventData"], None
        ) is not None
        if is_upcoming or upcoming_evt or pb_status.upper() == "LIVE_STREAM_OFFLINE":
            return (False, title)

        live_now = any([
            jget(player, ["playabilityStatus", "liveStreamability", "liveStreamabilityRenderer", "isLiveNow"], False) is True,
            jget(player, ["microformat", "playerMicroformatRenderer", "liveBroadcastDetails", "isLiveNow"], False) is True,
            jget(player, ["videoDetails", "isLive"], False) is True,
        ])
        if live_now:
            return (True, title)

    s = html.lower()
    negatives = (
        "assistir novamente", "watch again", "estreia", "premiere",
        "melhores momentos", "highlights", "will begin", "vai comeÃ§ar",
        "em breve", "aguardando", "scheduled for", "live_stream_offline",
        '"isupcoming":true', '"isupcoming": true',
    )
    if any(n in s for n in negatives):
        return (False, title)
    # "ao vivo" removido dos positivos â€” aparece tambÃ©m em pÃ¡ginas de lives agendadas
    positives = ('"islivebroadcast":true', '"islivenow":true', 'badge_style_type_live_now', 'live now')
    if any(p in s for p in positives):
        return (True, title)

    return (False, title)

def _extract_live_video_ids_from_html(html: str) -> List[str]:
    """Varre o ytInitialData procurando videoRenderer com badge/overlay LIVE."""
    out: List[str] = []
    if not html:
        return out

    data = extract_json_blob(
        html,
        [
            r"ytInitialData\s*=\s*(\{.*?\})\s*;",
            r'"ytInitialData"\s*:\s*(\{.*?\})\s*,\s*"ytcfg"',
        ],
    )
    if not isinstance(data, dict):
        return _extract_live_video_ids_from_html_loose(html)

    def walk(obj):
        if isinstance(obj, dict):
            if "videoRenderer" in obj:
                vr = obj["videoRenderer"]
                vid = vr.get("videoId")
                if not vid:
                    return
                is_live = False
                for ov in vr.get("thumbnailOverlays", []) or []:
                    tsr = ov.get("thumbnailOverlayTimeStatusRenderer") or {}
                    style = (tsr.get("style") or "").upper()
                    txt_obj = tsr.get("text") or {}
                    txt_simple = (txt_obj.get("simpleText") or "")
                    txt_runs = " ".join([str(r.get("text", "")) for r in (txt_obj.get("runs") or []) if isinstance(r, dict)])
                    txt = f"{txt_simple} {txt_runs}".upper()
                    if ("LIVE" in style) or ("LIVE" in txt) or ("AO VIVO" in txt):
                        is_live = True
                        break
                if not is_live:
                    for b in vr.get("badges", []) or []:
                        br = b.get("metadataBadgeRenderer") or {}
                        label = (br.get("label") or "").upper()
                        style = (br.get("style") or "").upper()
                        if ("LIVE" in label) or ("LIVE" in style) or ("AO VIVO" in label):
                            is_live = True
                            break
                if not is_live:
                    vct = vr.get("viewCountText") or {}
                    t = (vct.get("simpleText") or "").lower()
                    if not t and "runs" in vct:
                        t = " ".join([str(r.get("text", "")).lower() for r in vct["runs"]])
                    if "watching" in t or "assistindo" in t:
                        is_live = True
                if is_live and vid not in out:
                    out.append(vid)
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(data)
    return out

def _extract_live_video_ids_from_html_loose(html: str, limit: int = 40) -> List[str]:
    """Fallback robusto: busca videoId proximo de sinais de live no HTML bruto."""
    out: List[str] = []
    if not html:
        return out
    text = html or ""
    tokens = (
        "islivenow",
        "islive",
        "live_now",
        "live now",
        "badge_style_type_live_now",
        "ao vivo",
        "assistindo",
        "concurrentviewers",
        "concurrent viewers",
    )
    for m in re.finditer(r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"', text):
        vid = m.group(1)
        s = max(0, m.start() - 220)
        e = min(len(text), m.end() + 480)
        win = text[s:e].lower()
        if any(tk in win for tk in tokens):
            if vid not in out:
                out.append(vid)
                if len(out) >= max(1, limit):
                    break
    return out

def _extract_video_ids_from_channel_feed(channel_id: str, limit: int = 30) -> List[str]:
    """LÃª o feed XML do canal e retorna video_ids recentes.
    Fallback para quando pÃ¡ginas /streams e /live_view vierem sem videoId.
    """
    cid = (channel_id or "").strip()
    if not cid:
        return []
    try:
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
        r = SESSION.get(url, timeout=SCRAPE_TIMEOUT)
        r.raise_for_status()
        ids = re.findall(r"<yt:videoId>([A-Za-z0-9_-]{11})</yt:videoId>", r.text or "")
        seen = set()
        out: List[str] = []
        for vid in ids:
            if vid in seen:
                continue
            seen.add(vid)
            out.append(vid)
            if len(out) >= max(1, limit):
                break
        return out
    except Exception as e:
        _log_debug(f"[_extract_video_ids_from_channel_feed] erro: {e}")
        return []

def _has_recent_chat_activity(video_id: str, within_minutes: int = 20, probe_seconds: float = 1.5) -> bool:
    """Fallback sem API: detecta atividade recente no chat para inferir live ativa.
    Evita depender apenas do HTML do watch quando a VM recebe playability inconsistente.
    """
    br_tz = timezone(timedelta(hours=-3))
    now_brt = datetime.now(br_tz)
    chat = None
    try:
        chat = _create_chat(video_id)
        deadline = time.time() + max(1.0, probe_seconds)
        while time.time() < deadline:
            data = chat.get()
            items = getattr(data, "items", []) or []
            for it in items:
                dt_raw = getattr(it, "datetime", None)
                if not isinstance(dt_raw, str):
                    continue
                try:
                    dt = datetime.strptime(dt_raw[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=br_tz)
                except Exception:
                    continue
                age_min = (now_brt - dt).total_seconds() / 60.0
                if -5 <= age_min <= within_minutes:
                    return True
            time.sleep(0.35)
    except Exception:
        return False
    finally:
        try:
            if chat:
                chat.terminate()
        except Exception:
            pass
    return False

def _api_search_live(channel_id: str) -> List[Tuple[str, str]]:
    """Descobre lives ativas via YouTube Data API v3 (search.list).
    Usa cache de API_CACHE_TTL segundos para nÃ£o estourar a quota diÃ¡ria."""
    if not YOUTUBE_API_KEY or not channel_id:
        return []
    now_ts = time.time()
    cached = _api_cache.get(channel_id)
    if cached and (now_ts - cached[0]) < API_CACHE_TTL:
        return cached[1]
    try:
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "channelId": channel_id,
                "eventType": "live",
                "type": "video",
                "maxResults": 10,
                "key": YOUTUBE_API_KEY,
            },
            timeout=10,
        )
        r.raise_for_status()
        results: List[Tuple[str, str]] = []
        for item in r.json().get("items", []):
            vid = item["id"]["videoId"]
            title = item["snippet"]["title"]
            results.append((vid, title))
        _api_cache[channel_id] = (now_ts, results)
        if results:
            _log_debug(f"[_api_search_live] {len(results)} live(s) via API: {[v for v,_ in results]}")
        return results
    except Exception as e:
        _log_debug(f"[_api_search_live] erro: {e}")
        _api_cache[channel_id] = (now_ts, [])
        return []


def list_live_videos_any(handle: str, channel_id: str, max_results: int = LIVE_MAX_RESULTS) -> List[Tuple[str, str]]:
    """EstratÃ©gia combinada para descobrir lives ativas do canal."""

    def uniq(seq):
        seen = set(); out = []
        for x in seq:
            if x in seen: continue
            seen.add(x); out.append(x)
        return out

    def _extract_vid_from_url(u: str) -> Optional[str]:
        if not u: return None
        m = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", u)
        return m.group(1) if m else None

    def _try_live_endpoint(url: str) -> Optional[Tuple[str, str]]:
        try:
            r = SESSION.get(url, params=DEFAULT_PARAMS, timeout=DISCOVERY_TIMEOUT, allow_redirects=False)
            if r is not None and r.is_redirect:
                vid = _extract_vid_from_url(r.headers.get("Location", ""))
                if vid:
                    ok, title = is_live_now(vid)
                    if ok: return (vid, title or oembed_title(vid))
        except Exception as e:
            _log_debug(f"[_try_live_endpoint] no-redirect erro: {e}")
        try:
            r = SESSION.get(url, params=DEFAULT_PARAMS, timeout=DISCOVERY_TIMEOUT, allow_redirects=True)
            if r is not None and r.url:
                vid = _extract_vid_from_url(r.url)
                if vid:
                    ok, title = is_live_now(vid)
                    if ok: return (vid, title or oembed_title(vid))
        except Exception as e:
            _log_debug(f"[_try_live_endpoint] follow-redirect erro: {e}")
        try:
            html = safe_get(url, timeout=DISCOVERY_TIMEOUT, allow_redirects=True)
            if html:
                for vid in _extract_live_video_ids_from_html(html):
                    ok, title = is_live_now(vid)
                    if ok: return (vid, title or oembed_title(vid))
                # YouTube /live parou de redirecionar â€” extrai videoId do canonical link
                for pat in [
                    r'"canonical"[^>]*?watch\?v=([A-Za-z0-9_-]{11})',
                    r'"canonicalBaseUrl"\s*:\s*"/watch\?v=([A-Za-z0-9_-]{11})"',
                ]:
                    m = re.search(pat, html)
                    if m:
                        vid = m.group(1)
                        ok, title = is_live_now(vid)
                        if ok: return (vid, title or oembed_title(vid))
                        break
        except Exception as e:
            _log_debug(f"[_try_live_endpoint] parse erro: {e}")
        return None

    try:
        h   = (handle or "").strip().lstrip("@")
        cid = (channel_id or "").strip()
        if not cid and h:
            cid = resolve_channel_id_by_handle(h)

        # EstratÃ©gia 0: YouTube Data API v3 (confiÃ¡vel, cache 60s)
        api_confirmed: Set[str] = set()
        api_lives: List[Tuple[str, str]] = []
        if cid:
            api_lives = _api_search_live(cid)
            for vid, title in api_lives:
                api_confirmed.add(vid)

        # A) Listagem "sÃ³ lives"
        collected_ids: List[str] = [vid for vid, _ in api_lives]
        chat_fallback_ids: Set[str] = set()
        if h:
            html = safe_get(f"https://www.youtube.com/@{h}/videos?view=2&live_view=501", timeout=DISCOVERY_TIMEOUT)
            if html:
                collected_ids.extend(_extract_live_video_ids_from_html(html))
        if cid and not collected_ids:
            html = safe_get(f"https://www.youtube.com/channel/{cid}/videos?view=2&live_view=501", timeout=DISCOVERY_TIMEOUT)
            if html:
                collected_ids.extend(_extract_live_video_ids_from_html(html))
        collected_ids = uniq(collected_ids)
        chat_fallback_ids.update(collected_ids)

        # B) Fallback: /streams e home
        pages = []
        if h:   pages += [f"https://www.youtube.com/@{h}/streams", f"https://www.youtube.com/@{h}"]
        if cid: pages += [f"https://www.youtube.com/channel/{cid}/streams", f"https://www.youtube.com/channel/{cid}"]
        for url in pages:
            try:
                html = safe_get(url, timeout=DISCOVERY_TIMEOUT)
                if not html: continue
                ids = _extract_live_video_ids_from_html(html)
                if not ids:
                    ids = _extract_live_video_ids_from_html_loose(html, limit=30)
                if ids:
                    for vid in ids:
                        if vid not in collected_ids:
                            collected_ids.append(vid)
                        chat_fallback_ids.add(vid)
                else:
                    # Ultimo recurso: ids genericos (apenas se ainda nao temos candidatos).
                    if not collected_ids:
                        generic_ids = [m.group(1) for m in re.finditer(r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"', html)][:12]
                        for vid in generic_ids:
                            if vid not in collected_ids:
                                collected_ids.append(vid)
            except Exception as e:
                _log_debug(f"[list_live_videos_any] fallback erro: {e}")

        # C) /live (redirect)
        live_urls = []
        if h:   live_urls.append(f"https://www.youtube.com/@{h}/live")
        if cid: live_urls.append(f"https://www.youtube.com/channel/{cid}/live")
        for u in live_urls:
            got = _try_live_endpoint(u)
            if got and got[0] not in collected_ids:
                collected_ids.append(got[0])
            if got:
                chat_fallback_ids.add(got[0])

        # D) Feed XML do canal (fallback robusto para mudancas no HTML)
        if cid:
            feed_ids = _extract_video_ids_from_channel_feed(cid, limit=max(max_results, 15))
            if feed_ids:
                for vid in feed_ids:
                    if vid not in collected_ids:
                        collected_ids.append(vid)

        # Confirma ao vivo e pega tÃ­tulo
        lives_found: List[Tuple[str, str]] = []
        candidates = uniq(collected_ids)[:16]
        chat_fallback_budget = 2
        for idx, vid in enumerate(candidates):
            # API v3 confirmou â€" nÃ£o precisa de is_live_now()
            if vid in api_confirmed:
                title = dict(api_lives).get(vid, oembed_title(vid))
                lives_found.append((vid, title))
                if len(lives_found) >= max_results:
                    break
                continue

            # JÃ¡ tem monitor ativo â€" nÃ£o precisa re-verificar via HTTP
            with state_lock:
                already_active = any(vid in vids for vids in active_videos.values())
            if already_active:
                lives_found.append((vid, oembed_title(vid)))
                if len(lives_found) >= max_results:
                    break
                continue

            ok, title = is_live_now(vid)
            if not ok and vid in chat_fallback_ids and chat_fallback_budget > 0 and idx < 6:
                ttl = (title or oembed_title(vid) or "").lower()
                # SÃ³ usa fallback de chat quando o prÃ³prio tÃ­tulo indica transmissÃ£o ao vivo.
                # Evita reanimar replay/vod com chat replay.
                if "ao vivo" not in ttl and "live" not in ttl:
                    continue
                # Fallback para casos em que watch retorna UNPLAYABLE na VM, mas o chat estÃ¡ ativo.
                if _has_recent_chat_activity(vid):
                    ok = True
                    chat_fallback_budget -= 1
                    _log_debug(f"[list_live_videos_any] fallback chat ativo para {vid}")
            if ok:
                lives_found.append((vid, title or oembed_title(vid)))
            if len(lives_found) >= max_results:
                break

        seen = set(); out = []
        for vid, ttl in lives_found:
            if vid in seen: continue
            seen.add(vid); out.append((vid, ttl))
        return out

    except Exception as e:
        _log_debug(f"[list_live_videos_any] Erro: {e}")
        return []

# â”€â”€â”€ CLASSIFICAÃ‡ÃƒO â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
CLOUD_CONFIDENCE_THRESHOLD = float(os.environ.get("CLOUD_CONFIDENCE_THRESHOLD", "0.70"))

_cloud_session = requests.Session()
_cloud_adapter = requests.adapters.HTTPAdapter(
    max_retries=requests.packages.urllib3.util.retry.Retry(
        total=2, backoff_factor=0.3,
        status_forcelist=[502, 503, 504],
    )
)
_cloud_session.mount("https://", _cloud_adapter)

_KEYWORD_FALLBACK = [
    # (regex, category, issue, severity)
    (re.compile(r"\b(?:sem\s+(?:audio|som|narr))\b", re.I),
                                                                            "AUDIO", "sem_audio",        "high"),
    (re.compile(r"\b(?:audio|som)\s+(?:estouran|estourad|chiand|ruim|ruido|horrivel|pessim|muito\s+alto|alto\s+demais|baixo|baixissim|abafad|cortand)", re.I),
                                                                            "AUDIO", "qualidade_audio",  "medium"),
    (re.compile(r"\b(?:som|audio)\s+(?:ruim|horrivel|pessim)\b", re.I),
                                                                            "AUDIO", "qualidade_audio",  "medium"),
    # Vazamento de audio: outro canal / outro audio entrando na transmissao
    (re.compile(
        r"(?:"
        r"vaz(?:and|ou|amento)\s+(?:de\s+)?(?:audio|som)"
        r"|(?:audio|som)\s+vaz(?:and|ou)"
        r"|entrou\s+(?:outro\s+)?(?:audio|som)"
        r"|(?:audio|som)\s+(?:de\s+outro|errad|trocad)"
        r"|trocou\s+(?:o\s+)?(?:audio|som)"
        r"|(?:outro\s+)?(?:audio|som)\s+(?:entrando|tocando)"
        r"|passando\s+(?:audio|som)\s+(?:de\s+outro|errad)"
        r")",
        re.I),                                                              "AUDIO", "vazamento_audio",  "high"),
    (re.compile(r"\b(?:tela\s+preta|tela\s+escura|sem\s+(?:video|imagem))\b", re.I),
                                                                            "VIDEO", "tela_preta",       "high"),
    (re.compile(r"\b(?:travand|pixelan|imagem\s+ruim|imagem\s+borrad)", re.I),
                                                                            "VIDEO", "qualidade_video",  "medium"),
    # "congelando" so como tecnico se vier junto com contexto de tela/video
    (re.compile(r"(?:tela|imagem|video|transmiss)[^\n]{0,30}congel|congel[^\n]{0,30}(?:tela|imagem|video|transmiss)", re.I),
                                                                            "VIDEO", "qualidade_video",  "medium"),
    (re.compile(r"\b(?:buffering|buffer|live\s+caiu|caiu\s+a\s+live|erro\s+ao\s+abrir)\b", re.I),
                                                                            "REDE",  "conexao",          "high"),
]

def _keyword_override(text: str) -> Optional[dict]:
    """Fallback por regex para casos que o modelo DistilBERT erra."""
    for pattern, cat, issue, sev in _KEYWORD_FALLBACK:
        if pattern.search(text):
            return {"is_technical": True, "category": cat, "issue": issue, "severity": sev}
    return None

# ValidaÃ§Ã£o: pelo menos uma palavra tÃ©cnica precisa estar presente para aceitar positivo do modelo
_TECH_KEYWORDS = re.compile(
    r"(?:"
    r"\b(?:audio|Ã¡udio)\b|\bsom\b|\bnarr|\bmicrofone|\bmic\b"  # Ã¡udio
    r"|\b(?:video|vÃ­deo)\b|\btela\b|\bimagem\b|\bpixel|\bqualidade\b"  # vÃ­deo
    r"|\btravand|\btravan|\bfreez"                               # travamento (congel removido â€” ambÃ­guo com clima)
    r"|\bbuffer|\blag\b|\bping\b|\bcaiu\b|\bcarregan|\bloadin"  # rede
    r"|\bsem\s+(?:som|audio|Ã¡udio|video|vÃ­deo|imagem|sinal)"    # ausÃªncia
    r"|\bcortand|\bestouran|\bestourad|\bchian|\bruÃ­do|\beco\b"  # distorÃ§Ã£o
    r"|\bpreta\b|\bescura\b|\bborrad|\bpixelad"                 # visual
    r"|\bplacar\b|\bgc\b"                                       # GC
    r"|\bmudo|\bmuta|\bdessincroni|\batraso|\badianta|\bdelay"   # sincronia
    r"|\bvazand|\bvazou\b|\bvazamento"                          # vazamento de Ã¡udio
    r")",
    re.I,
)

def _has_tech_keyword(text: str) -> bool:
    """Verifica se o texto contÃ©m pelo menos uma keyword tÃ©cnica."""
    return bool(_TECH_KEYWORDS.search(text))

def cloud_classify(comment: str) -> Optional[dict]:
    """Classifica usando o modelo treinado no Cloud Run."""
    try:
        r = _cloud_session.post(
            f"{SERVING_URL}/classify",
            json={"text": comment.strip()},
            timeout=SERVING_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        is_tech = bool(data.get("is_technical", False))
        confidence = float(data.get("confidence", 1.0))
        # Descarta classificaÃ§Ãµes positivas com baixa confianÃ§a
        if is_tech and confidence < CLOUD_CONFIDENCE_THRESHOLD:
            is_tech = False
        # Rejeita falso positivo genÃ©rico (modelo disse tÃ©cnico mas sem keyword match)
        cat_raw = data.get("category")
        if is_tech and (cat_raw is None or cat_raw == "OUTRO"):
            is_tech = False
        # Guarda contra falso positivo: modelo disse tÃ©cnico mas nenhuma keyword tÃ©cnica presente
        if is_tech and not _has_tech_keyword(comment):
            is_tech = False
        sev = (data.get("severity") or "none").lower()
        if sev not in ("none", "low", "medium", "high"):
            sev = "none"
        if not is_tech:
            sev = "none"
        # Fallback: modelo disse nÃ£o-tÃ©cnico, mas regex detecta problema claro
        if not is_tech:
            override = _keyword_override(comment)
            if override:
                return {**override, "_raw": str(data) + " [keyword_override]"}
        return {
            "is_technical": is_tech,
            "category":     data.get("category") if is_tech else None,
            "issue":        data.get("issue") if is_tech else None,
            "severity":     sev,
            "_raw":         str(data),
        }
    except Exception as e:
        _log_debug(f"cloud_classify error: {e}")
        return None

def classify(comment: str) -> Optional[dict]:
    """Classifica via Cloud Run (DistilBERT fine-tuned)."""
    if len(comment) > MAX_COMMENT_LENGTH:
        return None
    if not SERVING_URL:
        _log_debug("classify: SERVING_URL nÃ£o configurado")
        return None
    return cloud_classify(comment)

# â”€â”€â”€ MONITOR DE CHAT (processo filho) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _sig(author: str, msg: str, ts_iso: Optional[str], mid: Optional[str]) -> str:
    if mid:
        return "id:" + mid
    base = f"{author}|{msg}|{(ts_iso or '')[:19]}"
    return "h:" + hashlib.sha1(base.encode("utf-8", errors="ignore")).hexdigest()

def _create_chat(video_id: str):
    return pytchat.create(video_id=video_id, topchat_only=False, interruptable=False)

def monitor_process_main(channel_display: str, video_id: str, title: str, queue: _stdlib_queue.Queue, stop_event: Event):
    proc_name = f"monitor[{channel_display}:{video_id}]"
    chat = None
    last_item_ts   = time.time()
    last_recreate_ts = 0.0
    msgs_read_in_window = 0
    window_start   = time.time()
    recent         = deque(maxlen=CHAT_DEDUP_WINDOW)
    recent_set     = set()

    def recreate(reason: str):
        nonlocal chat, last_recreate_ts
        try:
            if chat: chat.terminate()
        except Exception:
            pass
        queue.put({"type": "log", "msg": f"[{proc_name}] recriando pytchat: {reason}", "ts": now_iso()})
        try:
            chat = _create_chat(video_id)
            last_recreate_ts = time.time()
        except Exception as e:
            queue.put({"type": "error", "channel": channel_display, "video_id": video_id, "error": f"recreate failed: {e}"})
            chat = None

    try:
        queue.put({"type": "log", "msg": f"[{proc_name}] iniciando: '{title}'", "ts": now_iso()})
        recreate("start")
        queue.put({"type": "heartbeat", "channel": channel_display, "video_id": video_id,
                   "title": title, "url": f"https://www.youtube.com/watch?v={video_id}", "ts": now_iso()})

        while not stop_event.is_set():
            try:
                if chat is None or not chat.is_alive():
                    recreate("chat not alive")
                    time.sleep(0.2)
                    continue

                got_any = False
                for _ in range(CHAT_MAX_DRAIN_CYCLES):
                    try:
                        batch = chat.get()
                    except Exception as e:
                        queue.put({"type": "error", "channel": channel_display, "video_id": video_id,
                                   "error": f"chat.get() falhou: {e}"})
                        break

                    items_list = []
                    try:
                        it = getattr(batch, "items", None)
                        if callable(it): items_list = list(it())
                    except Exception:
                        items_list = []
                    if not items_list:
                        try:
                            it2 = getattr(batch, "sync_items", None)
                            if callable(it2): items_list = list(it2())
                        except Exception:
                            items_list = []
                    if not items_list:
                        break

                    n = 0
                    for c in items_list:
                        if n >= CHAT_MAX_BATCH_PER_DRAIN: break
                        n += 1
                        mid = getattr(c, "id", None) or getattr(c, "message_id", None) or None
                        try:
                            author = c.author.name
                        except Exception:
                            author = getattr(getattr(c, "author", None), "name", None) or "unknown"
                        msg = getattr(c, "message", "")
                        ts_chat = None
                        try:
                            ts_raw = getattr(c, "timestamp", None)
                            if isinstance(ts_raw, (int, float)):
                                ts_chat = datetime.fromtimestamp(
                                    ts_raw / 1000, tz=timezone(timedelta(hours=-3))
                                ).isoformat()
                            else:
                                ts_chat = getattr(c, "datetime", None)
                        except Exception:
                            ts_chat = None

                        sig = _sig(author, msg, ts_chat if isinstance(ts_chat, str) else None, mid)
                        if sig in recent_set:
                            continue
                        # Evicta ANTES do append para pegar o item correto que serÃ¡ removido
                        if len(recent) == recent.maxlen:
                            try:
                                recent_set.discard(recent[0])
                            except Exception:
                                pass
                        recent.append(sig)
                        recent_set.add(sig)

                        queue.put({
                            "type":     "chat",
                            "channel":  channel_display,
                            "video_id": video_id,
                            "author":   author,
                            "message":  msg,
                            "ts":       ts_chat if isinstance(ts_chat, str) else now_iso(),
                        })
                        got_any = True
                        msgs_read_in_window += 1

                nowt = time.time()
                if got_any:
                    last_item_ts = nowt
                    if CHAT_POLL_SLEEP_BETWEEN_DRAINS > 0:
                        time.sleep(CHAT_POLL_SLEEP_BETWEEN_DRAINS)
                else:
                    if nowt - last_item_ts > CHAT_IDLE_WARN_SECONDS:
                        queue.put({"type": "heartbeat", "channel": channel_display, "video_id": video_id, "ts": now_iso()})
                    time.sleep(CHAT_POLL_SLEEP_EMPTY)

                if nowt - window_start >= 5.0:
                    queue.put({"type": "log", "msg": f"[{proc_name}] throughput: {msgs_read_in_window}/5s", "ts": now_iso()})
                    msgs_read_in_window = 0
                    window_start = nowt

                if (nowt - last_item_ts) > CHAT_IDLE_RECREATE_SECONDS and (nowt - last_recreate_ts) > 5.0:
                    live, _ = is_live_now(video_id)
                    if live:
                        recreate("idle_recreate")
                        continue

                if (nowt - last_item_ts) > CHAT_HARD_WATCHDOG_SECONDS:
                    queue.put({"type": "error", "channel": channel_display, "video_id": video_id,
                               "error": "hard watchdog: sem msgs"})
                    break

            except Exception as e:
                queue.put({"type": "error", "channel": channel_display, "video_id": video_id,
                           "error": f"loop error: {e}"})
                time.sleep(0.05)

        queue.put({"type": "closed", "channel": channel_display, "video_id": video_id, "ts": now_iso()})

    except Exception:
        queue.put({"type": "error", "channel": channel_display, "video_id": video_id,
                   "error": traceback.format_exc()})
    finally:
        try:
            if chat: chat.terminate()
        except Exception:
            pass
        queue.put({"type": "log", "msg": f"[{proc_name}] encerrado", "ts": now_iso()})

# â”€â”€â”€ LIMPEZA DE EMOJIS CUSTOM DO YOUTUBE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_YT_EMOJI_RE = re.compile(r":[^:\s]{1,50}:")

def _clean_yt_emojis(text: str) -> str:
    """Remove emoji codes custom do YouTube (:nome:) da mensagem.
    Emojis Unicode normais (ðŸ˜‚â¤ï¸ðŸ”¥) passam intactos."""
    return _YT_EMOJI_RE.sub("", text).strip()

# â”€â”€â”€ PRÃ‰-FILTRO RÃPIDO (descarta mensagens Ã³bvias sem chamar IA) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_PREFILTER_SKIP = re.compile(
    r"^[\U0001F600-\U0001FAFF\U00002702-\U000027B0\sâ¤ï¸ðŸ”¥ðŸ‘ðŸ˜‚ðŸ¤£ðŸ’€ðŸ˜ðŸ¥°ðŸ˜­ðŸ˜ŽðŸ‘ðŸ‡§ðŸ‡·]+$"  # sÃ³ emojis
    r"|^.{0,2}$"                                                                        # < 3 chars
    r"|^(?:boa\s+(?:noite|tarde)|bom\s+dia|oi+|ola|hello|hi)\b"                        # saudaÃ§Ãµes
    r"|^(?:goo*l+|golaÃ§o|que\s+golaÃ§o)\b"                                               # torcida
    r"|^(?:vai\s+\w+|vamo|bora)\b"                                                      # torcida
    r"|^(?:kkk+|haha+|rsrs+|lol+)\s*$"                                                  # risadas
, re.I | re.UNICODE)

def _should_skip_classify(text: str) -> bool:
    """Retorna True se o texto Ã© obviamente nÃ£o-tÃ©cnico e pode pular a IA."""
    return bool(_PREFILTER_SKIP.search(text.strip()))

# â”€â”€â”€ QUEUE CONSUMER (batch GPU) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#
# Arquitetura para alto volume (atÃ© 500 msg/s):
#
#   pytchat â†’ multiprocessing.Queue â†’ consumer_loop
#                  â†“ (enqueue imediato, O(1))
#             _batch_queue (stdlib thread-safe)
#                  â†“ (drena a cada BATCH_MAX_WAIT s ou BATCH_SIZE itens)
#             _batcher_loop â†’ POST /classify/batch (GPU, atÃ© 64 textos/req)
#                  â†“ (resultados em batch)
#             _process_batch â†’ Firestore WriteBatch (reduz RPCs)
#
# Contadores do live doc (total_comments, technical_comments, issue_counts)
# sÃ£o acumulados em memÃ³ria e gravados no Firestore a cada FS_FLUSH_SECS,
# evitando o problema de "hot document" a 500 writes/s.
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_batch_queue    = _stdlib_queue.Queue(maxsize=200_000)   # inicializado aqui â€” nunca None
_counter_lock   = Lock()
_pending_counts: dict = {}   # vid â†’ {total, technical, issue_counts}

# â”€â”€â”€ AUDIÃŠNCIA / GPU POR LIVE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_gpu_lives:     Set[str] = set()   # video_ids com GPU ativo
_viewer_counts: Dict[str, int] = {}
_viewer_lock    = Lock()


def _fetch_concurrent_viewers(video_ids: List[str]) -> Dict[str, int]:
    """Consulta YouTube Data API v3 â€” retorna concurrent_viewers por video_id."""
    if not YOUTUBE_API_KEY or not video_ids:
        return {}
    try:
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={
                "part":   "liveStreamingDetails",
                "id":     ",".join(video_ids),
                "key":    YOUTUBE_API_KEY,
                "fields": "items(id,liveStreamingDetails(concurrentViewers))",
            },
            timeout=10,
        )
        r.raise_for_status()
        result: Dict[str, int] = {}
        for item in r.json().get("items", []):
            vid = item.get("id", "")
            raw = item.get("liveStreamingDetails", {}).get("concurrentViewers", "0")
            try:
                result[vid] = int(raw)
            except (ValueError, TypeError):
                result[vid] = 0
        return result
    except Exception as e:
        _log_debug(f"[viewership] erro: {e}")
        return {}


def _viewership_poll_loop():
    """Thread daemon: a cada VIEWER_POLL_SECS busca audiÃªncia e decide GPU por live."""
    while True:
        time.sleep(VIEWER_POLL_SECS)
        try:
            with state_lock:
                all_vids = [vid for vids in active_videos.values() for vid in vids]
            # Fallback: inclui tambÃ©m docs status=active do Firestore.
            # Evita perder audiÃªncia quando a descoberta oscila.
            fs = _get_fs()
            if fs:
                try:
                    for d in fs.collection("lives").where("status", "==", "active").stream():
                        all_vids.append(d.id)
                except Exception as e:
                    _log_debug(f"[viewership] active docs fallback: {e}")
            all_vids = list(dict.fromkeys(all_vids))
            if not all_vids:
                continue

            viewers_map = _fetch_concurrent_viewers(all_vids)
            viewers_full = {vid: int(viewers_map.get(vid, 0)) for vid in all_vids}

            with _viewer_lock:
                _viewer_counts.update(viewers_full)
                for vid, viewers in viewers_full.items():
                    if viewers >= GPU_VIEWER_THRESHOLD:
                        if vid not in _gpu_lives:
                            _log_debug(f"[GPU] {vid}: {viewers:,} viewers â‰¥ {GPU_VIEWER_THRESHOLD:,} â€” GPU ON")
                            _gpu_lives.add(vid)
                    else:
                        if vid in _gpu_lives:
                            _log_debug(f"[GPU] {vid}: {viewers:,} viewers < {GPU_VIEWER_THRESHOLD:,} â€” GPU OFF")
                        _gpu_lives.discard(vid)

            # Salva no Firestore para o dashboard exibir
            if fs:
                for vid, viewers in viewers_full.items():
                    try:
                        fs.collection("lives").document(vid).update({
                            "concurrent_viewers": viewers,
                            "gpu_active":         vid in _gpu_lives,
                        })
                    except Exception as e:
                        _log_debug(f"[viewership] Firestore {vid}: {e}")

            active_str = ", ".join(f"{v}({viewers_full.get(v,0):,})" for v in _gpu_lives) or "nenhuma"
            _log_debug(f"[viewership] lives com GPU: {active_str}")

        except Exception as e:
            _log_debug(f"[viewership_poll] {e}")


def _accum_counter(vid: str, is_tech: bool, category, issue):
    """Acumula contadores em memÃ³ria â€” flush periÃ³dico via _counter_flush_loop."""
    with _counter_lock:
        c = _pending_counts.setdefault(vid, {"total": 0, "technical": 0, "issue_counts": {}})
        c["total"] += 1
        if is_tech:
            c["technical"] += 1
            if category and issue:
                key = f"{category}:{issue}"
                c["issue_counts"][key] = c["issue_counts"].get(key, 0) + 1


def _flush_pending_counts():
    """Grava contadores acumulados no Firestore (1 update por live em vez de 500/s)."""
    global _pending_counts
    with _counter_lock:
        snapshot, _pending_counts = _pending_counts, {}
    failed: dict = {}
    for vid, c in snapshot.items():
        try:
            fs = _get_fs()
            if not fs:
                failed[vid] = c
                continue
            upd: dict = {
                "total_comments":     fb_firestore.Increment(c["total"]),
                "technical_comments": fb_firestore.Increment(c["technical"]),
                "last_seen_at":       now_iso(),
            }
            # Usa nested dict (nÃ£o dot-notation) para issue_counts:
            # evita erro "Invalid char" quando a categoria tem '/' (ex: REDE/PLATAFORMA)
            if c["issue_counts"]:
                upd["issue_counts"] = {
                    key: fb_firestore.Increment(n)
                    for key, n in c["issue_counts"].items()
                }
            fs.collection("lives").document(vid).update(upd)
        except Exception as e:
            _log_debug(f"[counter_flush] {vid}: {e}")
            failed[vid] = c  # re-enfileira para prÃ³ximo ciclo
    if failed:
        with _counter_lock:
            for vid, c in failed.items():
                ex = _pending_counts.setdefault(vid, {"total": 0, "technical": 0, "issue_counts": {}})
                ex["total"]     += c["total"]
                ex["technical"] += c["technical"]
                for k, n in c["issue_counts"].items():
                    ex["issue_counts"][k] = ex["issue_counts"].get(k, 0) + n


def _counter_flush_loop():
    """Thread daemon: flush periÃ³dico de contadores."""
    while True:
        time.sleep(FS_FLUSH_SECS)
        try:
            _flush_pending_counts()
        except Exception as e:
            _log_debug(f"[counter_flush_loop] {e}")


def _process_batch(items: list):
    """Classifica em batch via Cloud Run GPU e salva tudo via Firestore WriteBatch."""
    if not items:
        return

    # Itens que precisam de IA vs prÃ©-filtrados
    ai_items  = [it for it in items if it["needs_ai"]]
    ai_texts  = [it["text"] for it in ai_items]

    # Chama /classify/batch â€” 1 request para N textos (GPU)
    raw_results: list = []
    if ai_texts and SERVING_URL:
        try:
            r = _cloud_session.post(
                f"{SERVING_URL}/classify/batch",
                json={"texts": ai_texts},
                timeout=SERVING_TIMEOUT,
            )
            r.raise_for_status()
            raw_results = r.json()
        except Exception as e:
            _log_debug(f"[batch_classify] erro: {e}")

    # Mapeia result por comment_id
    ai_result_map: dict = {}
    for i, it in enumerate(ai_items):
        ai_result_map[it["comment_id"]] = raw_results[i] if i < len(raw_results) else None

    # Firestore WriteBatch â€” salva comment docs + minutes de uma vez
    fs = _get_fs()
    if not fs:
        return

    batch = fs.batch()
    batch_ops = 0

    def _maybe_commit():
        nonlocal batch, batch_ops
        if batch_ops >= 400:   # limite do WriteBatch Ã© 500; margem de seguranÃ§a
            try:
                batch.commit()
            except Exception as e:
                _log_debug(f"[batch_commit] erro: {e}")
            batch = fs.batch()
            batch_ops = 0

    for it in items:
        res = ai_result_map.get(it["comment_id"]) if it["needs_ai"] else None
        is_tech = False
        category, issue, severity = None, None, "none"

        if res:
            is_tech    = bool(res.get("is_technical", False))
            confidence = float(res.get("confidence", 1.0))
            cat_raw    = res.get("category")
            if is_tech and confidence < CLOUD_CONFIDENCE_THRESHOLD:
                is_tech = False
            if is_tech and (cat_raw is None or cat_raw == "OUTRO"):
                is_tech = False
            if is_tech and not _has_tech_keyword(it["text"]):
                is_tech = False
            if is_tech:
                category = cat_raw
                issue    = res.get("issue")
                sev_raw  = (res.get("severity") or "none").lower()
                severity = sev_raw if sev_raw in ("none", "low", "medium", "high") else "none"
            if not is_tech:
                override = _keyword_override(it["text"])
                if override:
                    is_tech  = True
                    category = override["category"]
                    issue    = override["issue"]
                    severity = override["severity"]

        _accum_counter(it["vid"], is_tech, category, issue)

        live_ref = fs.collection("lives").document(it["vid"])

        # Grava comentÃ¡rio
        batch.set(
            live_ref.collection("comments").document(it["comment_id"]),
            {
                "author":       it["author"],
                "text":         it["text"],
                "ts":           it["ts"],
                "is_technical": is_tech,
                "category":     category if is_tech else None,
                "issue":        issue    if is_tech else None,
                "severity":     severity if is_tech else "none",
            }
        )
        batch_ops += 1
        _maybe_commit()

        # Agrega minuto
        ts_val    = it["ts"]
        time_part = ts_val.split("T")[-1] if "T" in ts_val else ts_val.split(" ")[-1] if " " in ts_val else ts_val
        minute_key = time_part[:5]
        if minute_key and len(minute_key) == 5 and ":" in minute_key:
            batch.set(
                live_ref.collection("minutes").document(minute_key),
                {
                    "total":     fb_firestore.Increment(1),
                    "technical": fb_firestore.Increment(1 if is_tech else 0),
                },
                merge=True,
            )
            batch_ops += 1
            _maybe_commit()

    if batch_ops > 0:
        try:
            batch.commit()
        except Exception as e:
            _log_debug(f"[batch_commit_final] erro: {e}")


def _batcher_loop():
    """Thread daemon: drena _batch_queue e processa em micro-batches."""
    pending: list = []
    last_send = time.time()

    while True:
        # Coleta atÃ© BATCH_SIZE itens ou atÃ© BATCH_MAX_WAIT segundos
        deadline = last_send + BATCH_MAX_WAIT
        while len(pending) < BATCH_SIZE:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                item = _batch_queue.get(timeout=min(remaining, 0.02))
                pending.append(item)
            except _stdlib_queue.Empty:
                if time.time() >= deadline:
                    break

        if pending:
            to_send = pending[:BATCH_SIZE]
            pending = pending[BATCH_SIZE:]
            t = Thread(target=_process_batch, args=(to_send,), daemon=True)
            t.start()
            t.join(timeout=SERVING_TIMEOUT + 30)
            if t.is_alive():
                _log_debug(f"[batcher] AVISO: _process_batch travado â€” batch de {len(to_send)} perdido")

        last_send = time.time()


def _process_chat_item(vid: str, author: str, text: str, ts: str):
    """Limpa, prÃ©-filtra e enfileira no batcher (O(1), nÃ£o bloqueia o consumer)."""
    _last_chat_msg_ts[vid] = time.time()
    try:
        text = _clean_yt_emojis(text)
        if not text:
            return

        comment_id = hashlib.sha1(
            f"{author}{ts}{text}".encode("utf-8", errors="ignore")
        ).hexdigest()[:16]

        needs_ai = not _should_skip_classify(text)

        try:
            _batch_queue.put_nowait({
                "vid":        vid,
                "comment_id": comment_id,
                "author":     author,
                "text":       text,
                "ts":         ts,
                "needs_ai":   needs_ai,
            })
        except _stdlib_queue.Full:
            _log_debug(f"[batcher] fila cheia â€” descartando msg de {vid}")

    except Exception:
        _log_debug(f"[_process_chat_item] error: {traceback.format_exc()}")


def queue_consumer_loop(q: _stdlib_queue.Queue):
    Thread(target=_batcher_loop,        daemon=True, name="batcher").start()
    Thread(target=_counter_flush_loop,  daemon=True, name="counter_flush").start()
    Thread(target=_viewership_poll_loop, daemon=True, name="viewership_poll").start()
    _log_debug(f"[consumer] batch_size={BATCH_SIZE} max_wait={BATCH_MAX_WAIT}s flush={FS_FLUSH_SECS}s gpu_threshold={GPU_VIEWER_THRESHOLD:,}")

    while True:
        try:
            item = q.get(timeout=QUEUE_POLL_SECONDS)
        except Exception:
            continue

        try:
            t = item.get("type")

            if t == "log":
                print(item.get("msg"))

            elif t == "error":
                _log_debug(f"[ERRO] {item.get('channel')} {item.get('video_id')} {item.get('error')}")

            elif t == "heartbeat":
                vid   = item["video_id"]
                ch    = item["channel"]
                url   = item.get("url", f"https://www.youtube.com/watch?v={vid}")
                fs_touch_live(vid, ch, url)

            elif t == "chat":
                vid    = item["video_id"]
                author = item.get("author", "-")
                text   = item.get("message", "")
                ts     = item.get("ts", now_iso())
                _process_chat_item(vid, author, text, ts)

            elif t == "ended":
                fs_mark_live_ended(item["video_id"])

        except Exception:
            _log_debug(f"queue_consumer error: {traceback.format_exc()}")

# â”€â”€â”€ SUPERVISOR â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _load_active_from_firestore(channel_display: str):
    """Na inicializaÃ§Ã£o, popula active_videos com lives status=active do Firestore.
    Assim o miss-tolerance encerra lives de sessÃµes anteriores na 1Âª varredura."""
    if not FIRESTORE_ENABLED:
        return
    try:
        fs = _get_fs()
        if not fs:
            return
        docs = fs.collection("lives").where("status", "==", "active").stream()
        loaded = []
        with state_lock:
            for d in docs:
                data = d.to_dict() or {}
                if data.get("channel") == channel_display:
                    active_videos[channel_display].add(d.id)
                    loaded.append(d.id)
        if loaded:
            _log_debug(f"[{channel_display}] {len(loaded)} live(s) ativa(s) carregada(s) do Firestore: {loaded}")
    except Exception as e:
        _log_debug(f"[_load_active_from_firestore] erro: {e}")

def channel_supervisor_loop(channel_display: str, name: str, handle: str,
                            preset_channel_id: str, queue: _stdlib_queue.Queue):
    _log_debug(f"[{channel_display}] supervisor iniciado")
    channel_id = (preset_channel_id.strip() if preset_channel_id else "") or ""
    if not channel_id and handle:
        cid = resolve_channel_id_by_handle(handle)
        if cid:
            channel_id = cid

    video_misses: Dict[str, int] = {}
    with state_lock:
        active_videos[channel_display] = set()

    # Carrega lives ativas do Firestore para retomar o miss-tolerance
    _load_active_from_firestore(channel_display)

    while True:
        try:
            t0    = time.time()
            lives = list_live_videos_any(handle, channel_id, max_results=LIVE_MAX_RESULTS)
            dt    = time.time() - t0
            _log_debug(f"[{channel_display}] varredura em {dt:.1f}s â€” {len(lives)} live(s)")

            current_ids: Set[str] = set()
            for vid, title in lives:
                current_ids.add(vid)
                if not title or title == vid:
                    title = oembed_title(vid)

                with state_lock:
                    active_videos[channel_display].add(vid)
                    video_misses[vid] = 0

                fs_upsert_live(vid, channel_display, title or vid,
                               f"https://www.youtube.com/watch?v={vid}")

                key  = (channel_display, vid)
                thr  = running_monitors.get(key)
                nowt = time.time()
                if not thr or not thr.is_alive():
                    last_attempt = last_start_attempt.get(key, 0)
                    if nowt - last_attempt > CHAT_RETRY_SECONDS:
                        _log_debug(f"[{channel_display}] iniciando monitor {vid} ({title})")
                        ev = Event()
                        t = Thread(
                            target=monitor_process_main,
                            args=(channel_display, vid, title, queue, ev),
                            daemon=True,
                            name=f"monitor[{channel_display}:{vid}]",
                        )
                        t.start()
                        running_monitors[key] = t
                        _stop_events[key] = ev
                        last_start_attempt[key] = nowt

            # Miss tolerance â€” encerra monitores de lives que sumiram
            with state_lock:
                known = set(active_videos.get(channel_display, set()))
                for vid in known:
                    if vid not in current_ids:
                        # Chat-aware: se recebeu msg recentemente, live estÃ¡ ativa
                        last_msg = _last_chat_msg_ts.get(vid, 0)
                        if time.time() - last_msg < CHAT_ALIVE_GRACE:
                            video_misses[vid] = 0
                            _log_debug(f"[{channel_display}] {vid} miss ignorado - chat ativo")
                            continue
                        video_misses[vid] = video_misses.get(vid, 0) + 1
                to_remove = [vid for vid in known if video_misses.get(vid, 0) >= MISS_TOLERANCE]
                for vid in to_remove:
                    active_videos[channel_display].discard(vid)
                    video_misses.pop(vid, None)
                    # Marca encerrada direto no supervisor para nÃ£o depender apenas da fila.
                    fs_mark_live_ended(vid)
                    queue.put({"type": "ended", "channel": channel_display, "video_id": vid})
                    stop_monitor(channel_display, vid)
                    _log_debug(f"[{channel_display}] live encerrada: {vid}")

            time.sleep(SUPERVISOR_POLL_SECONDS)

        except Exception as e:
            _log_debug(f"[{channel_display}] Erro supervisor: {e}")
            traceback.print_exc()
            time.sleep(10)

# â”€â”€â”€ BOOTSTRAP â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
q: _stdlib_queue.Queue = _stdlib_queue.Queue()

def queue_consumer_bootstrap():
    # Um Ãºnico dispatcher thread + ThreadPoolExecutor interno com LLM_WORKERS
    Thread(target=queue_consumer_loop, args=(q,), daemon=True).start()

def supervisors_bootstrap():
    for ch in CHANNELS:
        Thread(
            target=channel_supervisor_loop,
            args=(ch["display"], ch["name"], ch.get("handle", ""), ch.get("channel_id", ""), q),
            daemon=True,
        ).start()

def _graceful_shutdown(signum, frame):
    print(f"\nRecebido sinal {signum}, encerrando monitores...")
    with state_lock:
        items = list(running_monitors.items())
    for key, thr in items:
        try:
            ev = _stop_events.get(key)
            if ev:
                ev.set()
        except Exception:
            pass
    for key, thr in items:
        try:
            thr.join(timeout=3)
        except Exception:
            pass
    running_monitors.clear()
    _stop_events.clear()
    raise SystemExit(0)

# â”€â”€â”€ MAIN â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if __name__ == "__main__":
    signal.signal(signal.SIGINT,  _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)

    print("=" * 60)
    print("  Monitor de Lives â€” CazÃ©TV")
    print(f"  Cloud Run : {SERVING_URL or 'NAO CONFIGURADO â€” defina SERVING_URL'}")
    print(f"  Firestore : {'ativo' if FIRESTORE_ENABLED else 'desativado'}")
    print("=" * 60)
    for ch in CHANNELS:
        print(f"  Canal: {ch['display']} ({ch.get('handle', '')})")
    print("=" * 60)

    queue_consumer_bootstrap()
    supervisors_bootstrap()

    # MantÃ©m o processo principal vivo
    while True:
        time.sleep(1)

