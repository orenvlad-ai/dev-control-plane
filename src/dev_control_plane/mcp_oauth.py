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

MCP_CONNECTION_CONTRACT_VERSION = "mcp_connection_v1"
MCP_PUBLIC_URL = "https://devcontrol.pro"
MCP_ENDPOINT_PATH = "/mcp"
MCP_AUTH_MODE = "oauth2_authorization_code_pkce"
MCP_WRITE_SCOPE = "dcp.write"
MCP_OFFLINE_SCOPE = "offline_access"
AUTH_CODE_TTL_SECONDS = 300
ACCESS_TOKEN_TTL_SECONDS = 3600
REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60
EXPIRED_GRANT_DIAGNOSTIC_RETENTION_SECONDS = 7 * 24 * 60 * 60
REGISTERED_CLIENT_RETENTION_SECONDS = 90 * 24 * 60 * 60
OAUTH_CLIENTS_COLLECTION = "mcp_oauth_clients"
OAUTH_CODES_COLLECTION = "mcp_oauth_codes"
OAUTH_TOKENS_COLLECTION = "mcp_oauth_tokens"
OAUTH_REFRESH_TOKENS_COLLECTION = "mcp_oauth_refresh_tokens"


@dataclass(frozen=True)
class OAuthTokenVerification:
    active: bool
    auth_type: str | None = None
    client_id: str | None = None
    scopes: tuple[str, ...] = ()
    resource: str | None = None
    blocker: str | None = None
    reason_code: str | None = None


