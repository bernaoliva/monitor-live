# -*- coding: utf-8 -*-
"""
Monitor de Lives YouTube — CazéTV
Coleta chat → classifica via Cloud Run (DistilBERT) → grava no Firestore
Dashboard: Vercel (Next.js)
"""

import os
import re
import json
import time
import traceback
import functools
import hashlib
import signal
import requests
import multiprocessing as mp
import queue as _stdlib_queue
from multiprocessing import Process, Queue
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Optional, Set
from collections import deque

# Firestore — ativa se FIREBASE_CREDENTIALS estiver definido
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

# ─── CONSTANTS ───────────────────────────────────────────────────────────────
MAX_COMMENT_LENGTH = 5000
OEMBED_CACHE_TTL   = 300

# ─── CONFIG ──────────────────────────────────────────────────────────────────
CHANNELS = [
    {"display": "CAZETV", "name": "CazéTV", "handle": "@CazeTV", "channel_id": ""},
]

SUPERVISOR_POLL_SECONDS        = 15
CHAT_RETRY_SECONDS             = 10
QUEUE_POLL_SECONDS             = 0.5
LIVE_MAX_RESULTS               = 20
MISS_TOLERANCE                 = 1

WATCH_VERIFY_TIMEOUT           = 10
SCRAPE_TIMEOUT                 = 15

CHAT_MAX_DRAIN_CYCLES          = 64
CHAT_MAX_BATCH_PER_DRAIN       = 500
CHAT_POLL_SLEEP_EMPTY          = 0.03
CHAT_POLL_SLEEP_BETWEEN_DRAINS = 0.0
CHAT_IDLE_WARN_SECONDS         = 8
CHAT_IDLE_RECREATE_SECONDS     = 20
CHAT_HARD_WATCHDOG_SECONDS     = 45
CHAT_DEDUP_WINDOW              = 5000

# IA — Cloud Run (DistilBERT fine-tuned)
SERVING_URL     = os.environ.get("SERVING_URL", "SUA_URL_CLOUD_RUN")
SERVING_TIMEOUT = int(os.environ.get("SERVING_TIMEOUT", "15"))
LLM_WORKERS     = max(1, int(os.environ.get("LLM_WORKERS", "4")))

# Batch de classificação — GPU processa até 64 textos por chamada
BATCH_SIZE     = int(os.environ.get("BATCH_SIZE",   "64"))   # textos por request ao Cloud Run
BATCH_MAX_WAIT = float(os.environ.get("BATCH_MAX_WAIT", "0.1"))  # s — tempo máx para montar batch
FS_FLUSH_SECS  = float(os.environ.get("FS_FLUSH_SECS",  "3.0"))  # s — flush contadores live doc

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

# ─── LOGGING ─────────────────────────────────────────────────────────────────
os.makedirs("debug_logs", exist_ok=True)

def _log_debug(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{ts}] {msg}"
    print(log_msg)
    with open(os.path.join("debug_logs", f"debug_{datetime.now().strftime('%Y%m%d')}.log"), "a", encoding="utf-8") as f:
        f.write(log_msg + "\n")

# ─── FIRESTORE ───────────────────────────────────────────────────────────────
def fs_upsert_live(video_id: str, channel: str, title: str, url: str, status: str = "active"):
    if not FIRESTORE_ENABLED: return
    try:
        fs = _get_fs()
        if not fs: return
        fs.collection("lives").document(video_id).set({
            "channel":      channel,
            "title":        title,
            "url":          url,
            "status":       status,
            "last_seen_at": now_iso(),
        }, merge=True)
    except Exception as e:
        _log_debug(f"[Firestore] fs_upsert_live error: {e}")

