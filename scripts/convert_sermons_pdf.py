#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convert 조헌수 목사 sermon PDFs -> clean Markdown.

Pipeline:
  1. Parse filename -> metadata (date / service / pastor / title / passage)
  2. Extract text (pymupdf) — text-based PDFs only (verified)
  3. Clean:
     - drop page-number lines (  - N -  )
     - drop blank / pure-punctuation lines
     - page 0: trim to first '성경봉독' (drops title block + 대표기도);
       if no '성경봉독' on page 0, keep page 0 but strip header-noise lines
     - remove any residual '대표기도' block (user asked to drop it)
     - split into 봉독 verses (lines starting with a digit) and sermon body
     - strip stray '( 16:1~6 )' reference fragments
  4. Sentence segmentation (regex, fast + safe — kss is too slow on long
     texts per Task O). Insert a space at no-space joins like 바랍니다+본문은
     (terminal eomi '다/까/죠/네/라' followed by Hangul), then split on
     terminal punctuation + whitespace.
  5. Structure: title + metadata + '## 성경봉독' (numbered verses) +
     '## 설교 본문' with '### 서론 / ### 본론 / ### 결론' promoted from
     the first occurrence of each marker.
  6. Write to data/documents/{date}_{title}.md

Usage:
  python scripts/convert_sermons_pdf.py --manifest scripts/_sermon_pdf_manifest.txt \
         --out data/documents
