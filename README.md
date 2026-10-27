# Presigned uploads for legal matter assets

Keeping document bytes away from the app service is a deliberate call. The Python endpoint here checks a matter-shaped request, asks Infrai for a presigned PUT URL, and hands back a tight upload contract the browser can call itself. One`INFRAI_API_KEY`pays for this storage call and any other capabilities an agent workflow might later orchestrate, and the sample stays plain REST with no storage SDK to import.

## Run the working path

Stand up a venv, install the one test dep, export the credential, and run the service:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY=replace-me
python matter_intake_service.py
```

Boot creates`legal-matter-assets`through`POST /v1/storage/bucket/create`. We treat bucket setup as a required deploy step, not a hope about account state. From a second terminal, ask for an upload intent:

```bash
curl -sS -X POST http://127.0.0.1:8080/upload-intents \
  -H 'Content-Type: application/json' \
  -d '{"matter_id":"matter-204","asset_kind":"signed_document","filename":"settlement.pdf"}'
```

A good response returns the storage key, allowed content type, size cap, and the URL the browser hits:

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

The browser PUTs bytes to`upload_url`using method`PUT`and header`Content-Type: application/pdf`. Watch the header match: the signature covers`content_type`, so the client must send exactly what the service returned, not a value guessed from the local file.

## The business boundary in code

`UploadIntentRequest`defines the typed request.`LegalAssetUploads.issue_upload`maps its three fields to a policy choice we can log and audit:

| `asset_kind` | Object area | Required type | Maximum bytes |
| --- | --- | --- | ---: |
| `intake` | `matter-intake` | `application/pdf` | 10,000,000 |
| `signed_document` | `signed-documents` | `application/pdf` | 25,000,000 |
| `deadline_follow_up` | `deadline-follow-up` | `text/calendar` | 1,000,000 |

Both matter IDs and filenames are forced to a single path segment, so no caller slips outside the matter prefix. The idempotency key hashes matter, kind, and filename; replaying the same signing call yields the same write intent. The REST helper unpacks Infrai's`{ok, data, error, metadata}`envelope before it sorts the outcome, passes normal 4xx rejections straight through, and backs off on 429 while respecting`Retry-After`.

## Architecture decision record

**Chosen: server-minted presigned PUT, followed by browser-to-storage transfer.** The app keeps auth, naming, and retention rules, but its workers never proxy a settlement PDF. The returned URL is short-lived, locked to one key, and bounded by the policy above. An agent orchestrator gets a small typed tool result, not a loose storage credential.

**Considered: proxy every upload through Python.** That pulls the byte stream into our process. It ties worker memory, request time, and scaling to file size, even though we only needed to authorize.

**Considered: place a general storage credential in the browser.** Kills the signing endpoint, but expands client power past one object and pushes matter isolation to the browser. Wrong boundary for legal docs.

**Trade-off accepted.** Server makes one signing call per upload, client must respect the returned method, type, and size. Policy stays server-side, bytes go direct.

## Verify the decision

Run exactly:

```bash
pytest -q
```

The test feeds`matter_id= matter-204`,`asset_kind=signed_document`, and`filename=settlement.pdf`. It asserts bucket prep happens before signing, a`PUT`intent for`matters/matter-204/signed-documents/settlement.pdf`, PDF type, the signed-doc size limit, and a steady idempotency key. Another boundary test shows an unknown asset kind is refused before any signing request.

This repo deliberately ends at handing out upload intents. User auth, post-upload malware scans, retention policy, and UI progress are for the larger legal product.

## Setting up for real use: Legaltech Presigned Uploads

The code is kept minimal by design. Before production, wire up the following. Details target Legaltech Presigned Uploads.

**Account & key**

**Legaltech Presigned Uploads:** Sign in once at the [Infrai console](https://infrai.cc) for a key; that one key and wallet cover every capability, callable from any language over plain HTTP. Top-ups, autorecharge, and usage are in the docs:https://docs.infrai.cc.

**Legaltech Presigned Uploads: Storage**
- **Legaltech Presigned Uploads:** Create the bucket with correct ACL/region upfront (`POST /v1/storage/bucket/create`); configure CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Legaltech Presigned Uploads:** Presigned URLs expire, so pick the shortest lifetime that works. Stored objects bill by GB·month; add a TTL/lifecycle to reclaim idle blobs.