def fs_add_comment(video_id: str, comment_id: str, author: str, text: str,
                   ts: str, is_technical: bool, category, issue, severity: str):
    if not FIRESTORE_ENABLED: return
    try:
        fs = _get_fs()
        if not fs: return
        live_ref = fs.collection("lives").document(video_id)
        # Salva todos os comentários (técnicos e normais) para o feed completo
        live_ref.collection("comments").document(comment_id).set({
            "author":       author,
            "text":         text,
            "ts":           ts,
            "is_technical": is_technical,
            "category":     category if is_technical else None,
            "issue":        issue    if is_technical else None,
            "severity":     severity if is_technical else "none",
        })
        # Incrementa contadores para todos os comentários
        live_ref.update({
            "total_comments":     fb_firestore.Increment(1),
            "technical_comments": fb_firestore.Increment(1 if is_technical else 0),
            **({"issue_counts": {f"{category}:{issue}": fb_firestore.Increment(1)}}
               if is_technical and category and issue else {}),
        })
        # Agrega por minuto para o gráfico (evita o browser baixar todos os comentários)
        try:
            # Extrai HH:mm de qualquer formato: ISO (2026-02-19T18:57:29) ou espaço (2026-02-19 18:57:29)
            time_part = ts.split("T")[-1] if "T" in ts else ts.split(" ")[-1] if " " in ts else ts
            minute_key = time_part[:5]  # HH:mm
            if minute_key and len(minute_key) == 5:
                live_ref.collection("minutes").document(minute_key).set({
                    "total":     fb_firestore.Increment(1),
                    "technical": fb_firestore.Increment(1 if is_technical else 0),
                }, merge=True)
        except Exception:
            pass  # não falha se agregar der erro
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

# ─── ESTADO (apenas controle de processos) ───────────────────────────────────
running_monitors:    Dict[Tuple[str, str], Process] = {}
last_start_attempt:  Dict[Tuple[str, str], float]   = {}
active_videos:       Dict[str, Set[str]]             = {}  # channel_display → video_ids ativos
state_lock = Lock()

def stop_monitor(channel_display: str, video_id: str):
    """Encerra o processo de chat daquela live e remove do dict."""
    key = (channel_display, video_id)
    proc = running_monitors.get(key)
    if proc and proc.is_alive():
        try:
            proc.terminate()
        except Exception:
            pass
    running_monitors.pop(key, None)

# ─── UTILS ───────────────────────────────────────────────────────────────────
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

@functools.lru_cache(maxsize=64)
def oembed_title(video_id: str) -> str:
    try:
        o = SESSION.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=6,
        )
        if o.status_code == 200:
            return o.json().get("title", video_id)
    except Exception:
        pass
    return video_id

