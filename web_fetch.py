"""Fetch one public web page that a person asked to add as a source.

This makes a request from the server on someone's behalf, so it is built defensively:
- http and https only, on the standard ports, no credentials in the address;
- the host is resolved here and every address must be a public one (no loopback, private,
  link-local, cloud-metadata or other reserved ranges), then the connection goes to that
  exact address, so a name that changes its answer afterwards cannot reach inside;
- redirects are followed by hand, at most five, and every hop goes through the same checks;
- no compression is requested, the body is capped, and the whole fetch has a deadline;
- only readable document types are accepted.
It makes one request per call and never crawls.
"""
import http.client
import ipaddress
import re
import socket
import ssl
import time
import urllib.parse
from datetime import datetime, timezone
from html import unescape

MAX_BYTES = 3 * 1024 * 1024
MAX_REDIRECTS = 5
DEADLINE_SECONDS = 20
ALLOWED_PORTS = {80, 443}
USER_AGENT = "SeedReflections-Reader/1.0 (one page, requested by the account owner)"
TYPES = {"text/html": ".html", "application/xhtml+xml": ".html", "text/plain": ".txt", "text/markdown": ".md", "application/pdf": ".pdf"}


class FetchError(ValueError):
    """A reason, safe to show to the person, why the page could not be added."""


def _is_public(address):
    ip = ipaddress.ip_address(address)
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def _resolve(host, port, allow_private):
    try:
        found = {item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
    except socket.gaierror:
        raise FetchError("That address could not be found.")
    if not found:
        raise FetchError("That address could not be found.")
    if not allow_private and not all(_is_public(address) for address in found):
        raise FetchError("That address points to a private or internal network, so it cannot be added.")
    return sorted(found)[0]


def _parse(url):
    parsed = urllib.parse.urlsplit(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise FetchError("Enter a full web address starting with http:// or https://")
    if parsed.username or parsed.password:
        raise FetchError("Addresses that contain a username or password are not accepted.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed, port


class _Pinned(http.client.HTTPConnection):
    """Connects to an address that was already checked, while still presenting the real host name."""
    def __init__(self, host, port, ip, secure, timeout):
        super().__init__(host, port, timeout=timeout)
        self._ip, self._secure = ip, secure

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host) if self._secure else sock


def _once(parsed, port, ip, timeout):
    connection = _Pinned(parsed.hostname, port, ip, parsed.scheme == "https", timeout)
    path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
    try:
        connection.request("GET", path, headers={"Host": parsed.netloc.rsplit("@", 1)[-1], "User-Agent": USER_AGENT,
                           "Accept": "text/html,text/plain,application/pdf;q=0.9,*/*;q=0.1", "Accept-Encoding": "identity", "Connection": "close"})
        response = connection.getresponse()
        if response.status in {301, 302, 303, 307, 308}:
            return response.status, response.getheader("Location"), None, None
        if response.status != 200:
            raise FetchError(f"The site answered with an error ({response.status}), so the page was not added.")
        kind = (response.getheader("Content-Type") or "").split(";")[0].strip().lower()
        if kind not in TYPES:
            raise FetchError("That page is not a readable document type (it must be a web page, text or PDF).")
        declared = response.getheader("Content-Length")
        if declared and declared.isdigit() and int(declared) > MAX_BYTES:
            raise FetchError("That page is too large to add (the limit is 3 MB).")
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise FetchError("That page is too large to add (the limit is 3 MB).")
        return 200, kind, body, response.getheader("Content-Type") or ""
    except FetchError:
        raise
    except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
        raise FetchError("The page could not be reached" + (" securely." if isinstance(exc, ssl.SSLError) else ".")) from None
    finally:
        connection.close()


def _title(body, kind):
    if kind not in {"text/html", "application/xhtml+xml"}:
        return None
    match = re.search(rb"<title[^>]*>(.*?)</title>", body[:200000], re.I | re.S)
    return re.sub(r"\s+", " ", unescape(match.group(1).decode("utf-8", "replace"))).strip()[:200] if match else None


def fetch_page(url, allow_private=False):
    """Return {url, final_url, title, kind, body, retrieved_at}. Raises FetchError with a person-readable reason."""
    deadline = time.monotonic() + DEADLINE_SECONDS
    current = str(url or "").strip()
    for _ in range(MAX_REDIRECTS + 1):
        parsed, port = _parse(current)
        if not allow_private and port not in ALLOWED_PORTS:
            raise FetchError("Only standard web ports (80 and 443) are accepted.")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FetchError("The page took too long to load.")
        ip = _resolve(parsed.hostname, port, allow_private)
        status, first, body, _ = _once(parsed, port, ip, min(10, remaining))
        if status == 200:
            return {"url": str(url).strip(), "final_url": current, "title": _title(body, first), "kind": first, "body": body,
                    "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
        if not first:
            raise FetchError("The site redirected without saying where.")
        current = urllib.parse.urljoin(current, first)
    raise FetchError("The address redirected too many times.")


def as_document(page):
    """Name and bytes to hand to the normal document import, with the address and retrieval time kept in the text."""
    host = urllib.parse.urlsplit(page["final_url"]).hostname or "web"
    slug = re.sub(r"[^a-z0-9]+", "-", (page["title"] or urllib.parse.urlsplit(page["final_url"]).path or "page").lower()).strip("-")[:50] or "page"
    if page["kind"] == "application/pdf":
        return f"web-{host}-{slug}.pdf", page["body"]
    from document_ingest import extract_document
    extension = TYPES[page["kind"]]
    text = extract_document(page["body"], "page" + extension)["text"].strip()
    head = f"# {page['title'] or host}\n\nSource: {page['final_url']}\nRetrieved: {page['retrieved_at']}\n\n"
    return f"web-{host}-{slug}.md", (head + text + "\n").encode("utf-8")
