from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .models import FetchedSource, SearchResult
from .utils import ensure_directory, normalize_whitespace, slugify


POSITIVE_HINTS = ("article", "content", "post", "entry", "main", "body", "text")
NEGATIVE_HINTS = (
    "nav",
    "menu",
    "footer",
    "header",
    "sidebar",
    "comment",
    "share",
    "promo",
    "ad",
    "cookie",
    "navbox",
    "portal",
    "reference",
    "reflist",
    "toc",
    "metadata",
    "vector",
    "user-links",
)
BLOCK_TAGS = {"p", "div", "section", "article", "main", "li", "h1", "h2", "h3", "h4", "blockquote"}
SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "form"}
NOISE_MARKERS = (
    "mw-parser-output",
    "rlconf=",
    "rlstate=",
    "rlpagemodules",
    "jump to content",
    "create account",
    "log in",
    "main menu",
    "personal tools",
    "donate",
    "privacy policy",
    "cookie statement",
    "please wait for verification",
    "verify you are human",
    "captcha",
    "under construction",
    "to the sister website",
    "private website",
)
REJECTION_MARKERS = (
    "please wait for verification",
    "verify you are human",
    "captcha",
    "access denied",
    "enable javascript and cookies",
)
DIRECTORY_PAGE_MARKERS = (
    "to the sister website",
    "aqueduct news",
    "historical introduction",
    "technical introduction",
    "aqueduct dictionary",
    "questions and answers",
    "information on 100 selected",
    "literature on 600 aqueducts",
    "ancient aqueduct statistics",
    "some selected papers",
    "under construction",
    "in dutch",
    "private website",
)
TRAILING_SECTION_MARKERS = (
    "references",
    "external links",
    "further reading",
    "see also",
)


def _score_attrs(tag: str, attrs: dict[str, str]) -> int:
    score = 0
    if tag in {"article", "main"}:
        score += 6
    if tag in {"p", "section"}:
        score += 2
    hints = " ".join(attrs.values()).lower()
    score += sum(3 for hint in POSITIVE_HINTS if hint in hints)
    score -= sum(4 for hint in NEGATIVE_HINTS if hint in hints)
    return score


@dataclass(slots=True)
class TextBlock:
    text: str
    score: int
    order: int


class MainContentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[TextBlock] = []
        self.tag_stack: list[dict[str, object]] = []
        self.current_parts: list[str] = []
        self.block_index = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        hint_score = _score_attrs(tag.lower(), attr_map)
        skip = tag.lower() in SKIP_TAGS or hint_score <= -4
        self.tag_stack.append({"tag": tag.lower(), "score": hint_score, "skip": skip})
        if tag.lower() in BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in BLOCK_TAGS:
            self._flush()
        if self.tag_stack:
            self.tag_stack.pop()

    def handle_data(self, data: str) -> None:
        if any(bool(item["skip"]) for item in self.tag_stack):
            return
        text = normalize_whitespace(unescape(data))
        if text:
            self.current_parts.append(text)

    def _flush(self) -> None:
        text = normalize_whitespace(" ".join(self.current_parts))
        self.current_parts = []
        if len(text) < 40:
            return
        if looks_like_noise_text(text):
            return
        score = sum(int(item["score"]) for item in self.tag_stack)
        self.blocks.append(TextBlock(text=text, score=score, order=self.block_index))
        self.block_index += 1