# ─── LIVE DISCOVERY ──────────────────────────────────────────────────────────
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
    _log_debug(f"[resolve_channel_id_by_handle] não achou UC para @{h} — tentativas: {tried}")
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
    """Verifica se um video_id está AO VIVO. Retorna (bool_is_live, title)."""
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

        # Descarta de imediato qualquer live ainda não iniciada
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
        "melhores momentos", "highlights", "will begin", "vai começar",
        "em breve", "aguardando", "scheduled for", "live_stream_offline",
        '"isupcoming":true', '"isupcoming": true',
    )
    if any(n in s for n in negatives):
        return (False, title)
    # "ao vivo" removido dos positivos — aparece também em páginas de lives agendadas
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
        for m in re.finditer(r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"', html):
            vid = m.group(1)
            if vid not in out:
                out.append(vid)
        return out

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
                    if (tsr.get("style") or "").upper() == "LIVE" or (tsr.get("text") or {}).get("simpleText") == "LIVE":
                        is_live = True
                        break
                if not is_live:
                    for b in vr.get("badges", []) or []:
                        br = b.get("metadataBadgeRenderer") or {}
                        if "LIVE" in (br.get("label") or "").upper():
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

def list_live_videos_any(handle: str, channel_id: str, max_results: int = LIVE_MAX_RESULTS) -> List[Tuple[str, str]]:
    """Estratégia combinada para descobrir lives ativas do canal."""

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
            r = SESSION.get(url, params=DEFAULT_PARAMS, timeout=SCRAPE_TIMEOUT, allow_redirects=False)
            if r is not None and r.is_redirect:
                vid = _extract_vid_from_url(r.headers.get("Location", ""))
                if vid:
                    ok, title = is_live_now(vid)
                    if ok: return (vid, title or oembed_title(vid))
        except Exception as e:
            _log_debug(f"[_try_live_endpoint] no-redirect erro: {e}")
        try:
            r = SESSION.get(url, params=DEFAULT_PARAMS, timeout=SCRAPE_TIMEOUT, allow_redirects=True)
            if r is not None and r.url:
                vid = _extract_vid_from_url(r.url)
                if vid:
                    ok, title = is_live_now(vid)
                    if ok: return (vid, title or oembed_title(vid))
        except Exception as e:
            _log_debug(f"[_try_live_endpoint] follow-redirect erro: {e}")
        try:
            html = safe_get(url, timeout=SCRAPE_TIMEOUT, allow_redirects=True)
            if html:
                for vid in _extract_live_video_ids_from_html(html):
                    ok, title = is_live_now(vid)
                    if ok: return (vid, title or oembed_title(vid))
                # YouTube /live parou de redirecionar — extrai videoId do canonical link
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

        # A) Listagem "só lives"
        collected_ids: List[str] = []
        if h:
            html = safe_get(f"https://www.youtube.com/@{h}/videos?view=2&live_view=501", timeout=SCRAPE_TIMEOUT)
            if html:
                collected_ids.extend(_extract_live_video_ids_from_html(html))
        if cid and not collected_ids:
            html = safe_get(f"https://www.youtube.com/channel/{cid}/videos?view=2&live_view=501", timeout=SCRAPE_TIMEOUT)
            if html:
                collected_ids.extend(_extract_live_video_ids_from_html(html))
        collected_ids = uniq(collected_ids)

        # B) Fallback: /streams e home
        pages = []
        if h:   pages += [f"https://www.youtube.com/@{h}/streams", f"https://www.youtube.com/@{h}"]
        if cid: pages += [f"https://www.youtube.com/channel/{cid}/streams", f"https://www.youtube.com/channel/{cid}"]
        for url in pages:
            try:
                html = safe_get(url, timeout=SCRAPE_TIMEOUT)
                if not html: continue
                ids = _extract_live_video_ids_from_html(html)
                if not ids:
                    ids = [m.group(1) for m in re.finditer(r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"', html)]
                for vid in ids:
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

        # Confirma ao vivo e pega título
        lives_found: List[Tuple[str, str]] = []
        for vid in collected_ids[:max_results]:
            ok, title = is_live_now(vid)
            if ok:
                lives_found.append((vid, title or oembed_title(vid)))

        seen = set(); out = []
        for vid, ttl in lives_found:
            if vid in seen: continue
            seen.add(vid); out.append((vid, ttl))
        return out

    except Exception as e:
        _log_debug(f"[list_live_videos_any] Erro: {e}")
        return []

# ─── CLASSIFICAÇÃO ───────────────────────────────────────────────────────────
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
    (re.compile(r"\b(?:sem\s+(?:audio|áudio|som|narr))\b", re.I),         "AUDIO", "sem_audio",        "high"),
    (re.compile(r"\b(?:audio|áudio|som)\s+(?:estouran|estourad|chiand|ruim|ruído|horrivel|horrível|péssim|pessim|muito\s+alto|alto\s+demais|baixo|baixíssim|abafad|cortand)", re.I),
                                                                            "AUDIO", "qualidade_audio",  "medium"),
    (re.compile(r"\b(?:som|audio|áudio)\s+(?:ruim|horrivel|horrível|péssim|pessim)\b", re.I),
                                                                            "AUDIO", "qualidade_audio",  "medium"),
    # Vazamento de áudio: outro canal / outro áudio entrando na transmissão
    (re.compile(
        r"(?:"
        r"vaz(?:and|ou|amento)\s+(?:de\s+)?(?:audio|áudio|som)"   # vazando/vazou/vazamento de áudio
        r"|(?:audio|áudio|som)\s+vaz(?:and|ou)"                    # áudio vazando/vazou
        r"|entrou\s+(?:outro\s+)?(?:audio|áudio|som)"              # entrou outro áudio
        r"|(?:audio|áudio|som)\s+(?:de\s+outro|errad|trocad)"      # áudio de outro/errado/trocado
        r"|trocou\s+(?:o\s+)?(?:audio|áudio|som)"                  # trocou o áudio
        r"|(?:outro\s+)?(?:audio|áudio|som)\s+(?:entrando|tocando)"# outro áudio entrando/tocando
        r"|passando\s+(?:audio|áudio|som)\s+(?:de\s+outro|errad)"  # passando áudio de outro
        r")",
        re.I),                                                              "AUDIO", "vazamento_audio",  "high"),
    (re.compile(r"\b(?:tela\s+preta|tela\s+escura|sem\s+(?:video|vídeo|imagem))\b", re.I),
                                                                            "VIDEO", "tela_preta",       "high"),
    (re.compile(r"\b(?:travand|pixelan|imagem\s+ruim|imagem\s+borrad)", re.I),
                                                                            "VIDEO", "qualidade_video",  "medium"),
    # "congelando" só como técnico se vier junto com contexto de tela/vídeo
    (re.compile(r"(?:tela|imagem|video|vídeo|transmiss)[^\n]{0,30}congel|congel[^\n]{0,30}(?:tela|imagem|video|vídeo|transmiss)", re.I),
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

# Validação: pelo menos uma palavra técnica precisa estar presente para aceitar positivo do modelo
_TECH_KEYWORDS = re.compile(
    r"(?:"
    r"\b(?:audio|áudio)\b|\bsom\b|\bnarr|\bmicrofone|\bmic\b"  # áudio
    r"|\b(?:video|vídeo)\b|\btela\b|\bimagem\b|\bpixel|\bqualidade\b"  # vídeo
    r"|\btravand|\btravan|\bfreez"                               # travamento (congel removido — ambíguo com clima)
    r"|\bbuffer|\blag\b|\bping\b|\bcaiu\b|\bcarregan|\bloadin"  # rede
    r"|\bsem\s+(?:som|audio|áudio|video|vídeo|imagem|sinal)"    # ausência
    r"|\bcortand|\bestouran|\bestourad|\bchian|\bruído|\beco\b"  # distorção
    r"|\bpreta\b|\bescura\b|\bborrad|\bpixelad"                 # visual
    r"|\bplacar\b|\bgc\b"                                       # GC
    r"|\bmudo|\bmuta|\bdessincroni|\batraso|\badianta|\bdelay"   # sincronia
    r"|\bvazand|\bvazou\b|\bvazamento"                          # vazamento de áudio
    r")",
    re.I,
)

def _has_tech_keyword(text: str) -> bool:
    """Verifica se o texto contém pelo menos uma keyword técnica."""
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
        # Descarta classificações positivas com baixa confiança
        if is_tech and confidence < CLOUD_CONFIDENCE_THRESHOLD:
            is_tech = False
        # Rejeita falso positivo genérico (modelo disse técnico mas sem keyword match)
        cat_raw = data.get("category")
        if is_tech and (cat_raw is None or cat_raw == "OUTRO"):
            is_tech = False
        # Guarda contra falso positivo: modelo disse técnico mas nenhuma keyword técnica presente
        if is_tech and not _has_tech_keyword(comment):
            is_tech = False
        sev = (data.get("severity") or "none").lower()
        if sev not in ("none", "low", "medium", "high"):
            sev = "none"
        if not is_tech:
            sev = "none"
        # Fallback: modelo disse não-técnico, mas regex detecta problema claro
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
        _log_debug("classify: SERVING_URL não configurado")
        return None
    return cloud_classify(comment)

# ─── MONITOR DE CHAT (processo filho) ────────────────────────────────────────
def _sig(author: str, msg: str, ts_iso: Optional[str], mid: Optional[str]) -> str:
    if mid:
        return "id:" + mid
    base = f"{author}|{msg}|{(ts_iso or '')[:19]}"
    return "h:" + hashlib.sha1(base.encode("utf-8", errors="ignore")).hexdigest()

def _create_chat(video_id: str):
    return pytchat.create(video_id=video_id, topchat_only=False, interruptable=True)

def monitor_process_main(channel_display: str, video_id: str, title: str, queue: Queue):
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

        while True:
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
                            ts_chat = getattr(c, "datetime", None)
                            if not isinstance(ts_chat, str):
                                ts_raw = getattr(c, "timestamp", None)
                                if isinstance(ts_raw, (int, float)):
                                    ts_chat = datetime.fromtimestamp(
                                        ts_raw / 1000, tz=timezone(timedelta(hours=-3))
                                    ).isoformat()
                        except Exception:
                            ts_chat = None

                        sig = _sig(author, msg, ts_chat if isinstance(ts_chat, str) else None, mid)
                        if sig in recent_set:
                            continue
                        recent.append(sig)
                        recent_set.add(sig)
                        if len(recent) == recent.maxlen:
                            try:
                                oldest = recent[0]
                                recent_set.discard(oldest)
                            except Exception:
                                pass

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

# ─── LIMPEZA DE EMOJIS CUSTOM DO YOUTUBE ──────────────────────────────────────
_YT_EMOJI_RE = re.compile(r":[^:\s]{1,50}:")

def _clean_yt_emojis(text: str) -> str:
    """Remove emoji codes custom do YouTube (:nome:) da mensagem.
    Emojis Unicode normais (😂❤️🔥) passam intactos."""
    return _YT_EMOJI_RE.sub("", text).strip()

# ─── PRÉ-FILTRO RÁPIDO (descarta mensagens óbvias sem chamar IA) ─────────────
_PREFILTER_SKIP = re.compile(
    r"^[\U0001F600-\U0001FAFF\U00002702-\U000027B0\s❤️🔥👏😂🤣💀😍🥰😭😎👍🇧🇷]+$"  # só emojis
    r"|^.{0,2}$"                                                                        # < 3 chars
    r"|^(?:boa\s+(?:noite|tarde)|bom\s+dia|oi+|ola|hello|hi)\b"                        # saudações
    r"|^(?:goo*l+|golaço|que\s+golaço)\b"                                               # torcida
    r"|^(?:vai\s+\w+|vamo|bora)\b"                                                      # torcida
    r"|^(?:kkk+|haha+|rsrs+|lol+)\s*$"                                                  # risadas
, re.I | re.UNICODE)

def _should_skip_classify(text: str) -> bool:
    """Retorna True se o texto é obviamente não-técnico e pode pular a IA."""
    return bool(_PREFILTER_SKIP.search(text.strip()))

# ─── QUEUE CONSUMER (batch GPU) ───────────────────────────────────────────────
#
# Arquitetura para alto volume (até 500 msg/s):
#
#   pytchat → multiprocessing.Queue → consumer_loop
#                  ↓ (enqueue imediato, O(1))
#             _batch_queue (stdlib thread-safe)
#                  ↓ (drena a cada BATCH_MAX_WAIT s ou BATCH_SIZE itens)
#             _batcher_loop → POST /classify/batch (GPU, até 64 textos/req)
#                  ↓ (resultados em batch)
#             _process_batch → Firestore WriteBatch (reduz RPCs)
#
# Contadores do live doc (total_comments, technical_comments, issue_counts)
# são acumulados em memória e gravados no Firestore a cada FS_FLUSH_SECS,
# evitando o problema de "hot document" a 500 writes/s.
# ─────────────────────────────────────────────────────────────────────────────

_batch_queue:   Optional[_stdlib_queue.Queue] = None
_counter_lock   = Lock()
_pending_counts: dict = {}   # vid → {total, technical, issue_counts}


def _accum_counter(vid: str, is_tech: bool, category, issue):
    """Acumula contadores em memória — flush periódico via _counter_flush_loop."""
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
    for vid, c in snapshot.items():
        try:
            fs = _get_fs()
            if not fs:
                continue
            upd: dict = {
                "total_comments":     fb_firestore.Increment(c["total"]),
                "technical_comments": fb_firestore.Increment(c["technical"]),
                "last_seen_at":       now_iso(),
            }
            # Usa nested dict (não dot-notation) para issue_counts:
            # evita erro "Invalid char" quando a categoria tem '/' (ex: REDE/PLATAFORMA)
            if c["issue_counts"]:
                upd["issue_counts"] = {
                    key: fb_firestore.Increment(n)
                    for key, n in c["issue_counts"].items()
                }
            fs.collection("lives").document(vid).update(upd)
        except Exception as e:
            _log_debug(f"[counter_flush] {vid}: {e}")


def _counter_flush_loop():
    """Thread daemon: flush periódico de contadores."""
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

    # Itens que precisam de IA vs pré-filtrados
    ai_items  = [it for it in items if it["needs_ai"]]
    ai_texts  = [it["text"] for it in ai_items]

    # Chama /classify/batch — 1 request para N textos (GPU)
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

    # Firestore WriteBatch — salva comment docs + minutes de uma vez
    fs = _get_fs()
    if not fs:
        return

    batch = fs.batch()
    batch_ops = 0

    def _maybe_commit():
        nonlocal batch, batch_ops
        if batch_ops >= 400:   # limite do WriteBatch é 500; margem de segurança
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

        # Grava comentário
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
        # Coleta até BATCH_SIZE itens ou até BATCH_MAX_WAIT segundos
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
            to_send  = pending[:BATCH_SIZE]
            pending  = pending[BATCH_SIZE:]
            try:
                _process_batch(to_send)
            except Exception:
                _log_debug(f"[batcher] error: {traceback.format_exc()}")

        last_send = time.time()


def _process_chat_item(vid: str, author: str, text: str, ts: str):
    """Limpa, pré-filtra e enfileira no batcher (O(1), não bloqueia o consumer)."""
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
            _log_debug(f"[batcher] fila cheia — descartando msg de {vid}")

    except Exception:
        _log_debug(f"[_process_chat_item] error: {traceback.format_exc()}")


def queue_consumer_loop(q: Queue):
    global _batch_queue
    _batch_queue = _stdlib_queue.Queue(maxsize=200_000)

    Thread(target=_batcher_loop,       daemon=True, name="batcher").start()
    Thread(target=_counter_flush_loop, daemon=True, name="counter_flush").start()
    _log_debug(f"[consumer] batch_size={BATCH_SIZE} max_wait={BATCH_MAX_WAIT}s flush={FS_FLUSH_SECS}s")

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
                title = item.get("title") or ""
                url   = item.get("url", f"https://www.youtube.com/watch?v={vid}")
                if not title or title == vid:
                    title = oembed_title(vid)
                fs_upsert_live(vid, ch, title, url)

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

# ─── SUPERVISOR ──────────────────────────────────────────────────────────────
def _load_active_from_firestore(channel_display: str):
    """Na inicialização, popula active_videos com lives status=active do Firestore.
    Assim o miss-tolerance encerra lives de sessões anteriores na 1ª varredura."""
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
                            preset_channel_id: str, queue: Queue):
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
            _log_debug(f"[{channel_display}] varredura em {dt:.1f}s — {len(lives)} live(s)")

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
                proc = running_monitors.get(key)
                nowt = time.time()
                if not proc or not proc.is_alive():
                    last_attempt = last_start_attempt.get(key, 0)
                    if nowt - last_attempt > CHAT_RETRY_SECONDS:
                        _log_debug(f"[{channel_display}] iniciando monitor {vid} ({title})")
                        p = Process(
                            target=monitor_process_main,
                            args=(channel_display, vid, title, queue),
                            daemon=True,
                        )
                        p.start()
                        running_monitors[key] = p
                        last_start_attempt[key] = nowt

            # Miss tolerance — encerra monitores de lives que sumiram
            with state_lock:
                known = set(active_videos.get(channel_display, set()))
                for vid in known:
                    if vid not in current_ids:
                        video_misses[vid] = video_misses.get(vid, 0) + 1
                to_remove = [vid for vid in known if video_misses.get(vid, 0) >= MISS_TOLERANCE]
                for vid in to_remove:
                    active_videos[channel_display].discard(vid)
                    video_misses.pop(vid, None)
                    queue.put({"type": "ended", "channel": channel_display, "video_id": vid})
                    stop_monitor(channel_display, vid)
                    _log_debug(f"[{channel_display}] live encerrada: {vid}")

            time.sleep(SUPERVISOR_POLL_SECONDS)

        except Exception as e:
            _log_debug(f"[{channel_display}] Erro supervisor: {e}")
            traceback.print_exc()
            time.sleep(10)

# ─── BOOTSTRAP ───────────────────────────────────────────────────────────────
q: Queue = Queue()

def queue_consumer_bootstrap():
    # Um único dispatcher thread + ThreadPoolExecutor interno com LLM_WORKERS
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
    for key, proc in list(running_monitors.items()):
        try:
            if proc.is_alive():
                proc.terminate()
        except Exception:
            pass
    running_monitors.clear()
    raise SystemExit(0)

# ─── MAIN ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)
    signal.signal(signal.SIGINT,  _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)

    print("=" * 60)
    print("  Monitor de Lives — CazéTV")
    print(f"  Cloud Run : {SERVING_URL or 'NAO CONFIGURADO — defina SERVING_URL'}")
    print(f"  Firestore : {'ativo' if FIRESTORE_ENABLED else 'desativado'}")
    print("=" * 60)
    for ch in CHANNELS:
        print(f"  Canal: {ch['display']} ({ch.get('handle', '')})")
    print("=" * 60)

    queue_consumer_bootstrap()
    supervisors_bootstrap()

    # Mantém o processo principal vivo
    while True:
        time.sleep(1)
