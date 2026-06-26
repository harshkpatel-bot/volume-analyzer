"""

Web Crawler Framework

=====================

Crawls any website starting from a seed URL, discovers all internal pages,

counts outbound links per page, and exports results to a CSV file.

Usage:

    python web_crawler.py --url https://example.com

    python web_crawler.py --url https://example.com --depth 3 --output results.csv

    python web_crawler.py --url https://example.com --delay 1.5 --workers 5

Requirements:

    pip install requests beautifulsoup4 lxml

"""

import argparse

import csv

import logging

import time

from collections import deque

from concurrent.futures import ThreadPoolExecutor, as_completed

from dataclasses import dataclass, field

from datetime import datetime

from typing import Optional

from urllib.parse import urljoin, urlparse

import requests

from bs4 import BeautifulSoup

# ──────────────────────────────────────────────

# Configuration

# ──────────────────────────────────────────────

logging.basicConfig(

    level=logging.INFO,

    format="%(asctime)s [%(levelname)s] %(message)s",

    datefmt="%H:%M:%S",

)

log = logging.getLogger(__name__)

DEFAULT_HEADERS = {

    "User-Agent": (

        "Mozilla/5.0 (compatible; WebCrawlerFramework/1.0; "

        "+https://github.com/your-repo)"

    )

}

# ──────────────────────────────────────────────

# Data Model

# ──────────────────────────────────────────────

@dataclass

class PageNode:

    """Represents a single crawled page (node) in the site graph."""

    url: str

    parent_url: str = ""

    status_code: int = 0

    page_title: str = ""

    depth: int = 0

    internal_links: int = 0          # links pointing to same domain

    external_links: int = 0          # links pointing outside the domain

    total_links: int = 0             # all <a href> tags found

    word_count: int = 0              # rough content word count

    crawled_at: str = ""

    error: str = ""

    child_urls: list = field(default_factory=list, repr=False)


# ──────────────────────────────────────────────

# Core Crawler

# ──────────────────────────────────────────────

class WebCrawler:

    """

    Generic web crawler that maps a site's node structure and link volumes.

    Parameters

    ----------

    seed_url   : The starting URL (must include scheme, e.g. https://).

    max_depth  : How many hops from the seed to follow (default 2).

    max_pages  : Hard cap on total pages crawled (default 200).

    delay      : Seconds to wait between requests (default 0.5).

    workers    : Concurrent threads for fetching (default 5).

    timeout    : HTTP request timeout in seconds (default 10).

    output     : CSV filename to write results to.

    """

    def __init__(

        self,

        seed_url: str,

        max_depth: int = 2,

        max_pages: int = 200,

        delay: float = 0.5,

        workers: int = 5,

        timeout: int = 10,

        output: str = "crawl_results.csv",

    ):

        parsed = urlparse(seed_url)

        if not parsed.scheme or not parsed.netloc:

            raise ValueError(f"Invalid URL: {seed_url!r}. Include scheme e.g. https://")

        self.seed_url = seed_url.rstrip("/")

        self.base_domain = parsed.netloc

        self.max_depth = max_depth

        self.max_pages = max_pages

        self.delay = delay

        self.workers = workers

        self.timeout = timeout

        self.output = output

        self.visited: set[str] = set()

        self.nodes: list[PageNode] = []

        self.session = requests.Session()

        self.session.headers.update(DEFAULT_HEADERS)

    # ── Helpers ──────────────────────────────

    def _normalize(self, url: str) -> str:

        """Strip fragments and trailing slashes for deduplication."""

        parsed = urlparse(url)

        clean = parsed._replace(fragment="").geturl()

        return clean.rstrip("/")

    def _is_internal(self, url: str) -> bool:

        return urlparse(url).netloc == self.base_domain

    def _is_crawlable(self, url: str) -> bool:

        """Skip non-HTML resource extensions."""

        skip_exts = {

            ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",

            ".mp4", ".mp3", ".zip", ".tar", ".gz", ".exe", ".dmg",

            ".css", ".js", ".woff", ".woff2", ".ttf", ".ico",

        }

        path = urlparse(url).path.lower()

        return not any(path.endswith(ext) for ext in skip_exts)

    # ── Fetch & Parse ─────────────────────────

    def _fetch(self, url: str, parent: str, depth: int) -> PageNode:

        """Fetch a single URL and extract node data."""

        node = PageNode(

            url=url,

            parent_url=parent,

            depth=depth,

            crawled_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),

        )

        try:

            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)

            node.status_code = resp.status_code

            if resp.status_code != 200:

                node.error = f"HTTP {resp.status_code}"

                return node

            content_type = resp.headers.get("Content-Type", "")

            if "text/html" not in content_type:

                node.error = f"Skipped: content-type={content_type}"

                return node

            soup = BeautifulSoup(resp.text, "lxml")

            # Page title

            title_tag = soup.find("title")

            node.page_title = title_tag.get_text(strip=True) if title_tag else ""

            # Word count (body text only)

            body = soup.find("body")

            if body:

                node.word_count = len(body.get_text(separator=" ").split())

            # Link analysis

            all_anchors = soup.find_all("a", href=True)

            node.total_links = len(all_anchors)

            for a in all_anchors:

                href = a["href"].strip()

                if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):

                    continue

                abs_url = self._normalize(urljoin(url, href))

                if not abs_url.startswith("http"):

                    continue

                if self._is_internal(abs_url):

                    node.internal_links += 1

                    if self._is_crawlable(abs_url):

                        node.child_urls.append(abs_url)

                else:

                    node.external_links += 1

        except requests.exceptions.Timeout:

            node.error = "Timeout"

        except requests.exceptions.ConnectionError as e:

            node.error = f"ConnectionError: {e}"

        except Exception as e:

            node.error = f"Error: {e}"

        return node

    # ── BFS Crawl ─────────────────────────────

    def crawl(self) -> list[PageNode]:

        """

        BFS crawl starting from seed_url.

        Returns the list of all crawled PageNode objects.

        """
