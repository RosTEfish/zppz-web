from io import BytesIO

from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber

from app.core.config import get_settings
from app.modules.object_storage import R2ObjectStore


def r2_store() -> R2ObjectStore:
    settings = get_settings()
    previous = {
        name: getattr(settings, name)
        for name in (
            "object_storage_backend",
            "r2_account_id",
            "r2_bucket_name",
            "r2_access_key_id",
            "r2_secret_access_key",
        )
    }
    try:
        settings.object_storage_backend = "r2"
        settings.r2_account_id = "a" * 32
        settings.r2_bucket_name = "submissions"
        settings.r2_access_key_id = "access-key"
        settings.r2_secret_access_key = "secret-key"
        return R2ObjectStore()
    finally:
        for name, value in previous.items():
            setattr(settings, name, value)


def test_r2_adapter_heads_copies_streams_and_deletes_objects():
    store = r2_store()
    body = StreamingBody(BytesIO(b"payload"), 7)
    with Stubber(store.client) as stubber:
        stubber.add_response(
            "head_object",
            {"ContentLength": 7, "ContentType": "application/zip"},
            {"Bucket": "submissions", "Key": "source.zip"},
        )
        stubber.add_response(
            "copy_object",
            {},
            {
                "Bucket": "submissions",
                "Key": "final.zip",
                "CopySource": {"Bucket": "submissions", "Key": "source.zip"},
                "MetadataDirective": "REPLACE",
                "ContentType": "application/zip",
                "ContentDisposition": "attachment; filename=\"final.zip\"",
            },
        )
        stubber.add_response(
            "get_object",
            {"Body": body, "ContentLength": 7},
            {"Bucket": "submissions", "Key": "final.zip"},
        )
        stubber.add_response(
            "delete_object",
            {},
            {"Bucket": "submissions", "Key": "final.zip"},
        )

        assert store.head("source.zip").size == 7
        store.copy(
            "source.zip",
            "final.zip",
            content_type="application/zip",
            content_disposition='attachment; filename="final.zip"',
        )
        assert b"".join(store.chunks("final.zip", 7)) == b"payload"
        store.delete("final.zip")


def test_r2_adapter_generates_scoped_presigned_urls_without_network_calls():
    store = r2_store()
    upload = store.create_upload_url("intent", "application/zip", "pending/source.zip")
    download = store.create_download_url("final/source.zip", "投稿.zip")

    assert "pending/source.zip" in upload
    assert "X-Amz-Signature=" in upload
    assert "final/source.zip" in download
    assert "X-Amz-Signature=" in download


def test_r2_storage_check_verifies_bucket_and_object_lifecycle():
    store = r2_store()
    with Stubber(store.client) as stubber:
        stubber.add_response("head_bucket", {}, {"Bucket": "submissions"})
        stubber.add_response(
            "put_object",
            {},
            {
                "Bucket": "submissions",
                "Key": ANY,
                "Body": b"ok",
                "ContentType": "text/plain",
            },
        )
        stubber.add_response(
            "head_object",
            {"ContentLength": 2, "ContentType": "text/plain"},
            {"Bucket": "submissions", "Key": ANY},
        )
        stubber.add_response(
            "delete_object",
            {},
            {"Bucket": "submissions", "Key": ANY},
        )

        store.check()
