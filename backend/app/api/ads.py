"""Ads API — mobile public query + admin CRUD.
Stores ads metadata in data/ads.json and images in data/ads_images/.
"""
from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from .enhanced_rag import require_admin

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
_ADS_FILE = _DATA_DIR / "ads.json"
_IMG_DIR = _DATA_DIR / "ads_images"

# ── Routers ──────────────────────────────────────────────────────
public_router = APIRouter(prefix="/ads", tags=["ads-public"])
admin_router = APIRouter(prefix="/admin/ads", tags=["ads-admin"],
                         dependencies=[Depends(require_admin)])

# ── Models ───────────────────────────────────────────────────────
class AdSlot(str):
    qa_top    = "qa_top"     # 인기QA 상단 배너
    qa_feed   = "qa_feed"    # 인기QA 리스트 사이
    today_top = "today_top"  # Today 화면 상단 배너 (인기QA+채팅 합병 탭)

class AdCreate(BaseModel):
    title: str
    subtitle: Optional[str] = ""
    link_url: Optional[str] = ""
    slot: str = "qa_top"   # "qa_top" | "qa_feed" | "today_top"
    active: bool = True
    image_data: Optional[str] = None  # base64 (data:image/... or raw)

class AdUpdate(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    link_url: Optional[str] = None
    slot: Optional[str] = None
    active: Optional[bool] = None
    image_data: Optional[str] = None  # base64 for update; null = keep current

# ── helpers ──────────────────────────────────────────────────────
def _load_ads() -> list[dict]:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _IMG_DIR.mkdir(parents=True, exist_ok=True)
    if _ADS_FILE.exists():
        try:
            return json.loads(_ADS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []

def _save_ads(ads: list[dict]):
    _ADS_FILE.write_text(json.dumps(ads, ensure_ascii=False, indent=2), encoding="utf-8")

def _image_path(ad_id: str, ext: str = ".png") -> Path:
    return _IMG_DIR / f"{ad_id}{ext}"

def _ads_for_client(ads: list[dict]) -> list[dict]:
    """Public API: strip internal fields; include image as base64 data URI."""
    out = []
    for a in ads:
        if not a.get("active", True):
            continue
        item = {
            "id": a["id"],
            "title": a.get("title", ""),
            "subtitle": a.get("subtitle", ""),
            "link_url": a.get("link_url", ""),
            "slot": a.get("slot", "qa_top"),
        }
        # attach image if exists
        img_path = _image_path(a["id"]) if a["id"] else None
        if img_path and img_path.exists():
            item["image_url"] = f"/ads/image/{a['id']}"
        out.append(item)
    return out

# ── Public ───────────────────────────────────────────────────────
@public_router.get("/list")
async def list_ads():
    """Return active ads grouped by slot (public)."""
    ads = _load_ads()
    return {"ads": _ads_for_client(ads)}

@public_router.get("/image/{ad_id}")
async def get_ad_image(ad_id: str):
    """Serve static ad image."""
    img_path = _image_path(ad_id)
    if not img_path.exists():
        # try with other extensions
        for ext in [".png", ".jpg", ".jpeg", ".webp"]:
            alt = _IMG_DIR / f"{ad_id}{ext}"
            if alt.exists():
                img_path = alt
                break
        else:
            raise HTTPException(404, "Image not found")
    from fastapi.responses import FileResponse
    return FileResponse(img_path, media_type="image/" + img_path.suffix.lstrip("."))

# ── Admin ────────────────────────────────────────────────────────
@admin_router.get("/list")
async def admin_list_ads():
    """Admin: full ad list with image presence flag."""
    ads = _load_ads()
    for a in ads:
        a["has_image"] = _image_path(a["id"]).exists()
    return {"ads": ads}

@admin_router.post("/create")
async def admin_create_ad(ad: AdCreate):
    """Create a new ad with optional base64 image."""
    ads = _load_ads()
    ad_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()

    entry = {
        "id": ad_id,
        "title": ad.title,
        "subtitle": ad.subtitle or "",
        "link_url": ad.link_url or "",
        "slot": ad.slot,
        "active": ad.active,
        "created_at": now,
        "updated_at": now,
    }
    ads.append(entry)

    # save image
    if ad.image_data:
        _save_image(ad_id, ad.image_data)

    _save_ads(ads)
    entry["has_image"] = _image_path(ad_id).exists()
    return {"ok": True, "ad": entry}

@admin_router.put("/{ad_id}")
async def admin_update_ad(ad_id: str, ad: AdUpdate):
    """Update an existing ad."""
    ads = _load_ads()
    found = None
    for a in ads:
        if a["id"] == ad_id:
            found = a
            break
    if not found:
        raise HTTPException(404, "Ad not found")

    for f in ["title", "subtitle", "link_url", "slot", "active"]:
        val = getattr(ad, f, None)
        if val is not None:
            found[f] = val
    found["updated_at"] = datetime.now(timezone.utc).isoformat()

    if ad.image_data is not None:
        # None = keep current, empty = delete, data = update
        if ad.image_data == "":
            _delete_image(ad_id)
        else:
            _save_image(ad_id, ad.image_data)

    _save_ads(ads)
    found["has_image"] = _image_path(ad_id).exists()
    return {"ok": True, "ad": found}

@admin_router.delete("/{ad_id}")
async def admin_delete_ad(ad_id: str):
    """Delete an ad and its image."""
    ads = _load_ads()
    new_ads = [a for a in ads if a["id"] != ad_id]
    if len(new_ads) == len(ads):
        raise HTTPException(404, "Ad not found")
    _save_ads(new_ads)
    _delete_image(ad_id)
    return {"ok": True}

# ── Image helpers ────────────────────────────────────────────────
def _save_image(ad_id: str, data_uri: str):
    if not data_uri:
        return
    # strip data:image/...;base64, prefix
    if data_uri.startswith("data:"):
        # e.g., "data:image/png;base64,iVBOR..."
        header, encoded = data_uri.split(",", 1)
        ext = header.split(";")[0].split("/")[-1] if "/" in header else "png"
        data = base64.b64decode(encoded)
    else:
        ext = "png"
        data = base64.b64decode(data_uri)
    for old_ext in ["png", "jpg", "jpeg", "webp"]:
        p = _IMG_DIR / f"{ad_id}.{old_ext}"
        if p.exists():
            p.unlink()
    path = _IMG_DIR / f"{ad_id}.{ext}"
    path.write_bytes(data)

def _delete_image(ad_id: str):
    for ext in ["png", "jpg", "jpeg", "webp"]:
        p = _IMG_DIR / f"{ad_id}.{ext}"
        if p.exists():
            p.unlink()
