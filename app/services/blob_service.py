"""
Azure Blob Storage Service
Handles image uploads for destinations, hotels, vehicles, itineraries
and PDF uploads for quotations. All container names and keys come from env.
"""

import io
import logging
import mimetypes
import uuid
from pathlib import Path
from typing import Optional, Tuple

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
)
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, UploadFile, status

from app.config import settings

logger = logging.getLogger(__name__)


class BlobStorageService:
    """Thin wrapper around Azure BlobServiceClient."""

    def __init__(self) -> None:
        self._client: Optional[BlobServiceClient] = None

    @property
    def client(self) -> BlobServiceClient:
        if self._client is None:
            if settings.AZURE_STORAGE_CONNECTION_STRING:
                self._client = BlobServiceClient.from_connection_string(
                    settings.AZURE_STORAGE_CONNECTION_STRING
                )
            elif settings.AZURE_STORAGE_ACCOUNT_NAME and settings.AZURE_STORAGE_ACCOUNT_KEY:
                account_url = f"https://{settings.AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net"
                self._client = BlobServiceClient(
                    account_url=account_url,
                    credential=settings.AZURE_STORAGE_ACCOUNT_KEY,
                )
            else:
                raise RuntimeError(
                    "Azure storage not configured. Set AZURE_STORAGE_CONNECTION_STRING "
                    "or AZURE_STORAGE_ACCOUNT_NAME + AZURE_STORAGE_ACCOUNT_KEY in .env"
                )
        return self._client

    # ── Container bootstrap ───────────────────────────────────────────────────

    async def ensure_containers_exist(self) -> None:
        """Create all required containers if they don't exist. Run at startup."""
        containers = [
            settings.AZURE_CONTAINER_DESTINATIONS,
            settings.AZURE_CONTAINER_HOTELS,
            settings.AZURE_CONTAINER_ITINERARIES,
            settings.AZURE_CONTAINER_QUOTATIONS,
            settings.AZURE_CONTAINER_VEHICLES,
        ]
        for container_name in containers:
            try:
                container_client = self.client.get_container_client(container_name)
                container_client.create_container(public_access="blob")
                logger.info(f"Created container: {container_name}")
            except Exception:
                # Container already exists — that's fine
                logger.debug(f"Container already exists: {container_name}")

    # ── Upload ────────────────────────────────────────────────────────────────

    def _validate_file(self, file: UploadFile, allowed_types: Tuple[str, ...]) -> None:
        if file.size and file.size > settings.max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum size is {settings.MAX_UPLOAD_SIZE_MB} MB",
            )
        content_type = file.content_type or ""
        if not any(content_type.startswith(t) for t in allowed_types):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported file type: {content_type}. Allowed: {allowed_types}",
            )

    def _generate_blob_name(self, original_filename: str, prefix: str = "") -> str:
        ext = Path(original_filename).suffix.lower() or ".bin"
        unique_id = uuid.uuid4().hex
        safe_prefix = prefix.strip("/").replace(" ", "_") if prefix else ""
        if safe_prefix:
            return f"{safe_prefix}/{unique_id}{ext}"
        return f"{unique_id}{ext}"

    async def upload_image(
        self,
        file: UploadFile,
        container_name: str,
        prefix: str = "",
    ) -> Tuple[str, str]:
        """
        Upload an image file to Azure Blob Storage.
        Returns (blob_name, public_url).
        """
        self._validate_file(file, ("image/jpeg", "image/png", "image/webp", "image/gif"))

        blob_name = self._generate_blob_name(file.filename or "image.jpg", prefix)
        content_type = file.content_type or "image/jpeg"

        try:
            content = await file.read()
            blob_client = self.client.get_blob_client(container=container_name, blob=blob_name)
            blob_client.upload_blob(
                data=io.BytesIO(content),
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
            )
            public_url = settings.blob_public_url(container_name, blob_name)
            logger.info(f"Uploaded image: {blob_name} → {container_name}")
            return blob_name, public_url

        except AzureError as exc:
            logger.error(f"Azure upload failed: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"File upload failed: {str(exc)}",
            ) from exc

    async def upload_pdf(
        self,
        pdf_bytes: bytes,
        blob_name: str,
    ) -> str:
        """
        Upload a generated PDF quotation to Azure Blob.
        Returns the public URL.
        """
        container_name = settings.AZURE_CONTAINER_QUOTATIONS
        try:
            blob_client = self.client.get_blob_client(container=container_name, blob=blob_name)
            blob_client.upload_blob(
                data=io.BytesIO(pdf_bytes),
                overwrite=True,
                content_settings=ContentSettings(content_type="application/pdf"),
            )
            public_url = settings.blob_public_url(container_name, blob_name)
            logger.info(f"Uploaded PDF: {blob_name}")
            return public_url

        except AzureError as exc:
            logger.error(f"Azure PDF upload failed: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"PDF upload failed: {str(exc)}",
            ) from exc

    # ── Delete ────────────────────────────────────────────────────────────────

    def delete_blob(self, container_name: str, blob_name: str) -> bool:
        """Delete a blob. Returns True if deleted, False if not found."""
        try:
            blob_client = self.client.get_blob_client(container=container_name, blob=blob_name)
            blob_client.delete_blob()
            logger.info(f"Deleted blob: {blob_name} from {container_name}")
            return True
        except ResourceNotFoundError:
            return False
        except AzureError as exc:
            logger.error(f"Azure delete failed: {exc}")
            return False

    # ── Signed URL (for private containers) ──────────────────────────────────

    def generate_sas_url(
        self,
        container_name: str,
        blob_name: str,
        expiry_hours: int = 24,
    ) -> str:
        """Generate a time-limited SAS URL for private blob access."""
        sas_token = generate_blob_sas(
            account_name=settings.AZURE_STORAGE_ACCOUNT_NAME,
            container_name=container_name,
            blob_name=blob_name,
            account_key=settings.AZURE_STORAGE_ACCOUNT_KEY,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(hours=expiry_hours),
        )
        return (
            f"https://{settings.AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net"
            f"/{container_name}/{blob_name}?{sas_token}"
        )

    # ── Health check ──────────────────────────────────────────────────────────

    def check_connection(self) -> bool:
        try:
            list(self.client.list_containers(max_results=1))
            return True
        except Exception:
            return False


# Singleton instance
blob_service = BlobStorageService()