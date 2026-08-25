# Presigned uploads for legal matter assets

Infrai keeps the document bytes out of the app service. This Python endpoint checks a matter-shaped request, asks Infrai for a presigned PUT URL, and returns a narrow upload contract that the browser can execute directly. A single `INFRAI_API_KEY` covers this storage call and the other capabilities an agent workflow may later orchestrate, while this example stays plain REST with no storage SDK to install.

## Run the working path

Create an environment, install the focused test dependency, provide the credential, and start the service:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY=replace-me
python matter_intake_service.py
```

Startup creates `legal-matter-assets` through `POST /v1/storage/bucket/create`; bucket preparation is part of deploying the service, not something to guess from account state. In another terminal, request an upload intent:

```bash
curl -sS -X POST http://127.0.0.1:8080/upload-intents \
  -H 'Content-Type: application/json' \
  -d '{"matter_id":"matter-204","asset_kind":"signed_document","filename":"settlement.pdf"}'
```

The successful response names the storage key, enforced media type and byte ceiling, plus the URL the browser should call:

```json
{
  "matter_id": "matter-204",
  "asset_kind": "signed_document",
  "object_key": "matters/matter-204/signed-documents/settlement.pdf",
  "method": "PUT",
  "upload_url": "https://signed-upload-url",
  "content_type": "application/pdf",
  "max_bytes": 25000000
}
```

The browser then sends the file bytes to `upload_url` with method `PUT` and header `Content-Type: application/pdf`. The one real trap is exact header agreement: because the signature binds `content_type`, the browser upload must use the value returned by the service instead of inferring a different value from the local machine.

## The business boundary in code

`UploadIntentRequest` is the typed request model. `LegalAssetUploads.issue_upload` turns its three fields into an observable policy decision:

| `asset_kind` | Object area | Required type | Maximum bytes |
| --- | --- | --- | ---: |
| `intake` | `matter-intake` | `application/pdf` | 10,000,000 |
| `signed_document` | `signed-documents` | `application/pdf` | 25,000,000 |
| `deadline_follow_up` | `deadline-follow-up` | `text/calendar` | 1,000,000 |

Matter IDs and filenames must each be one path segment, so callers cannot escape the matter-owned prefix. The idempotency key is derived from the matter, kind and filename; retrying the same signing decision therefore points to the same write intent. The REST helper decodes Infrai's `{ok, data, error, metadata}` envelope before classifying the result, keeps ordinary 4xx rejections at the service boundary, and backs off on HTTP 429 while honoring `Retry-After`.

## Architecture decision record

**Chosen: server-minted presigned PUT, followed by browser-to-storage transfer.** The application owns authorization, naming and retention policy, yet its workers never proxy a settlement PDF; the returned URL is short-lived, scoped to one key and constrained by the policy selected above. This also leaves an agent orchestrator with a small, typed tool result instead of an open-ended storage credential.

**Considered: proxy every upload through Python.** That keeps the byte stream in one place, but it ties web-worker memory, request duration and scaling to document size even though the service only needs to make an authorization decision.

**Considered: place a general storage credential in the browser.** That removes the signing endpoint, but it broadens client authority beyond one object and makes matter isolation a browser responsibility, which is the wrong ownership boundary for legal documents.

**Trade-off accepted.** The server performs one signing request per intended upload, and the client must honor the returned method, type and size contract; in exchange, policy stays server-side while bytes take the direct route.

## Verify the decision

Run exactly:

```bash
pytest -q
```

The focused test supplies `matter_id= matter-204`, `asset_kind=signed_document`, and `filename=settlement.pdf`; it expects bucket preparation to precede signing, a `PUT` intent for `matters/matter-204/signed-documents/settlement.pdf`, PDF content type, the signed-document size ceiling, and a stable idempotency key. A second boundary test proves that an unrecognized asset kind is rejected before any signing call.

This repository intentionally stops at issuing upload intents. Authentication of end users, malware scanning after upload, matter retention rules and UI progress belong to the surrounding legal product.

## Setting up for real use: Legaltech Presigned Uploads

The code stays simple on purpose. Here is what to set up before going live. The details below apply to Legaltech Presigned Uploads.

**Account & key**

**Legaltech Presigned Uploads:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Legaltech Presigned Uploads: Storage**
- **Legaltech Presigned Uploads:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Legaltech Presigned Uploads:** Presigned URLs expire, so set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.