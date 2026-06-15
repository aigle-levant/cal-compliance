import re
from urllib.parse import urlparse, urlunparse

def normalize_url(url: str) -> str:
    p = urlparse(url)
    path = p.path
    path = re.sub(r"/title8/", "/t8/", path, flags=re.IGNORECASE)
    path = re.sub(r"/t8/", "/t8/", path, flags=re.IGNORECASE)
    path = path.lower()
    return urlunparse((
        p.scheme.lower(),
        p.netloc.lower(),
        path,
        "",
        p.query,
        "",
))