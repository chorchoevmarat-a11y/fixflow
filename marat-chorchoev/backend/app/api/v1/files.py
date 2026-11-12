import os
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_membership
from app.database import get_db
from app.models.models import FileAttachment, OrganizationMembership, ServiceRequest

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
    service_request_id: uuid.UUID | None = None,
    work_note_id: uuid.UUID | None = None,
) -> dict:
    if service_request_id:
        sr = await db.get(ServiceRequest, service_request_id)
        if not sr or sr.org_id != membership.organization_id:
            raise HTTPException(status_code=404, detail="Service request not found")

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_ext = Path(file.filename or "").suffix
    stored_name = f"{uuid.uuid4()}{file_ext}"
    dest_path = upload_dir / stored_name

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")

    with open(dest_path, "wb") as f:
        f.write(content)

    attachment = FileAttachment(
        org_id=membership.organization_id,
        service_request_id=service_request_id,
        work_note_id=work_note_id,
        uploaded_by_id=membership.user_id,
        filename=file.filename or "unknown",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        storage_path=str(dest_path),
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)

    return {
        "id": str(attachment.id),
        "filename": attachment.filename,
        "size_bytes": attachment.size_bytes,
        "content_type": attachment.content_type,
    }


@router.get("/{file_id}")
async def download_file(
    file_id: uuid.UUID,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    att = await db.get(FileAttachment, file_id)
    if not att or att.org_id != membership.organization_id:
        raise HTTPException(status_code=404, detail="File not found")

    if not os.path.exists(att.storage_path):
        raise HTTPException(status_code=404, detail="File content missing on disk")

    return FileResponse(path=att.storage_path, filename=att.filename, media_type=att.content_type)