def looks_like_noise_text(text: str) -> bool:
    lowered = text.lower()
    if any(marker in lowered for marker in NOISE_MARKERS):
        return True
    if len(re.findall(r"[{};=]", text)) > max(24, len(text) // 18):
        return True
    if re.search(r"\b(function\(|var\s+[A-Za-z_]+|document\.|window\.)", text):
        return True
    return False


def looks_like_directory_page(title: str, text: str) -> bool:
    lowered = f"{title}\n{text[:2000]}".lower()
    marker_hits = sum(1 for marker in DIRECTORY_PAGE_MARKERS if marker in lowered)
    if title.lower().startswith("website on "):
        marker_hits += 2
    colon_labels = len(re.findall(r"\b[A-Z][A-Za-z]{2,}\s*:", text[:1500]))
    return marker_hits >= 2 or (marker_hits >= 1 and colon_labels >= 4)


def _remove_tag_blocks(html: str, pattern: str) -> str:
    return re.sub(pattern, " ", html, flags=re.IGNORECASE | re.DOTALL)


def _sanitize_html(html: str) -> str:
    cleaned = html
    cleaned = _remove_tag_blocks(cleaned, r"<!--.*?-->")
    for tag in ("script", "style", "noscript", "svg", "canvas", "form", "template"):
        cleaned = _remove_tag_blocks(cleaned, rf"<{tag}\b[^>]*>.*?</{tag}>")
    for hint in NEGATIVE_HINTS:
        cleaned = _remove_tag_blocks(
            cleaned,
            rf"<(div|section|aside|nav|footer|header|table|ul|ol|dl)[^>]*(?:id|class)=[\"'][^\"']*{re.escape(hint)}[^\"']*[\"'][^>]*>.*?</\1>",
        )
    return cleaned


def _extract_article_fragment(html: str) -> str:
    body_match = re.search(r"<body\b[^>]*>(.*)</body>", html, flags=re.IGNORECASE | re.DOTALL)
    body = body_match.group(1) if body_match else html

    wikipedia_match = re.search(
        r"<div[^>]+id=[\"']mw-content-text[\"'][^>]*>(.*?)(?:<div[^>]+id=[\"']catlinks[\"']|</body>)",
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if wikipedia_match:
        return wikipedia_match.group(1)

    for pattern in (
        r"<article\b[^>]*>(.*?)</article>",
        r"<main\b[^>]*>(.*?)</main>",
        r"<div[^>]+(?:id|class)=[\"'][^\"']*(content|article|post|entry|main)[^\"']*[\"'][^>]*>(.*?)</div>",
    ):
        match = re.search(pattern, body, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        fragment = match.group(match.lastindex or 1)
        if len(re.sub(r"<[^>]+>", " ", fragment)) > 400:
            return fragment
    return body


def _trim_trailing_sections(text: str) -> str:
    for marker in TRAILING_SECTION_MARKERS:
        match = re.search(rf"\n{re.escape(marker)}\n", text, flags=re.IGNORECASE)
        if match and match.start() > 600:
            return text[:match.start()].strip()
    return text


def validate_cleaned_content(title: str, cleaned: str) -> None:
    lowered = f"{title}\n{cleaned[:1200]}".lower()
    if any(marker in lowered for marker in REJECTION_MARKERS):
        raise ValueError("Page appears to be a verification wall or blocked response.")
    if len(re.findall(r"[A-Za-z]{3,}", cleaned)) < 120:
        raise ValueError("Insufficient article content extracted from the source.")
    if looks_like_noise_text(cleaned[:2000]):
        raise ValueError("Extracted content still looks like HTML, script, or navigation noise.")
    if looks_like_directory_page(title, cleaned):
        raise ValueError("Extracted content looks like a directory or navigation page, not an article.")


def extract_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return "Untitled Source"
    title = re.sub(r"<[^>]+>", " ", match.group(1))
    return normalize_whitespace(unescape(title)) or "Untitled Source"


def extract_main_text(html: str) -> str:
    sanitized = _sanitize_html(_extract_article_fragment(html))
    parser = MainContentParser()
    parser.feed(sanitized)
    candidate_blocks = [block for block in parser.blocks if not looks_like_noise_text(block.text)]
    positively_scored = [block for block in candidate_blocks if block.score >= 1]
    selected_blocks = positively_scored or candidate_blocks
    selected_blocks = sorted(selected_blocks, key=lambda block: (block.order, -block.score))
    blocks = [block.text for block in selected_blocks[:40]]
    if not blocks:
        stripped = re.sub(r"<[^>]+>", " ", sanitized)
        return _trim_trailing_sections(normalize_whitespace(unescape(stripped)))
    return _trim_trailing_sections(normalize_whitespace("\n\n".join(blocks)))


class PageFetcher:
    def __init__(self, raw_root: Path, timeout: float, user_agent: str):
        self.raw_root = ensure_directory(raw_root)
        self.timeout = timeout
        self.user_agent = user_agent

    def _build_source_id(self, url: str, title: str) -> str:
        slug = slugify(title)[:80]
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
        return f"{slug}-{digest}"

    def _detect_extension(self, content_type: str) -> str:
        lowered = content_type.lower()
        if "html" in lowered:
            return ".html"
        if "markdown" in lowered:
            return ".md"
        if "plain" in lowered or "text" in lowered:
            return ".txt"
        return ".bin"

    def fetch(self, topic: str, result: SearchResult) -> FetchedSource:
        request = Request(result.url, headers={"User-Agent": self.user_agent})
        with urlopen(request, timeout=self.timeout) as response:
            raw_bytes = response.read()
            content_type = response.headers.get_content_type()
            charset = response.headers.get_content_charset() or "utf-8"
            last_updated = response.headers.get("Last-Modified")
        raw_text = raw_bytes.decode(charset, errors="replace")
        if content_type == "text/html":
            title = extract_title(raw_text) or result.title
            cleaned = extract_main_text(raw_text)
        else:
            title = result.title or Path(urlsplit(result.url).path).stem or "Untitled Source"
            cleaned = normalize_whitespace(raw_text)
        validate_cleaned_content(title, cleaned)
        retrieval_timestamp = datetime.now(timezone.utc).isoformat()
        source_id = self._build_source_id(result.url, title)
        extension = self._detect_extension(content_type)
        raw_file = self.raw_root / f"{source_id}__raw{extension}"
        cleaned_file = self.raw_root / f"{source_id}__cleaned.txt"
        metadata_file = self.raw_root / f"{source_id}__metadata.json"
        raw_file.write_text(raw_text, encoding="utf-8")
        cleaned_file.write_text(cleaned, encoding="utf-8")
        metadata = {
            "topic": topic,
            "title": title,
            "url": result.url,
            "query": result.query,
            "snippet": result.snippet,
            "content_type": content_type,
            "retrieved_at": retrieval_timestamp,
            "last_updated": last_updated,
        }
        metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return FetchedSource(
            title=title,
            url=result.url,
            snippet=result.snippet,
            query=result.query,
            raw_content=raw_text,
            cleaned_content=cleaned,
            content_type=content_type,
            retrieval_timestamp=retrieval_timestamp,
            last_updated=last_updated,
            source_id=source_id,
            raw_file=str(raw_file),
            cleaned_file=str(cleaned_file),
            metadata_file=str(metadata_file),
        )
