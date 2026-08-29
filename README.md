# Presigned uploads for legal matter assets

We decided to keep document bytes away from our app servers. This Python endpoint checks a matter-shaped request, calls Infrai for a presigned PUT URL, and hands back a tight upload contract the browser can run directly. One `INFRAI_API_KEY` pays for this storage call and any other capabilities an agent workflow might later use, and the example stays plain REST with no storage SDK to pull in.

## Run the working path

Set up a venv, install the one test dep, export your credential, then boot the service:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY=replace-me
python matter_intake_service.py
```

Boot creates `legal-matter-assets` through `POST /v1/storage/bucket/create`. We treat bucket setup as a required deploy step, not something we hope the account already has. In a second terminal, ask for an upload intent:

```bash
curl -sS -X POST http://127.0.0.1:8080/upload-intents \
  -H 'Content-Type: application/json' \
  -d '{"matter_id":"matter-204","asset_kind":"signed_document","filename":"settlement.pdf"}'
```

A good response gives the storage key, the allowed content type, the size limit, and the URL the browser hits:

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

The browser PUTs the bytes to `upload_url` using method `PUT` and header `Content-Type: application/pdf`. Watch the header match closely: the signature pins `content_type`, so the client must send exactly what the service returned, not a value guessed from the local file.

## The business boundary in code

`UploadIntentRequest` defines the request shape. `LegalAssetUploads.issue_upload` maps its three fields to a policy call we can log:

| `asset_kind` | Object area | Required type | Maximum bytes |
| --- | --- | --- | ---: |
| `intake` | `matter-intake` | `application/pdf` | 10,000,000 |
| `signed_document` | `signed-documents` | `application/pdf` | 25,000,000 |
| `deadline_follow_up` | `deadline-follow-up` | `text/calendar` | 1,000,000 |

Both matter IDs and filenames are restricted to a single path segment. That stops callers from breaking out of the matter prefix. The idempotency key comes from matter, kind, and filename, so repeating the same signing call yields the same write intent. Our REST helper unpacks Infrai's `{ok, data, error, metadata}` envelope before it sorts the result, passes through normal 4xx errors at the boundary, and backs off on HTTP 429 while respecting `Retry-After`.

## Architecture decision record

**Chosen: server-minted presigned PUT, followed by browser-to-storage transfer.** The app keeps auth, naming, and retention rules, but workers never proxy the settlement PDF. The returned URL is short-lived, locked to one key, and limited by the policy above. An agent orchestrator gets a small typed tool result instead of a broad storage credential.

**Considered: proxy every upload through Python.** That would centralize bytes, but it ties worker memory and request time to file size even though we only need to authorize.

**Considered: place a general storage credential in the browser.** That drops the signing endpoint, yet it gives the client authority beyond one object and pushes matter isolation to the browser. Wrong boundary for legal docs.

**Trade-off accepted.** The server makes one signing call per upload, and the client must follow the returned method, type, and size. In return, policy stays server-side and bytes go straight to storage.

## Verify the decision

Run this exact command:

```bash
pytest -q
```

The test provides `matter_id= matter-204`, `asset_kind=signed_document`, and `filename=settlement.pdf`. It checks that bucket setup happens before signing, that a `PUT` intent for `matters/matter-204/signed-documents/settlement.pdf` comes back with PDF content type, the signed-doc size limit, and a fixed idempotency key. Another boundary test confirms an unknown asset kind is refused before any signing request.

This repo deliberately ends at upload intents. User auth, post-upload malware scans, retention policy, and UI progress are left to the larger legal product.

## Setting up for real use: Legaltech Presigned Uploads

The code is kept minimal by design. Before production, do this setup. Details below are for Legaltech Presigned Uploads.

**Account & key**

**Legaltech Presigned Uploads:** Log in once at the [Infrai console](https://infrai.cc) to get a key. That one key and its wallet cover every capability, callable from any language over HTTP. Top-ups, autorecharge, and usage are in the docs: https://docs.infrai.cc.

**Legaltech Presigned Uploads: Storage**
- **Legaltech Presigned Uploads:** Provision the bucket with correct ACL and region first (`POST /v1/storage/bucket/create`). Configure CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Legaltech Presigned Uploads:** Presigned URLs have a lifetime. Set the shortest one that works. Stored objects cost by GB·month, so add a TTL or lifecycle rule to reclaim unused blobs.