class MCPOAuthProvider:
    def __init__(self, store: Any) -> None:
        self.store = store

    def status(self, base_url: str) -> dict[str, Any]:
        cleanup = self.cleanup_expired()
        clients = self._read_collection(OAUTH_CLIENTS_COLLECTION)
        tokens = self._read_collection(OAUTH_TOKENS_COLLECTION)
        codes = self._read_collection(OAUTH_CODES_COLLECTION)
        refresh_tokens = self._read_collection(OAUTH_REFRESH_TOKENS_COLLECTION)
        active_grants = len([item for item in tokens.values() if not _expired(item) and item.get("revoked") is not True])
        pending_codes = len([item for item in codes.values() if not _expired(item) and item.get("used") is not True])
        expired_grants = max(0, len(tokens) - active_grants)
        active_refresh_tokens = len(
            [
                item
                for item in refresh_tokens.values()
                if isinstance(item, Mapping) and item.get("status") == "active" and not _expired(item)
            ]
        )
        expired_refresh_tokens = len(
            [
                item
                for item in refresh_tokens.values()
                if isinstance(item, Mapping) and item.get("status") == "active" and _expired(item)
            ]
        )
        revoked_refresh_tokens = len(
            [
                item
                for item in refresh_tokens.values()
                if isinstance(item, Mapping) and item.get("status") in {"revoked", "reuse_detected", "family_revoked"}
            ]
        )
        return {
            "enabled": True,
            "connection_contract_version": MCP_CONNECTION_CONTRACT_VERSION,
            "auth_mode": MCP_AUTH_MODE,
            "issuer": base_url,
            "resource": self.resource_uri(base_url),
            "authorize_url": f"{base_url}/oauth/authorize",
            "exchange_url": f"{base_url}/oauth/token",
            "register_url": f"{base_url}/oauth/register",
            "resource_metadata_url": f"{base_url}/.well-known/oauth-protected-resource/mcp",
            "scopes_supported": [MCP_WRITE_SCOPE, MCP_OFFLINE_SCOPE],
            "dynamic_client_registration": True,
            "client_type": "public_pkce",
            "authorize_user_gate": "reverse_proxy_basic_auth",
            "storage": {
                "mode": "durable_state_collection",
                "clients_collection": OAUTH_CLIENTS_COLLECTION,
                "codes_collection": OAUTH_CODES_COLLECTION,
                "grants_collection": OAUTH_TOKENS_COLLECTION,
                "refresh_tokens_collection": OAUTH_REFRESH_TOKENS_COLLECTION,
                "restart_survives": True,
                "stores_hashes_only": True,
            },
            "registered_clients_count": len(clients),
            "pending_codes_count": pending_codes,
            "active_grants_count": active_grants,
            "expired_grants_count": expired_grants,
            "active_refresh_tokens_count": active_refresh_tokens,
            "expired_refresh_tokens_count": expired_refresh_tokens,
            "revoked_refresh_tokens_count": revoked_refresh_tokens,
            "access_grant_ttl_seconds": ACCESS_TOKEN_TTL_SECONDS,
            "auth_code_ttl_seconds": AUTH_CODE_TTL_SECONDS,
            "refresh_token_ttl_seconds": REFRESH_TOKEN_TTL_SECONDS,
            "expired_grant_diagnostic_retention_seconds": EXPIRED_GRANT_DIAGNOSTIC_RETENTION_SECONDS,
            "registered_client_retention_seconds": REGISTERED_CLIENT_RETENTION_SECONDS,
            "cleanup": cleanup,
            "cleanup_policy": {
                "expired_codes": "removed on status/register/authorize/token exchange",
                "used_codes": "removed after successful token exchange",
                "expired_grants": "retained briefly for token_expired diagnostics, then removed",
                "expired_refresh_tokens": "retained briefly for refresh diagnostics, then removed",
                "registered_clients": "stale clients without live code/grant references are removed after retention",
            },
            "refresh_supported": True,
            "refresh_tokens_supported": True,
            "offline_access_supported": True,
            "refresh_token_rotation": True,
            "refresh_token_reuse_revokes_family": True,
            "token_expired_requires_reconnect": False,
            "known_gap": None,
            "auth_failure_diagnostics": {
                "sanitized": True,
                "supported_reason_codes": [
                    "unauthenticated_call",
                    "unsupported_authorization_scheme",
                    "client_or_grant_not_found",
                    "token_expired",
                    "write_scope_missing",
                    "invalid_resource_metadata",
                    "refresh_token_expired",
                    "refresh_token_revoked",
                    "refresh_token_reuse_detected",
                    "offline_access_not_requested",
                ],
                "external_connector_cache_limitation": (
                    "DevControl can report stable OAuth/resource/grant diagnostics, but ChatGPT connector link-cache "
                    "404/reconnect behavior is external to DevControl."
                ),
                "token_expired_reconnect_required": False,
            },
        }

    def protected_resource_metadata(self, base_url: str) -> dict[str, Any]:
        return {
            "resource": self.resource_uri(base_url),
            "authorization_servers": [base_url],
            "bearer_methods_supported": ["header"],
            "scopes_supported": [MCP_WRITE_SCOPE, MCP_OFFLINE_SCOPE],
            "resource_name": "dev-control-plane MCP",
        }

    def authorization_server_metadata(self, base_url: str) -> dict[str, Any]:
        return {
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/oauth/authorize",
            "token_endpoint": f"{base_url}/oauth/token",
            "registration_endpoint": f"{base_url}/oauth/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": [MCP_WRITE_SCOPE, MCP_OFFLINE_SCOPE],
            "client_id_metadata_document_supported": False,
            "service_documentation": f"{base_url}/mcp",
        }

    def register_client(self, payload: Mapping[str, Any], base_url: str) -> dict[str, Any]:
        self.cleanup_expired()
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
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "scope": f"{MCP_WRITE_SCOPE} {MCP_OFFLINE_SCOPE}",
            "created_at": now,
        }
        self._write_collection(OAUTH_CLIENTS_COLLECTION, clients)
        return {
            "client_id": client_id,
            "client_id_issued_at": int(time.time()),
            "client_name": clients[client_id]["client_name"],
            "redirect_uris": redirects,
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "scope": f"{MCP_WRITE_SCOPE} {MCP_OFFLINE_SCOPE}",
        }

    def authorize_page(self, query: Mapping[str, list[str]], base_url: str) -> str:
        self.cleanup_expired()
        request = self._validated_authorization_request(_first_values(query), base_url)
        return _authorization_html(request)

    def approve_authorization(self, form: Mapping[str, str], base_url: str) -> str:
        self.cleanup_expired()
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
        self.cleanup_expired()
        grant_type = str(payload.get("grant_type") or "")
        if grant_type == "refresh_token":
            return self._exchange_refresh_token(payload, base_url)
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

        family_id = f"dcp-family-{secrets.token_urlsafe(18)}"
        access_token = f"dcp-access-{secrets.token_urlsafe(48)}"
        tokens = self._read_collection(OAUTH_TOKENS_COLLECTION)
        tokens[_sha256(access_token)] = {
            "client_id": client_id,
            "scope": stored.get("scope") or MCP_WRITE_SCOPE,
            "resource": stored.get("resource") or self.resource_uri(base_url),
            "refresh_family_id": family_id,
            "created_at": _now_utc(),
            "expires_at_epoch": time.time() + ACCESS_TOKEN_TTL_SECONDS,
        }
        response = {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": ACCESS_TOKEN_TTL_SECONDS,
            "scope": stored.get("scope") or MCP_WRITE_SCOPE,
        }
        if MCP_OFFLINE_SCOPE in _scope_tokens(str(stored.get("scope") or "")):
            refresh_token = f"dcp-refresh-{secrets.token_urlsafe(64)}"
            refresh_tokens = self._read_collection(OAUTH_REFRESH_TOKENS_COLLECTION)
            refresh_tokens[_sha256(refresh_token)] = {
                "client_id": client_id,
                "scope": stored.get("scope") or f"{MCP_WRITE_SCOPE} {MCP_OFFLINE_SCOPE}",
                "resource": stored.get("resource") or self.resource_uri(base_url),
                "refresh_family_id": family_id,
                "status": "active",
                "created_at": _now_utc(),
                "expires_at_epoch": time.time() + REFRESH_TOKEN_TTL_SECONDS,
            }
            self._write_collection(OAUTH_REFRESH_TOKENS_COLLECTION, refresh_tokens)
            response["refresh_token"] = refresh_token
            response["refresh_token_expires_in"] = REFRESH_TOKEN_TTL_SECONDS
        codes.pop(code_hash, None)
        self._write_collection(OAUTH_CODES_COLLECTION, codes)
        self._write_collection(OAUTH_TOKENS_COLLECTION, tokens)
        return response

    def _exchange_refresh_token(self, payload: Mapping[str, Any], base_url: str) -> dict[str, Any]:
        refresh_token = str(payload.get("refresh_token") or "").strip()
        client_id = str(payload.get("client_id") or "").strip()
        if not refresh_token:
            raise OAuthError("refresh_token is required", reason_code="offline_access_not_requested")
        refresh_tokens = self._read_collection(OAUTH_REFRESH_TOKENS_COLLECTION)
        token_hash = _sha256(refresh_token)
        stored = refresh_tokens.get(token_hash)
        if not isinstance(stored, Mapping):
            raise OAuthError("refresh token not found; offline_access may not have been requested", reason_code="offline_access_not_requested")
        if client_id and stored.get("client_id") != client_id:
            raise OAuthError("refresh token client binding mismatch", reason_code="refresh_token_revoked")
        family_id = str(stored.get("refresh_family_id") or "")
        status = str(stored.get("status") or "active")
        if status != "active":
            self._revoke_refresh_family(family_id, reason="refresh_token_reuse_detected")
            raise OAuthError("refresh token reuse detected; token family revoked", reason_code="refresh_token_reuse_detected")
        if _expired(stored):
            refresh_tokens[token_hash] = {**dict(stored), "status": "revoked", "revoked_at": _now_utc(), "revoked_reason": "refresh_token_expired"}
            self._write_collection(OAUTH_REFRESH_TOKENS_COLLECTION, refresh_tokens)
            raise OAuthError("refresh token expired", reason_code="refresh_token_expired")
        scopes = _scope_tokens(str(stored.get("scope") or ""))
        if MCP_OFFLINE_SCOPE not in scopes:
            raise OAuthError("offline_access was not requested for this grant", reason_code="offline_access_not_requested")
        requested_resource = str(payload.get("resource") or stored.get("resource") or "").strip()
        if requested_resource and requested_resource != stored.get("resource"):
            raise OAuthError("resource binding mismatch", reason_code="invalid_resource_metadata")

        new_access_token = f"dcp-access-{secrets.token_urlsafe(48)}"
        new_refresh_token = f"dcp-refresh-{secrets.token_urlsafe(64)}"
        tokens = self._read_collection(OAUTH_TOKENS_COLLECTION)
        tokens[_sha256(new_access_token)] = {
            "client_id": stored.get("client_id"),
            "scope": stored.get("scope") or f"{MCP_WRITE_SCOPE} {MCP_OFFLINE_SCOPE}",
            "resource": stored.get("resource") or self.resource_uri(base_url),
            "refresh_family_id": family_id,
            "created_at": _now_utc(),
            "expires_at_epoch": time.time() + ACCESS_TOKEN_TTL_SECONDS,
        }
        refresh_tokens[token_hash] = {
            **dict(stored),
            "status": "revoked",
            "revoked_at": _now_utc(),
            "revoked_reason": "rotated",
        }
        refresh_tokens[_sha256(new_refresh_token)] = {
            "client_id": stored.get("client_id"),
            "scope": stored.get("scope") or f"{MCP_WRITE_SCOPE} {MCP_OFFLINE_SCOPE}",
            "resource": stored.get("resource") or self.resource_uri(base_url),
            "refresh_family_id": family_id,
            "status": "active",
            "created_at": _now_utc(),
            "expires_at_epoch": time.time() + REFRESH_TOKEN_TTL_SECONDS,
            "rotated_from_hash": token_hash,
        }
        self._write_collection(OAUTH_TOKENS_COLLECTION, tokens)
        self._write_collection(OAUTH_REFRESH_TOKENS_COLLECTION, refresh_tokens)
        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "Bearer",
            "expires_in": ACCESS_TOKEN_TTL_SECONDS,
            "refresh_token_expires_in": REFRESH_TOKEN_TTL_SECONDS,
            "scope": stored.get("scope") or f"{MCP_WRITE_SCOPE} {MCP_OFFLINE_SCOPE}",
        }

    def verify_access_token(self, token: str, *, base_url: str | None = None) -> OAuthTokenVerification:
        token = str(token or "").strip()
        if not token:
            return OAuthTokenVerification(active=False, blocker="missing bearer token", reason_code="unauthenticated_call")
        tokens = self._read_collection(OAUTH_TOKENS_COLLECTION)
        stored = tokens.get(_sha256(token))
        if not isinstance(stored, Mapping):
            return OAuthTokenVerification(active=False, blocker="OAuth client/grant not found for bearer token", reason_code="client_or_grant_not_found")
        if stored.get("revoked") is True:
            return OAuthTokenVerification(active=False, blocker="OAuth access token revoked", reason_code="client_or_grant_not_found")
        if _expired(stored):
            return OAuthTokenVerification(active=False, blocker="OAuth access token expired; reauthentication required", reason_code="token_expired")
        scopes = tuple(str(stored.get("scope") or "").split())
        if MCP_WRITE_SCOPE not in scopes:
            return OAuthTokenVerification(active=False, blocker="OAuth bearer token is missing dcp.write scope", reason_code="write_scope_missing")
        if base_url:
            expected = self.resource_uri(base_url)
            resource = str(stored.get("resource") or "")
            if resource and resource != expected:
                return OAuthTokenVerification(active=False, blocker="OAuth resource metadata mismatch for MCP endpoint", reason_code="invalid_resource_metadata")
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
        return f"{base_url}{MCP_ENDPOINT_PATH}"

    def cleanup_expired(self) -> dict[str, Any]:
        now = time.time()
        clients = self._read_collection(OAUTH_CLIENTS_COLLECTION)
        codes = self._read_collection(OAUTH_CODES_COLLECTION)
        tokens = self._read_collection(OAUTH_TOKENS_COLLECTION)
        refresh_tokens = self._read_collection(OAUTH_REFRESH_TOKENS_COLLECTION)

        kept_codes: dict[str, Any] = {}
        removed_codes = 0
        for key, item in codes.items():
            if isinstance(item, Mapping) and item.get("used") is not True and not _expired(item):
                kept_codes[str(key)] = item
            else:
                removed_codes += 1

        kept_tokens: dict[str, Any] = {}
        removed_grants = 0
        for key, item in tokens.items():
            if not isinstance(item, Mapping):
                removed_grants += 1
                continue
            expiry = float(item.get("expires_at_epoch") or 0)
            if expiry and expiry < now and expiry + EXPIRED_GRANT_DIAGNOSTIC_RETENTION_SECONDS < now:
                removed_grants += 1
                continue
            kept_tokens[str(key)] = item

        kept_refresh_tokens: dict[str, Any] = {}
        removed_refresh_tokens = 0
        for key, item in refresh_tokens.items():
            if not isinstance(item, Mapping):
                removed_refresh_tokens += 1
                continue
            expiry = float(item.get("expires_at_epoch") or 0)
            if expiry and expiry < now and expiry + EXPIRED_GRANT_DIAGNOSTIC_RETENTION_SECONDS < now:
                removed_refresh_tokens += 1
                continue
            kept_refresh_tokens[str(key)] = item

        referenced_clients = {
            str(item.get("client_id") or "")
            for item in list(kept_codes.values()) + list(kept_tokens.values()) + list(kept_refresh_tokens.values())
            if isinstance(item, Mapping) and item.get("client_id")
        }
        kept_clients: dict[str, Any] = {}
        removed_clients = 0
        for client_id, item in clients.items():
            text_client_id = str(client_id)
            if text_client_id in referenced_clients:
                kept_clients[text_client_id] = item
                continue
            if isinstance(item, Mapping):
                created_at_epoch = _iso_to_epoch(str(item.get("created_at") or "")) or now
                if created_at_epoch + REGISTERED_CLIENT_RETENTION_SECONDS >= now:
                    kept_clients[text_client_id] = item
                    continue
            removed_clients += 1

        if removed_codes:
            self._write_collection(OAUTH_CODES_COLLECTION, kept_codes)
        if removed_grants:
            self._write_collection(OAUTH_TOKENS_COLLECTION, kept_tokens)
        if removed_refresh_tokens:
            self._write_collection(OAUTH_REFRESH_TOKENS_COLLECTION, kept_refresh_tokens)
        if removed_clients:
            self._write_collection(OAUTH_CLIENTS_COLLECTION, kept_clients)
        return {
            "status": "ok",
            "removed_expired_codes_count": removed_codes,
            "removed_expired_grants_count": removed_grants,
            "removed_expired_refresh_tokens_count": removed_refresh_tokens,
            "removed_stale_clients_count": removed_clients,
            "expired_grants_retained_for_diagnostics": len(
                [
                    item
                    for item in kept_tokens.values()
                    if isinstance(item, Mapping) and _expired(item)
                ]
            ),
            "expired_refresh_tokens_retained_for_diagnostics": len(
                [
                    item
                    for item in kept_refresh_tokens.values()
                    if isinstance(item, Mapping) and _expired(item)
                ]
            ),
        }

    def _revoke_refresh_family(self, family_id: str, *, reason: str) -> None:
        if not family_id:
            return
        refresh_tokens = self._read_collection(OAUTH_REFRESH_TOKENS_COLLECTION)
        updated_refresh = False
        for key, item in list(refresh_tokens.items()):
            if isinstance(item, Mapping) and str(item.get("refresh_family_id") or "") == family_id:
                refresh_tokens[str(key)] = {
                    **dict(item),
                    "status": "reuse_detected" if reason == "refresh_token_reuse_detected" else "family_revoked",
                    "revoked_at": _now_utc(),
                    "revoked_reason": reason,
                }
                updated_refresh = True
        if updated_refresh:
            self._write_collection(OAUTH_REFRESH_TOKENS_COLLECTION, refresh_tokens)
        tokens = self._read_collection(OAUTH_TOKENS_COLLECTION)
        updated_tokens = False
        for key, item in list(tokens.items()):
            if isinstance(item, Mapping) and str(item.get("refresh_family_id") or "") == family_id:
                tokens[str(key)] = {**dict(item), "revoked": True, "revoked_at": _now_utc(), "revoked_reason": reason}
                updated_tokens = True
        if updated_tokens:
            self._write_collection(OAUTH_TOKENS_COLLECTION, tokens)

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
        scopes = _scope_tokens(scope)
        unsupported_scopes = scopes - {MCP_WRITE_SCOPE, MCP_OFFLINE_SCOPE}
        if unsupported_scopes:
            raise OAuthError(f"unsupported OAuth scope: {sorted(unsupported_scopes)[0]}")
        if MCP_WRITE_SCOPE not in scopes:
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
    def __init__(self, message: str, *, reason_code: str | None = None) -> None:
        super().__init__(message)
        self.reason_code = reason_code


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


def _scope_tokens(scope: str) -> set[str]:
    return {item for item in str(scope or "").split() if item}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _iso_to_epoch(value: str) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


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
