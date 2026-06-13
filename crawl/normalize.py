"""
URL normalization for T8/CCR crawling.

Fixes audit item 1: same page discovered multiple times due to casing
differences (e.g. /T8/14003.html vs /t8/14003.html).
"""

import re
from urllib.parse import urlparse, urlunparse


def normalize_url(url: str) -> str:
    """
    Normalize a URL so casing/path variants collapse to one canonical form:
      - scheme and host lowercased
      - /title8/ and /T8/ (any casing) -> /t8/
      - path lowercased
      - fragment stripped (query kept, since some leginfo URLs need it)
    """
    p = urlparse(url)

    path = p.path
    # Collapse /title8/ and any-case /t8/ variants to a single canonical /t8/
    path = re.sub(r"/title8/", "/t8/", path, flags=re.IGNORECASE)
    path = re.sub(r"/t8/", "/t8/", path, flags=re.IGNORECASE)
    path = path.lower()

    return urlunparse((
        p.scheme.lower(),
        p.netloc.lower(),
        path,
        "",          # params
        p.query,     # keep query string (leginfo URLs encode hierarchy here)
        "",          # fragment
    ))