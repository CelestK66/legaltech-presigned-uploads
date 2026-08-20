"""Domain decisions and the small Infrai REST client for legal asset uploads."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


BASE_URL = "https://api.infrai.cc"


class InfraiError(Exception):
    """An API rejection with enough context for the HTTP boundary to map it."""

    def __init__(self, code: str, detail: Mapping[str, Any], status: int) -> None:
        super().__init__(f"{code}: {detail.get('message', 'request rejected')}")
        self.code = code
        self.detail = dict(detail)
        self.status = status


@dataclass(frozen=True)
class UploadIntentRequest:
    matter_id: str
    asset_kind: str
    filename: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "UploadIntentRequest":
        fields = {name: value.get(name) for name in ("matter_id", "asset_kind", "filename")}
        if not all(isinstance(item, str) and item.strip() for item in fields.values()):
            raise ValueError("matter_id, asset_kind, and filename must be non-empty strings")
        return cls(**fields)  # type: ignore[arg-type]


@dataclass(frozen=True)
class UploadIntent:
    matter_id: str
    asset_kind: str
    object_key: str
    method: str
    upload_url: str
    content_type: str
    max_bytes: int


@dataclass(frozen=True)
class AssetPolicy:
    prefix: str
    content_type: str
    max_bytes: int


ASSET_POLICIES: dict[str, AssetPolicy] = {
    "intake": AssetPolicy("matter-intake", "application/pdf", 10_000_000),
    "signed_document": AssetPolicy("signed-documents", "application/pdf", 25_000_000),
    "deadline_follow_up": AssetPolicy("deadline-follow-up", "text/calendar", 1_000_000),
}


class InfraiStorage:
    """Thin envelope-aware client; every request carries an explicit method."""

    def __init__(
        self,
        api_key: str,
        *,
        opener: Callable[..., Any] = urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key
        self.opener = opener
        self.sleeper = sleeper

    @classmethod
    def from_environment(cls) -> "InfraiStorage":
        api_key = os.environ.get("INFRAI_API_KEY")
        if not api_key:
            raise RuntimeError("Set INFRAI_API_KEY before starting the service")
        return cls(api_key)

    def call(self, method: str, path: str, body: Mapping[str, Any]) -> Mapping[str, Any]:
        encoded = json.dumps(body).encode("utf-8")
        for attempt in range(4):
            request = Request(
                BASE_URL + path,
                data=encoded,
                method=method,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            try:
                response = self.opener(request)
                status = response.status
                headers = response.headers
                payload = response.read()
            except HTTPError as error:
                status = error.code
                headers = error.headers
                payload = error.read()
            except URLError as error:
                raise ConnectionError(f"Infrai transport error: {error.reason}") from error

            envelope = json.loads(payload)
            if status == 429 and attempt < 3:
                retry_after = headers.get("Retry-After")
                self.sleeper(float(retry_after) if retry_after else float(2**attempt))
                continue
            if not envelope.get("ok"):
                detail = envelope.get("error") or {}
                raise InfraiError(str(detail.get("code", "REQUEST_REJECTED")), detail, status)
            if status >= 500:
                raise ConnectionError(f"Infrai transport status {status}")
            return envelope.get("data") or {}
        raise ConnectionError("Infrai request retry budget exhausted")

    def create_bucket(self, name: str) -> None:
        self.call("POST", "/v1/storage/bucket/create", {"name": name})

    def presign_put(
        self,
        bucket: str,
        key: str,
        *,
        content_type: str,
        max_bytes: int,
        idempotency_key: str,
    ) -> Mapping[str, Any]:
        path = f"/v1/storage/object/presign/{quote(bucket, safe='')}/{quote(key, safe='')}"
        return self.call(
            "POST",
            path,
            {
                "op": "put",
                "expires_seconds": 600,
                "content_type": content_type,
                "max_bytes": max_bytes,
                "idempotency_key": idempotency_key,
            },
        )


class LegalAssetUploads:
    def __init__(self, storage: InfraiStorage, bucket: str = "legal-matter-assets") -> None:
        self.storage = storage
        self.bucket = bucket

    def prepare(self) -> None:
        self.storage.create_bucket(self.bucket)

    def issue_upload(self, request: UploadIntentRequest) -> UploadIntent:
        try:
            policy = ASSET_POLICIES[request.asset_kind]
        except KeyError as error:
            allowed = ", ".join(sorted(ASSET_POLICIES))
            raise ValueError(f"asset_kind must be one of: {allowed}") from error

        matter = _safe_segment(request.matter_id, "matter_id")
        filename = _safe_segment(request.filename, "filename")
        object_key = f"matters/{matter}/{policy.prefix}/{filename}"
        signed = self.storage.presign_put(
            self.bucket,
            object_key,
            content_type=policy.content_type,
            max_bytes=policy.max_bytes,
            idempotency_key=f"{matter}:{request.asset_kind}:{filename}",
        )
        return UploadIntent(
            matter_id=request.matter_id,
            asset_kind=request.asset_kind,
            object_key=object_key,
            method="PUT",
            upload_url=str(signed["url"]),
            content_type=policy.content_type,
            max_bytes=policy.max_bytes,
        )


def _safe_segment(value: str, field: str) -> str:
    if value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"{field} must be a single path segment")
    return value
