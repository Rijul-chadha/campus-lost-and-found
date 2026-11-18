"""S3-compatible object storage (S3Mock locally; S3 / Cloudflare R2 / Supabase in production).

Uploads never pass through the API: the browser POSTs directly to the bucket with a
short-lived presigned policy that pins the key prefix, size limit and content type.
Two clients exist because presigned URLs embed the host: the internal one talks to
`s3:9090` inside Docker, the public one signs URLs for `localhost:9000` / the CDN.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any

import boto3
from botocore.client import Config

from app.core.config import Settings, get_settings


def _client(settings: Settings, endpoint: str | None) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.s3_access_key or None,
        aws_secret_access_key=settings.s3_secret_key or None,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


class Storage:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.bucket = settings.s3_bucket
        self._internal = _client(settings, settings.s3_endpoint_url)
        self._public = _client(settings, settings.s3_public_endpoint_url or
                               settings.s3_endpoint_url)

    def presign_upload(self, key: str, content_type: str) -> dict[str, Any]:
        return self._public.generate_presigned_post(  # type: ignore[no-any-return]
            Bucket=self.bucket,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, self.s.upload_max_bytes],
            ],
            ExpiresIn=self.s.upload_url_ttl_seconds,
        )

    def presign_get(self, key: str, ttl_s: int = 900) -> str:
        return self._public.generate_presigned_url(  # type: ignore[no-any-return]
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=ttl_s
        )

    async def get_bytes(self, key: str) -> bytes:
        def _get() -> bytes:
            obj = self._internal.get_object(Bucket=self.bucket, Key=key)
            return obj["Body"].read()  # type: ignore[no-any-return]

        return await asyncio.to_thread(_get)

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._internal.put_object, Bucket=self.bucket, Key=key, Body=data,
            ContentType=content_type,
        )

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._internal.delete_object, Bucket=self.bucket, Key=key)


@lru_cache
def get_storage() -> Storage:
    return Storage(get_settings())
