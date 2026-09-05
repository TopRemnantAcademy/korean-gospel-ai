# DESIGN.md — Design Token Source of Truth

> This file is the **single source of truth** for design tokens across all three
> front-ends (root `app.py` Streamlit, `admin/`, `mobile/`). When a token changes,
> update it here first, then mirror into code. Do not hard-code colors/spacing in
> component files.

## 1. Brand

| Token | Value | Notes |
|-------|-------|-------|
| Brand name | (Gospel AI) | formerly "회복 AI" — rebranded in P3-1 |
| Icon | — | brand leaf emoji (🌿) removed per user request; no single glyph brand icon |
| Domain | Gospel / spiritual care (믿음, 말씀, 기도, 위로) | addiction-domain copy removed in P3-1 |

## 2. Color tokens (Streamlit `app.py` — `THEMES["dark"]`)

All keys below live in the single `THEMES` dict in `app.py`. Access via
`THEMES.get(theme_key, THEMES["dark"])` (crash-safe, P3-2) — never `THEMES[key]`.

| Token | Value | Usage |
|-------|-------|-------|
| `app_bg` | `#0d0d0d` | page background |
| `surface` | `#1a1a1a` | cards / panels |
| `sidebar_bg` | `#0d0d0d` | sidebar |
| `sidebar_hover` | `#1f1f1f` | sidebar hover |
| `sidebar_text` | `#e8e8e8` | sidebar text |
| `input_bg` | `#1a1a1a` | text inputs |
| `input_border` | `#333333` | input border |
| `input_focus` | `#4285f4` | **focus ring** (WCAG visible focus, P3-2) |
| `text` | `#e8e8e8` | primary text |
| `text_sub` | `#9aa0a6` | secondary text |
| `text_muted` | `#5f6368` | muted / captions |
| `divider` | `#282828` | hairlines |
| `accent` | `#4285f4` | primary accent (Google Blue) |
| `accent_secondary` | `#9c27b0` | gradient secondary |
| `accent_glow` | `rgba(66,133,244,0.20)` | glow |
| `chip_bg` / `chip_border` / `chip_hover` / `chip_text` | `#1a1a1a` / `#333333` / `#282828` / `#e8e8e8` | suggestion chips |
| `btn_bg` / `btn_text` | `#1a1a1a` / `#e8e8e8` | buttons |
| `popup_bg` | `#0d0d0d` | modals |
| `user_msg_bg` | `#1a1a1a` | user message bubble |
| `gradient_start` / `gradient_mid` / `gradient_end` | `#4285f4` / `#9c27b0` / `#ea4335` | gradients |
| `shadow` | `rgba(0,0,0,0.25)` | elevation |

## 3. Mobile / Admin unified tokens (Gospel palette)

Adopted per remediation plan §174 — Espresso base + emerald + brass-gold + serif.
Keep these in sync with `mobile/` and `admin/` token files.

| Token | Value |
|-------|-------|
| Base (espresso) | `#1b1410` |
| Emerald | `#2e8b74` |
| Brass gold | `#c9a24b` |
| Serif font | `Noto Serif KR` |

## 4. Accessibility (WCAG AA)

- **Visible focus**: `*:focus-visible { outline: 2px solid input_focus }` (P3-2).
- **Gradient titles**: solid `color` fallback declared before `@supports` gradient
  clip — text never becomes invisible (P3-2).
- **Copy / Share buttons**: restored (no longer force-hidden, P3-2).
- Contrast: `text #e8e8e8` on `#0d0d0d` ≈ 15:1 (passes AA).

## 5. Life-safety resources (do NOT remove)

Crisis hotlines are preserved in `app.py` (`_panel_emergency`, emergency banner)
regardless of domain rebrand:

- 자살예방상담전화 **1393**
- 정신건강위기상담 **1577-0199**
- 보건복지상담센터 **129**
- 생명의 전화 **1588-9191**
