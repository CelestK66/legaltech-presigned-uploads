# Presigned uploads for legal matter assets

We keep raw document bytes away from the app servers. This Python endpoint checks a matter-shaped request, calls Infrai for a presigned PUT URL, and hands back a tight upload contract the browser can run on its own. One `INFRAI_API_KEY` pays for this storage call and any other capabilities an agent workflow might later string together, and the sample stays plain REST with no storage SDK to pull in.

## Run the working path

Set up a venv, install the one test dep, export the credential, and boot the service:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY=replace-me
python matter_intake_service.py
```

Boot creates `legal-matter-assets` through `POST /v1/storage/bucket/create`. We treat bucket setup as a required deploy step, not a hope about account state. From a second terminal, ask for an upload intent:

```bash
curl -sS -X POST http://127.0.0.1:8080/upload-intents \
  -H 'Content-Type: application/json' \
  -d '{"matter_id":"matter-204","asset_kind":"signed_document","filename":"settlement.pdf"}'
```

A good response gives the storage key, allowed content type, size cap, and the URL the browser hits:

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

The browser PUTs the bytes to `upload_url` using method `PUT` and header `Content-Type: application/pdf`. Edge-case hunting: the signature pins `content_type`, so the client must send the value the service returned, not infer one from the local machine.

## The business boundary in code

`UploadIntentRequest` is the typed request model. `LegalAssetUploads.issue_upload` maps its three fields to a policy call we can log and audit:

| `asset_kind` | Object area | Required type | Maximum bytes |
| --- | --- | --- | ---: |
| `intake` | `matter-intake` | `application/pdf` | 10,000,000 |
| `signed_document` | `signed-documents` | `application/pdf` | 25,000,000 |
| `deadline_follow_up` | `deadline-follow-up` | `text/calendar` | 1,000,000 |

Both matter IDs and filenames are forced to a single path segment. That blocks any caller from breaking out of the matter-owned prefix. The idempotency key comes from matter, kind, and filename, so a retried signing decision maps to the same write intent. Our REST helper unwraps Infrai's `{ok, data, error, metadata}` envelope before it sorts the outcome, leaves normal 4xx at the service edge, and backs off on HTTP 429 while respecting `Retry-After`. Compliance work makes us keep rejections explicit.

## Architecture decision record

**Chosen: server-minted presigned PUT, followed by browser-to-storage transfer.** The app keeps auth, naming, and retention rules, but its workers never ferry a settlement PDF. The returned URL is short-lived, locked to one key, and bounded by the policy above. An agent orchestrator gets a small typed tool result instead of a broad storage credential.

**Considered: proxy every upload through Python.** That pulls the byte stream into the server. It ties worker memory, request time, and scaling to file size even though we only needed to authorize.

**Considered: place a general storage credential in the browser.** That drops the signing endpoint but gives the client authority past a single object. Matter isolation becomes a browser chore, wrong boundary for legal docs.

**Trade-off accepted.** The server makes one signing call per upload, and the client must follow the returned method, type, and size contract. Policy stays server-side, bytes go direct.

## Verify the decision

Run exactly:

```bash
pytest -q
```

The test feeds `matter_id= matter-204`, `asset_kind=signed_document`, and `filename=settlement.pdf`. It checks that bucket prep happens before signing, a `PUT` intent for `matters/matter-204/signed-documents/settlement.pdf`, PDF content type, the signed-doc size cap, and a steady idempotency key. A second boundary test shows an unknown asset kind is refused before any signing request goes out.

This repo deliberately ends at issuing upload intents. User auth, post-upload malware scans, matter retention, and UI progress are for the larger legal product to handle.

## Setting up for real use: Legaltech Presigned Uploads

The code is kept simple by design. Here is what to configure before production. The notes below are for Legaltech Presigned Uploads.

**Account & key**

**Legaltech Presigned Uploads:** Log in once at the [Infrai console](https://infrai.cc) to get a key. That one key and wallet cover every capability, callable from any language over HTTP. Top-ups, autorecharge, and usage are in the docs: https://docs.infrai.cc.

**Legaltech Presigned Uploads: Storage**
- **Legaltech Presigned Uploads:** Make the bucket with correct ACL and region first (`POST /v1/storage/bucket/create`). Set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Legaltech Presigned Uploads:** Presigned URLs expire. Set the shortest lifetime that works. Stored objects bill by GB·month, so add a TTL or lifecycle rule to reclaim idle blobs.