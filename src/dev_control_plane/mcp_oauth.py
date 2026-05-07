"""OAuth helpers for the hosted dev-control-plane MCP endpoint.

This module implements the bounded OAuth pieces needed by ChatGPT Developer
Mode without becoming a general identity provider. It stores only hashes of
authorization codes and access tokens in the runtime state directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import time
from typing import Any, Mapping
from urllib.parse import parse_qs, urlencode, urlparse

MCP_WRITE_SCOPE = "dcp.write"
AUTH_CODE_TTL_SECONDS = 300
ACCESS_TOKEN_TTL_SECONDS = 3600
OAUTH_CLIENTS_COLLECTION = "mcp_oauth_clients"
OAUTH_CODES_COLLECTION = "mcp_oauth_codes"
OAUTH_TOKENS_COLLECTION = "mcp_oauth_tokens"


@dataclass(frozen=True)
class OAuthTokenVerification:
    active: bool
    auth_type: str | None = None
    client_id: str | None = None
    scopes: tuple[str, ...] = ()
    resource: str | None = None
    blocker: str | None = None


class MCPOAuthProvider:
    def __init__(self, store: Any) -> None:
        self.store = store

    def status(self, base_url: str) -> dict[str, Any]:
        clients = self._read_collection(OAUTH_CLIENTS_COLLECTION)
        tokens = self._read_collection(OAUTH_TOKENS_COLLECTION)
        return {
            "enabled": True,
            "auth_mode": "oauth2_authorization_code_pkce",
            "issuer": base_url,
            "authorize_url": f"{base_url}/oauth/authorize",
            "exchange_url": f"{base_url}/oauth/token",
            "register_url": f"{base_url}/oauth/register",
            "resource_metadata_url": f"{base_url}/.well-known/oauth-protected-resource/mcp",
            "scopes_supported": [MCP_WRITE_SCOPE],
            "dynamic_client_registration": True,
            "client_type": "public_pkce",
            "authorize_user_gate": "reverse_proxy_basic_auth",
            "registered_clients_count": len(clients),
            "active_grants_count": len([item for item in tokens.values() if not _expired(item)]),
        }

    def protected_resource_metadata(self, base_url: str) -> dict[str, Any]:
        return {
            "resource": self.resource_uri(base_url),
            "authorization_servers": [base_url],
            "bearer_methods_supported": ["header"],
            "scopes_supported": [MCP_WRITE_SCOPE],
            "resource_name": "dev-control-plane MCP",
        }

    def authorization_server_metadata(self, base_url: str) -> dict[str, Any]:
        return {
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/oauth/authorize",
            "token_endpoint": f"{base_url}/oauth/token",
            "registration_endpoint": f"{base_url}/oauth/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": [MCP_WRITE_SCOPE],
            "client_id_metadata_document_supported": False,
            "service_documentation": f"{base_url}/mcp",
        }

    def register_client(self, payload: Mapping[str, Any], base_url: str) -> dict[str, Any]:
        redirect_uris = payload.get("redirect_uris")
        if not isinstance(redirect_uris, list) or not redirect_uris:
            raise OAuthError("redirect_uris is required")
        redirects = [_validated_redirect_uri(str(uri or "")) for uri in redirect_uris]
        client_id = f"dcp-client-{secrets.token_urlsafe(24)}"
        now = _now_utc()
        clients = self._read_collection(OAUTH_CLIENTS_COLLECTION)
        clients[client_id] = {
            "client_id": client_id,
            "client_name": _safe_text(payload.get("client_name") or "ChatGPT MCP client", 160),
            "redirect_uris": redirects,
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
            "scope": MCP_WRITE_SCOPE,
            "created_at": now,
        }
        self._write_collection(OAUTH_CLIENTS_COLLECTION, clients)
        return {
            "client_id": client_id,
            "client_id_issued_at": int(time.time()),
            "client_name": clients[client_id]["client_name"],
            "redirect_uris": redirects,
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
            "scope": MCP_WRITE_SCOPE,
        }

    def authorize_page(self, query: Mapping[str, list[str]], base_url: str) -> str:
        request = self._validated_authorization_request(_first_values(query), base_url)
        return _authorization_html(request)

    def approve_authorization(self, form: Mapping[str, str], base_url: str) -> str:
        request = self._validated_authorization_request(form, base_url)
        code = f"dcp-code-{secrets.token_urlsafe(32)}"
        codes = self._read_collection(OAUTH_CODES_COLLECTION)
        codes[_sha256(code)] = {
            "client_id": request["client_id"],
            "redirect_uri": request["redirect_uri"],
            "scope": request["scope"],
            "resource": request["resource"],
            "code_challenge": request["code_challenge"],
            "code_challenge_method": "S256",
            "created_at": _now_utc(),
            "expires_at_epoch": time.time() + AUTH_CODE_TTL_SECONDS,
            "used": False,
        }
        self._write_collection(OAUTH_CODES_COLLECTION, codes)
        params = {"code": code}
        if request.get("state"):
            params["state"] = str(request["state"])
        separator = "&" if "?" in request["redirect_uri"] else "?"
        return f"{request['redirect_uri']}{separator}{urlencode(params)}"

    def exchange_token(self, payload: Mapping[str, Any], base_url: str) -> dict[str, Any]:
        grant_type = str(payload.get("grant_type") or "")
        if grant_type != "authorization_code":
            raise OAuthError("unsupported grant_type")
        code = str(payload.get("code") or "").strip()
        code_verifier = str(payload.get("code_verifier") or "").strip()
        client_id = str(payload.get("client_id") or "").strip()
        redirect_uri = str(payload.get("redirect_uri") or "").strip()
        if not code or not code_verifier or not client_id or not redirect_uri:
            raise OAuthError("code, code_verifier, client_id and redirect_uri are required")
        clients = self._read_collection(OAUTH_CLIENTS_COLLECTION)
        client = clients.get(client_id)
        if not isinstance(client, Mapping):
            raise OAuthError("unknown client_id")
        codes = self._read_collection(OAUTH_CODES_COLLECTION)
        code_hash = _sha256(code)
        stored = codes.get(code_hash)
        if not isinstance(stored, Mapping):
            raise OAuthError("invalid authorization code")
        if stored.get("used") is True or _expired(stored):
            raise OAuthError("expired authorization code")
        if stored.get("client_id") != client_id or stored.get("redirect_uri") != redirect_uri:
            raise OAuthError("authorization code binding mismatch")
        if not _verify_pkce(str(stored.get("code_challenge") or ""), code_verifier):
            raise OAuthError("PKCE verification failed")
        requested_resource = str(payload.get("resource") or stored.get("resource") or "").strip()
        if requested_resource and requested_resource != stored.get("resource"):
            raise OAuthError("resource binding mismatch")

        access_token = f"dcp-access-{secrets.token_urlsafe(48)}"
        tokens = self._read_collection(OAUTH_TOKENS_COLLECTION)
        tokens[_sha256(access_token)] = {
            "client_id": client_id,
            "scope": stored.get("scope") or MCP_WRITE_SCOPE,
            "resource": stored.get("resource") or self.resource_uri(base_url),
            "created_at": _now_utc(),
            "expires_at_epoch": time.time() + ACCESS_TOKEN_TTL_SECONDS,
        }
        codes[code_hash] = {**dict(stored), "used": True, "used_at": _now_utc()}
        self._write_collection(OAUTH_CODES_COLLECTION, codes)
        self._write_collection(OAUTH_TOKENS_COLLECTION, tokens)
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": ACCESS_TOKEN_TTL_SECONDS,
            "scope": stored.get("scope") or MCP_WRITE_SCOPE,
        }

    def verify_access_token(self, token: str, *, base_url: str | None = None) -> OAuthTokenVerification:
        token = str(token or "").strip()
        if not token:
            return OAuthTokenVerification(active=False, blocker="missing token")
        tokens = self._read_collection(OAUTH_TOKENS_COLLECTION)
        stored = tokens.get(_sha256(token))
        if not isinstance(stored, Mapping):
            return OAuthTokenVerification(active=False, blocker="unknown token")
        if _expired(stored):
            return OAuthTokenVerification(active=False, blocker="expired token")
        scopes = tuple(str(stored.get("scope") or "").split())
        if MCP_WRITE_SCOPE not in scopes:
            return OAuthTokenVerification(active=False, blocker="missing write scope")
        if base_url:
            expected = self.resource_uri(base_url)
            resource = str(stored.get("resource") or "")
            if resource and resource != expected:
                return OAuthTokenVerification(active=False, blocker="resource mismatch")
        return OAuthTokenVerification(
            active=True,
            auth_type="oauth2",
            client_id=str(stored.get("client_id") or ""),
            scopes=scopes,
            resource=str(stored.get("resource") or ""),
        )

    def www_authenticate(self, base_url: str) -> str:
        return (
            'Bearer resource_metadata="'
            f'{base_url}/.well-known/oauth-protected-resource/mcp", scope="{MCP_WRITE_SCOPE}"'
        )

    def resource_uri(self, base_url: str) -> str:
        return f"{base_url}/mcp"

    def _validated_authorization_request(self, params: Mapping[str, Any], base_url: str) -> dict[str, str]:
        response_type = str(params.get("response_type") or "")
        client_id = str(params.get("client_id") or "").strip()
        redirect_uri = str(params.get("redirect_uri") or "").strip()
        code_challenge = str(params.get("code_challenge") or "").strip()
        method = str(params.get("code_challenge_method") or "").strip()
        scope = str(params.get("scope") or MCP_WRITE_SCOPE).strip() or MCP_WRITE_SCOPE
        state = str(params.get("state") or "")
        resource = str(params.get("resource") or self.resource_uri(base_url)).strip()
        if response_type != "code":
            raise OAuthError("response_type must be code")
        clients = self._read_collection(OAUTH_CLIENTS_COLLECTION)
        client = clients.get(client_id)
        if not isinstance(client, Mapping):
            raise OAuthError("unknown client_id")
        if redirect_uri not in client.get("redirect_uris", []):
            raise OAuthError("redirect_uri is not registered for this client")
        if not code_challenge or method != "S256":
            raise OAuthError("PKCE S256 code_challenge is required")
        if MCP_WRITE_SCOPE not in scope.split():
            raise OAuthError(f"{MCP_WRITE_SCOPE} scope is required for write tools")
        if resource != self.resource_uri(base_url):
            raise OAuthError("resource must match the MCP endpoint")
        return {
            "response_type": response_type,
            "client_id": client_id,
            "client_name": str(client.get("client_name") or "ChatGPT MCP client"),
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
            "resource": resource,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

    def _read_collection(self, name: str) -> dict[str, Any]:
        if hasattr(self.store, "_read_collection"):
            return dict(self.store._read_collection(name))
        path = _collection_path(self.store.state_dir, name)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_collection(self, name: str, payload: Mapping[str, Any]) -> None:
        if hasattr(self.store, "_write_collection"):
            self.store._write_collection(name, payload)
            return
        path = _collection_path(self.store.state_dir, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class OAuthError(ValueError):
    pass


def parse_form_urlencoded(raw: bytes) -> dict[str, str]:
    parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
    return _first_values(parsed)


def external_base_url(headers: Mapping[str, str], *, default_scheme: str = "http") -> str:
    proto = _header(headers, "X-Forwarded-Proto") or default_scheme
    host = _header(headers, "Host") or "127.0.0.1"
    return f"{proto}://{host}".rstrip("/")


def bearer_token_from_header(authorization: str | None) -> str | None:
    value = str(authorization or "").strip()
    prefix = "Bearer "
    if not value.lower().startswith(prefix.lower()):
        return None
    token = value[len(prefix) :].strip()
    return token or None


def _authorization_html(request: Mapping[str, str]) -> str:
    hidden = "\n".join(
        f'<input type="hidden" name="{_html_escape(key)}" value="{_html_escape(value)}">'
        for key, value in request.items()
        if key != "client_name"
    )
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>Authorize dev-control-plane MCP</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:760px;margin:48px auto;padding:0 20px;line-height:1.45}"
        "button{font:inherit;padding:10px 14px}code{background:#eee;padding:2px 4px}</style></head><body>"
        "<h1>Authorize dev-control-plane MCP</h1>"
        f"<p>Client: <strong>{_html_escape(request.get('client_name') or 'ChatGPT MCP client')}</strong></p>"
        f"<p>Scope: <code>{_html_escape(request.get('scope') or MCP_WRITE_SCOPE)}</code></p>"
        "<p>This authorizes write-capable MCP tools. ChatGPT will still ask for confirmation before write actions.</p>"
        "<form method=\"post\" action=\"/oauth/authorize\">"
        f"{hidden}<button type=\"submit\">Authorize write tools</button></form>"
        "</body></html>"
    )


def _validated_redirect_uri(uri: str) -> str:
    parsed = urlparse(uri)
    if parsed.scheme == "https" and parsed.netloc:
        return uri
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}:
        return uri
    raise OAuthError("redirect_uris must be HTTPS, localhost, or 127.0.0.1")


def _verify_pkce(challenge: str, verifier: str) -> bool:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return hmac.compare_digest(challenge, expected)


def _expired(record: Mapping[str, Any]) -> bool:
    expiry = float(record.get("expires_at_epoch") or 0)
    return bool(expiry and expiry < time.time())


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _collection_path(state_dir: Path, name: str) -> Path:
    return Path(state_dir).resolve() / "collections" / f"{name}.json"


def _first_values(values: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in values.items():
        if isinstance(value, list):
            result[str(key)] = str(value[0] if value else "")
        else:
            result[str(key)] = str(value)
    return result


def _header(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if str(key).lower() == lowered:
            return str(value)
    return None


def _safe_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 15] + "...[truncated]"


def _html_escape(value: Any) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