log.info(f"Starting crawl → {self.seed_url}")
log.info(f"Settings: max_depth={self.max_depth}, max_pages={self.max_pages}, "

                 f"workers={self.workers}, delay={self.delay}s")

        # Queue entries: (url, parent_url, depth)

        queue: deque[tuple[str, str, int]] = deque()

        queue.append((self.seed_url, "", 0))

        self.visited.add(self.seed_url)

        while queue and len(self.nodes) < self.max_pages:

            # Build a batch of up to `workers` URLs from the same depth level

            batch: list[tuple[str, str, int]] = []

            while queue and len(batch) < self.workers:

                item = queue.popleft()

                if len(self.nodes) + len(batch) >= self.max_pages:

                    break

                batch.append(item)

            if not batch:

                break

            # Fetch batch concurrently

            with ThreadPoolExecutor(max_workers=self.workers) as pool:

                futures = {

                    pool.submit(self._fetch, url, parent, depth): (url, parent, depth)

                    for url, parent, depth in batch

                }

                for future in as_completed(futures):

                    node = future.result()

                    self.nodes.append(node)
log.info(

                        f"[{len(self.nodes):>4}] depth={node.depth} "

                        f"links={node.internal_links}in/{node.external_links}out "

                        f"→ {node.url[:80]}"

                    )

                    # Enqueue children if within depth limit

                    if node.depth < self.max_depth:

                        for child_url in node.child_urls:

                            if child_url not in self.visited and len(self.visited) < self.max_pages * 2:

                                self.visited.add(child_url)

                                queue.append((child_url, node.url, node.depth + 1))

            if self.delay > 0:

                time.sleep(self.delay)
log.info(f"Crawl complete. {len(self.nodes)} pages visited.")

        return self.nodes

    # ── CSV Export ────────────────────────────

    def export_csv(self, filepath: Optional[str] = None) -> str:

        """Write all crawled nodes to a CSV file. Returns the file path."""

        out = filepath or self.output

        fieldnames = [

            "url",

            "parent_url",

            "depth",

            "status_code",

            "page_title",

            "internal_links",

            "external_links",

            "total_links",

            "word_count",

            "crawled_at",

            "error",

        ]

        with open(out, "w", newline="", encoding="utf-8") as f:

            writer = csv.DictWriter(f, fieldnames=fieldnames)

            writer.writeheader()

            for node in self.nodes:

                writer.writerow({k: getattr(node, k) for k in fieldnames})
log.info(f"CSV saved → {out}")

        return out

    # ── Summary ───────────────────────────────

    def print_summary(self):

        """Print a quick summary table to the terminal."""

        total = len(self.nodes)

        ok = sum(1 for n in self.nodes if n.status_code == 200)

        errors = sum(1 for n in self.nodes if n.error)

        total_internal = sum(n.internal_links for n in self.nodes)

        total_external = sum(n.external_links for n in self.nodes)

        print("\n" + "═" * 60)

        print(f"  CRAWL SUMMARY — {self.seed_url}")

        print("═" * 60)

        print(f"  Pages crawled     : {total}")

        print(f"  Successful (200)  : {ok}")

        print(f"  Errors / skipped  : {errors}")

        print(f"  Total internal Δ  : {total_internal}")

        print(f"  Total external Δ  : {total_external}")

        print("═" * 60)

        # Top 10 pages by internal link count

        top = sorted(self.nodes, key=lambda n: n.internal_links, reverse=True)[:10]

        print("\n  TOP PAGES BY INTERNAL LINKS")

        print(f"  {'Links':>6}  URL")

        print("  " + "─" * 56)

        for n in top:

            print(f"  {n.internal_links:>6}  {n.url[:70]}")

        print()


# ──────────────────────────────────────────────

# CLI Entry Point

# ──────────────────────────────────────────────

def main():

    parser = argparse.ArgumentParser(

        description="Web Crawler Framework — maps node-level URLs and link volumes to CSV.",

        formatter_class=argparse.ArgumentDefaultsHelpFormatter,

    )

    parser.add_argument("--url",      required=True,  help="Seed URL to start crawling (include https://)")

    parser.add_argument("--depth",    type=int,   default=2,    help="Max crawl depth from seed")

    parser.add_argument("--pages",    type=int,   default=200,  help="Max total pages to crawl")

    parser.add_argument("--delay",    type=float, default=0.5,  help="Seconds between request batches")

    parser.add_argument("--workers",  type=int,   default=5,    help="Concurrent fetch threads")

    parser.add_argument("--timeout",  type=int,   default=10,   help="HTTP timeout per request (seconds)")

    parser.add_argument("--output",   default="crawl_results.csv", help="Output CSV filename")

    args = parser.parse_args()

    crawler = WebCrawler(

        seed_url=args.url,

        max_depth=args.depth,

        max_pages=args.pages,

        delay=args.delay,

        workers=args.workers,

        timeout=args.timeout,

        output=args.output,

    )

    crawler.crawl()

    crawler.export_csv()

    crawler.print_summary()


if __name__ == "__main__":

    main()
Example Domain
 
