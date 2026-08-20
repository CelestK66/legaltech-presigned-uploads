from typing import Any

import pytest

from legal_asset_uploads import InfraiStorage, LegalAssetUploads, UploadIntentRequest


class RecordingStorage(InfraiStorage):
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def create_bucket(self, name: str) -> None:
        self.calls.append(("create_bucket", {"name": name}))

    def presign_put(self, bucket: str, key: str, **body: Any) -> dict[str, str]:
        self.calls.append(("presign_put", {"bucket": bucket, "key": key, **body}))
        return {"url": "https://upload.example/signed"}


def test_signed_document_gets_a_scoped_pdf_upload_after_bucket_setup() -> None:
    storage = RecordingStorage()
    workflow = LegalAssetUploads(storage)
    workflow.prepare()

    intent = workflow.issue_upload(
        UploadIntentRequest("matter-204", "signed_document", "settlement.pdf")
    )

    assert intent.method == "PUT"
    assert intent.object_key == "matters/matter-204/signed-documents/settlement.pdf"
    assert intent.content_type == "application/pdf"
    assert intent.max_bytes == 25_000_000
    assert storage.calls[0] == ("create_bucket", {"name": "legal-matter-assets"})
    assert storage.calls[1][1]["idempotency_key"] == "matter-204:signed_document:settlement.pdf"


def test_unknown_asset_kind_is_rejected_before_signing() -> None:
    storage = RecordingStorage()
    workflow = LegalAssetUploads(storage)

    with pytest.raises(ValueError, match="asset_kind must be one of"):
        workflow.issue_upload(UploadIntentRequest("matter-204", "evidence", "photo.jpg"))

    assert storage.calls == []