"""
import argparse
import fitz  # pymupdf
import os
import re
import sys

# ---------------------------------------------------------------------------
# 1. Filename -> metadata
# ---------------------------------------------------------------------------
def parse_filename(path):
    name = os.path.basename(path)[:-4]  # strip .pdf
    date_raw = re.search(r"\d{8}", name)
    date = date_raw.group() if date_raw else ""
    date_iso = f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 else date

    svc = ""
    m = re.search(r"\[([주일][^\]]*)\]", name)
    if m:
        svc = m.group(1)
        svc = re.sub(r"주일(\d)", r"주일 \1", svc)  # 주일1부 -> 주일 1부

    pastor = "조헌수 목사"

    passages = re.findall(r"\(([^)]*)\)", name)
    passage = passages[-1].strip() if passages else ""

    # title = strip date, brackets, pastor, trailing passage
    t = name
    if date:
        t = t.replace(date, "", 1)
    t = re.sub(r"\[[^\]]*\]", "", t)          # remove all [..]
    t = re.sub(r"[\[\]]", "", t)               # any stray brackets
    t = re.sub(r"조헌수\s*목사", "", t)        # remove pastor text
    if passage:
        t = t.replace("(" + passage + ")", "")
    t = re.sub(r"\([^)]*\)", "", t)            # any other parens
    title = re.sub(r"\s+", " ", t).strip()
    safe = re.sub(r"\s+", "", title)
    return {
        "date": date,
        "date_iso": date_iso,
        "service": svc,
        "pastor": pastor,
        "title": title,
        "passage": passage,
        "safe_title": safe,
    }


# ---------------------------------------------------------------------------
# 2+3. Extract + clean
# ---------------------------------------------------------------------------
PAGE_NUM_RE = re.compile(r"^\s*-\s*\d+\s*-\s*$")
PURE_PUNCT_RE = re.compile(r"^[\s\.\,\-\·\:\;\!\?\'\"]+$")
PASSAGE_FRAG_RE = re.compile(r"^[\(\d:\~\-\s\)]+$")
HEADER_NOISE_RE = re.compile(r"(20\d{6}|주일부|조헌수\s*목사|^\s*\[\s*)$")
REF_PREFIX_RE = re.compile(r"^\([^)]*\)\s*")          # ( 16:1~6)  leading ref on a verse
VERSE_RE = re.compile(r"^\d+\s")                        # verse line starts with a number
BODY_SIGNAL_RE = re.compile(r"찬양|서론|본론|결론")      # clear body-start markers (never in scripture)


def drop_daepyo(lines):
    """Remove any residual '대표기도' block (user asked to drop it)."""
    res = []
    skip = False
    for ln in lines:
        if "대표기도" in ln:
            skip = True
            continue
        if skip:
            # resume when a clear sermon-structure keyword appears
            if any(k in ln for k in ["성경봉독", "서론", "본론", "결론",
                                      "찬양", "말씀", "개요", "설교"]):
                skip = False
                res.append(ln)
            continue
        res.append(ln)
    return res


def clean_lines(doc):
    raw_pages = [doc[pi].get_text("text") for pi in range(doc.page_count)]

    out = []
    for pi, txt in enumerate(raw_pages):
        lines = txt.split("\n")
        if pi == 0:
            start = None
            for i, ln in enumerate(lines):
                if "성경봉독" in ln:
                    start = i
                    break
            if start is not None:
                lines = lines[start:]
            else:
                lines = [ln for ln in lines if not HEADER_NOISE_RE.search(ln)]
        for ln in lines:
            s = ln.strip()
            if not s:
                continue
            if PAGE_NUM_RE.match(s):
                continue
            if PURE_PUNCT_RE.match(s):
                continue
            out.append(s)

    out = drop_daepyo(out)

    # split into 봉독 verses + body
    bongdo_idx = None
    for i, ln in enumerate(out):
        if "성경봉독" in ln:
            bongdo_idx = i
            break

    if bongdo_idx is None:
        return [], out

    # collect 봉독 verses (lines starting with a digit). Verse lines may wrap
    # onto a follow-up line with no leading digit -> append as continuation.
    # Stop at the first non-verse line that clearly starts the sermon body.
    j = bongdo_idx + 1
    verses = []
    verse_mode = False
    while j < len(out):
        ln = out[j]
        if VERSE_RE.match(ln):
            verses.append(ln)
            verse_mode = True
        elif verse_mode:
            if BODY_SIGNAL_RE.search(ln):
                break  # body starts here
            # continuation of the previous (wrapped) verse
            verses[-1] = (verses[-1] + " " + ln).strip()
        else:
            # stray reference fragment between heading and verse 1 -> skip
            pass
        j += 1
    body_lines = out[j:]

    # strip a leading '( 16:1~6 )' reference from the first verse line
    if verses:
        verses[0] = REF_PREFIX_RE.sub("", verses[0]).strip()
    return verses, body_lines


# ---------------------------------------------------------------------------
# 4. Sentence segmentation (regex, fast + safe)
# ---------------------------------------------------------------------------
# Insert a space at no-space joins: a terminal eomi (다/까/죠/네/라) directly
# followed by a Hangul syllable = new-sentence start with no space inserted
# by the PDF extractor (e.g. 바랍니다+본문은 -> 바랍니다 본문은).
EOMI_INSERT = re.compile(r"([다까죠네라])(?=[가-힣])")
SPLIT_RE = re.compile(
    r"(?<=다)\s+|(?<=요)\s+|(?<=까)\s+|(?<=죠)\s+|"
    r"(?<=네)\s+|(?<=라)\s+|(?<=[.!?])\s+"
)


def split_sentences(text):
    t = EOMI_INSERT.sub(r"\1 ", text)
    parts = SPLIT_RE.split(t)
    return [p.strip() for p in parts if p.strip()]


def group_paragraphs(sentences, max_chars=260):
    """Group sentences into readable paragraph blocks."""
    paras = []
    buf = ""
    for s in sentences:
        if buf and len(buf) + len(s) + 1 > max_chars:
            paras.append(buf)
            buf = s
        else:
            buf = (buf + " " + s).strip() if buf else s
    if buf:
        paras.append(buf)
    return paras


# ---------------------------------------------------------------------------
# 5. Structure into markdown
# ---------------------------------------------------------------------------
SECTION_RE = re.compile(r"^(서론|본론|결론)\s*")


def build_body_sections(sentences):
    sections = []          # (heading, [sentences])
    cur_heading = None
    cur_buf = []
    opened = set()

    def flush():
        nonlocal cur_heading, cur_buf
        if cur_heading is not None or cur_buf:
            sections.append((cur_heading, cur_buf))
        cur_heading = None
        cur_buf = []

    for s in sentences:
        m = SECTION_RE.match(s)
        if m and m.group(1) not in opened:
            flush()
            cur_heading = m.group(1)
            opened.add(cur_heading)
            rest = s[m.end():].strip()
            rest = re.sub(r"^-\s*", "", rest)            # drop leading " - "
            rest = re.sub(r"^결론입니다\.?$", "", rest)  # drop trailing echo
            cur_buf = [rest] if rest else []
        else:
            cur_buf.append(s)
    flush()
    return sections


def build_markdown(meta, verses, body_lines):
    head = []
    head.append(f"# {meta['date']} [{meta['service']}] [{meta['pastor']}] "
                + f"{meta['title']}"
                + (f" ({meta['passage']})" if meta["passage"] else ""))
    head.append("")
    head.append(f"- **날짜**: {meta['date_iso']}")
    head.append(f"- **예배**: {meta['service']}")
    head.append(f"- **설교자**: {meta['pastor']}")
    if meta["passage"]:
        head.append(f"- **본문**: {meta['passage']}")
    head.append("")
    head.append("---")
    head.append("")

    body = []
    if verses:
        body.append("## 성경봉독")
        body.append("")
        for v in verses:
            body.append(v)
        body.append("")

    body.append("## 설교 본문")
    body.append("")

    sentences = split_sentences(" ".join(body_lines))
    sections = build_body_sections(sentences)
    if not sections:
        sections = [(None, sentences)]

    for heading, sents in sections:
        if heading:
            body.append(f"### {heading}")
            body.append("")
        for para in group_paragraphs(sents):
            body.append(para)
            body.append("")

    return "\n".join(head + body).strip() + "\n"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", default="data/documents")
    args = ap.parse_args()

    with open(args.manifest, encoding="utf-8") as f:
        paths = [l.strip() for l in f if l.strip() and not l.startswith("#")]

    os.makedirs(args.out, exist_ok=True)

    seen = set()
    done = 0
    skipped_dup = 0
    for p in paths:
        if not os.path.exists(p):
            print(f"[WARN] missing: {p}", file=sys.stderr)
            continue
        meta = parse_filename(p)
        key = (meta["date"], meta["safe_title"])
        if key in seen:
            print(f"[SKIP dup] {meta['date']} {meta['safe_title']}")
            skipped_dup += 1
            continue
        seen.add(key)

        doc = fitz.open(p)
        verses, body_lines = clean_lines(doc)
        doc.close()
        md = build_markdown(meta, verses, body_lines)

        out_name = f"{meta['date']}_{meta['safe_title']}.md"
        out_path = os.path.join(args.out, out_name)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md)
        done += 1
        print(f"[OK] {out_name}  ({len(verses)} verses, "
              f"{len(body_lines)} raw lines, {len(md)} chars)")

    print(f"\nDONE: {done} written, {skipped_dup} dup skipped, "
          f"{len(paths)-done-skipped_dup} missing")


if __name__ == "__main__":
    main()
