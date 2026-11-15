"""Work notes and evidence files (COMM-01, COMM-02, COMM-05, COMM-06)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import Body, CommandId
from app.config import settings
from app.core.deps import DB, Ctx, CurrentCtx
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.core.security import payload_hash
from app.models.models import (
    Assignment,
    AssignmentStatus,
    EvidenceFile,
    EvidenceKind,
    NoteVisibility,
    RequestStatus,
    ServiceRequest,
    TechnicianProfile,
    User,
    WorkNote,
)
from app.services import files as file_service
from app.services import requests as svc
from app.services.common import audit, iso

router = APIRouter(tags=["notes and files"])
_CLOSED = (RequestStatus.CLOSED, RequestStatus.CANCELED)


class NoteBody(Body):
    body: str = Field(min_length=1, max_length=4000)
    visibility: NoteVisibility = NoteVisibility.PUBLIC
    client_command_id: CommandId
    assignment_id: uuid.UUID | None = Field(
        default=None,
        description="Technicians: the assignment the note was written under. "
        "The command is rejected if that assignment is no longer active.",
    )


async def _writable_request(
    db: AsyncSession, ctx: Ctx, request_id: uuid.UUID, expected_assignment: uuid.UUID | None
) -> tuple[ServiceRequest, Assignment | None]:
    """Load a request for a note/evidence command, with offline-replay conflict detection.

    A technician whose job was reassigned or closed while they were offline gets an
    explicit 409 (never a silent publish to somebody else's assignment) so the mobile
    app can keep the draft and show a conflict (MOB-07).
    """
    try:
        req = await svc.get_request(db, ctx, request_id, lock=True)
    except NotFound:
        if ctx.is_technician:
            was_mine = await db.scalar(
                select(func.count())
                .select_from(Assignment)
                .join(TechnicianProfile, TechnicianProfile.id == Assignment.technician_id)
                .where(
                    Assignment.request_id == request_id,
                    Assignment.org_id == ctx.org_id,
                    TechnicianProfile.user_id == ctx.user.id,
                )
            )
            if was_mine:
                raise Conflict(
                    "This job is no longer assigned to you.", code="ASSIGNMENT_REVOKED"
                ) from None
        raise
    if req.status in _CLOSED:
        raise Conflict(f"This request is {req.status}.", code="REQUEST_CLOSED")
    assignment = None
    if ctx.is_technician:
        assignment = await svc.active_assignment(db, req.id)
        profile = await svc.my_profile(db, ctx)
        mine = (
            assignment is not None
            and profile is not None
            and assignment.technician_id == profile.id
        )
        if not mine or (
            expected_assignment is not None
            and assignment is not None
            and assignment.id != expected_assignment
        ):
            raise Conflict("This job is no longer assigned to you.", code="ASSIGNMENT_REVOKED")
    return req, assignment


def _note_view(note: WorkNote, author: str, attachments: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": str(note.id),
        "request_id": str(note.request_id),
        "author_id": str(note.author_id),
        "author_name": author,
        "author_role": note.author_role,
        "body": note.body,
        "visibility": note.visibility,
        "client_command_id": note.client_command_id,
        "created_at": iso(note.created_at),
        "attachments": attachments,
    }


def _file_view(file: EvidenceFile, uploader: str | None = None) -> dict[str, Any]:
    return {
        "id": str(file.id),
        "request_id": str(file.request_id),
        "note_id": str(file.note_id) if file.note_id else None,
        "kind": file.kind,
        "visibility": file.visibility,
        "original_name": file.original_name,
        "content_type": file.content_type,
        "size_bytes": file.size_bytes,
        "width": file.width,
        "height": file.height,
        "uploaded_by": uploader,
        "client_command_id": file.client_command_id,
        "created_at": iso(file.created_at),
        "content_url": f"/api/v1/files/{file.id}/content",
    }


@router.get(
    "/requests/{request_id}/notes", summary="Notes on a request (internal hidden from requesters)"
)
async def list_notes(request_id: uuid.UUID, ctx: CurrentCtx, db: DB) -> list[dict[str, Any]]:
    req = await svc.get_request(db, ctx, request_id)
    query = (
        select(WorkNote, User.full_name)
        .join(User, User.id == WorkNote.author_id)
        .where(WorkNote.request_id == req.id, WorkNote.org_id == ctx.org_id)
        .order_by(WorkNote.created_at, WorkNote.id)
        .limit(500)
    )
    if ctx.is_requester:
        query = query.where(WorkNote.visibility == NoteVisibility.PUBLIC)
    rows = (await db.execute(query)).all()
    attachments: dict[uuid.UUID, list[dict[str, Any]]] = {note.id: [] for note, _ in rows}
    if rows:
        for file in await db.scalars(
            select(EvidenceFile)
            .where(EvidenceFile.note_id.in_(list(attachments)))
            .order_by(EvidenceFile.created_at)
        ):
            if file.note_id is not None:
                attachments[file.note_id].append(_file_view(file))
    return [_note_view(note, author, attachments[note.id]) for note, author in rows]


@router.post(
    "/requests/{request_id}/notes",
    status_code=201,
    summary="Add an immutable note (replay safe via client_command_id)",
    responses={
        200: {"description": "Replay of an already-stored note"},
        409: {"description": "Command id reused, request closed, or assignment revoked"},
    },
)
async def create_note(
    request_id: uuid.UUID, body: NoteBody, ctx: CurrentCtx, db: DB
) -> JSONResponse:
    digest = payload_hash(
        {"request_id": request_id, "body": body.body, "visibility": body.visibility.value}
    )

    async def replayed() -> JSONResponse | None:
        existing = (
            await db.execute(
                select(WorkNote).where(
                    WorkNote.org_id == ctx.org_id,
                    WorkNote.client_command_id == body.client_command_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            return None
        if existing.author_id != ctx.user.id or existing.payload_hash != digest:
            raise Conflict(
                "This command id was already used for a different note.", code="COMMAND_ID_REUSED"
            )
        return JSONResponse(
            _note_view(existing, ctx.user.full_name, []),
            status_code=200,
            headers={"Idempotency-Replayed": "true"},
        )

    # Replays win over state checks: the original effect is preserved exactly once.
    if (response := await replayed()) is not None:
        return response
    if ctx.is_requester and body.visibility == NoteVisibility.INTERNAL:
        raise Forbidden("Requesters cannot write internal notes.", code="ROLE_FORBIDDEN")
    req, assignment = await _writable_request(db, ctx, request_id, body.assignment_id)
    note = WorkNote(
        org_id=ctx.org_id,
        request_id=req.id,
        author_id=ctx.user.id,
        author_role=ctx.role,
        body=body.body,
        visibility=body.visibility,
        assignment_id=assignment.id if assignment else None,
        client_command_id=body.client_command_id,
        payload_hash=digest,
    )
    try:
        async with db.begin_nested():
            db.add(note)
            await db.flush()
    except IntegrityError as exc:
        if "uq_work_note_command" not in str(exc.orig):
            raise
        if (response := await replayed()) is not None:
            return response
        raise
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="note.added",
        target_type="work_note",
        target_id=note.id,
        request_id=req.id,
        summary=f"{ctx.user.full_name} added a{'n internal' if body.visibility == NoteVisibility.INTERNAL else ''} note",
        after={"visibility": body.visibility.value},
        is_public=body.visibility == NoteVisibility.PUBLIC,
    )
    await svc.publish_request_event(
        db,
        req,
        "note_added",
        (await svc.technician_user_id(db, await svc.active_assignment(db, req.id)),),
    )
    await db.commit()
    return JSONResponse(_note_view(note, ctx.user.full_name, []), status_code=201)


@router.get("/requests/{request_id}/files", summary="Evidence files of a request")
async def list_files(request_id: uuid.UUID, ctx: CurrentCtx, db: DB) -> list[dict[str, Any]]:
    req = await svc.get_request(db, ctx, request_id)
    query = (
        select(EvidenceFile, User.full_name)
        .join(User, User.id == EvidenceFile.uploader_id)
        .where(EvidenceFile.request_id == req.id, EvidenceFile.org_id == ctx.org_id)
        .order_by(EvidenceFile.created_at, EvidenceFile.id)
        .limit(500)
    )
    if ctx.is_requester:
        query = query.where(EvidenceFile.visibility == NoteVisibility.PUBLIC)
    return [_file_view(file, uploader) for file, uploader in await db.execute(query)]


@router.post(
    "/requests/{request_id}/files",
    status_code=201,
    summary="Upload a JPEG/PNG/WebP image (max 10 MiB; replay safe)",
    responses={
        200: {"description": "Replay of an already-stored file"},
        413: {"description": "File too large"},
        422: {"description": "Not a valid supported image"},
    },
)
async def upload_file(
    request_id: uuid.UUID,
    ctx: CurrentCtx,
    db: DB,
    file: Annotated[UploadFile, File(description="JPEG, PNG, or WebP image")],
    kind: Annotated[EvidenceKind, Form()],
    client_command_id: Annotated[
        str, Form(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    ],
    note_id: Annotated[uuid.UUID | None, Form()] = None,
    assignment_id: Annotated[uuid.UUID | None, Form()] = None,
) -> JSONResponse:
    image = await file_service.read_image(file)

    async def replayed() -> JSONResponse | None:
        existing = (
            await db.execute(
                select(EvidenceFile).where(
                    EvidenceFile.org_id == ctx.org_id,
                    EvidenceFile.client_command_id == client_command_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            return None
        if (
            existing.uploader_id != ctx.user.id
            or existing.sha256 != image.sha256
            or existing.request_id != request_id
        ):
            raise Conflict(
                "This command id was already used for a different file.", code="COMMAND_ID_REUSED"
            )
        return JSONResponse(
            _file_view(existing, ctx.user.full_name),
            status_code=200,
            headers={"Idempotency-Replayed": "true"},
        )

    if (response := await replayed()) is not None:
        return response

    req, assignment = await _writable_request(db, ctx, request_id, assignment_id)
    visibility = NoteVisibility.PUBLIC
    if kind == EvidenceKind.INTAKE:
        if ctx.is_technician or (ctx.is_requester and req.requester_id != ctx.user.id):
            raise Forbidden(
                "Only the requester or staff can add intake images.", code="ROLE_FORBIDDEN"
            )
        if req.status not in (RequestStatus.SUBMITTED, RequestStatus.TRIAGED):
            raise Conflict(
                "Intake images can only be added before work is scheduled.",
                code="INVALID_TRANSITION",
            )
        # The request row is locked, so this count cannot race another upload (REQ-01).
        count = await db.scalar(
            select(func.count())
            .select_from(EvidenceFile)
            .where(EvidenceFile.request_id == req.id, EvidenceFile.kind == EvidenceKind.INTAKE)
        )
        if (count or 0) >= settings.MAX_INTAKE_IMAGES:
            raise Conflict(
                f"A request can have at most {settings.MAX_INTAKE_IMAGES} intake images.",
                code="INTAKE_IMAGE_LIMIT",
            )
    elif kind == EvidenceKind.COMPLETION:
        if assignment is None:
            raise Forbidden(
                "Only the assigned technician can add completion evidence.", code="ROLE_FORBIDDEN"
            )
        if req.status != RequestStatus.IN_PROGRESS:
            raise Conflict(
                "Completion evidence can only be added while work is in progress.",
                code="INVALID_TRANSITION",
            )
    else:
        if note_id is None:
            raise Unprocessable("note_id is required for note attachments.", code="NOTE_REQUIRED")
        note = (
            await db.execute(
                select(WorkNote).where(
                    WorkNote.id == note_id,
                    WorkNote.org_id == ctx.org_id,
                    WorkNote.request_id == req.id,
                    WorkNote.author_id == ctx.user.id,
                )
            )
        ).scalar_one_or_none()
        if note is None:
            raise Unprocessable(
                "Attach files only to your own notes on this request.", code="NOTE_NOT_FOUND"
            )
        visibility = NoteVisibility(note.visibility)

    storage_key = file_service.new_storage_key(ctx.org_id, image.extension)
    record = EvidenceFile(
        org_id=ctx.org_id,
        request_id=req.id,
        note_id=note_id if kind == EvidenceKind.NOTE else None,
        assignment_id=assignment.id if assignment else None,
        uploader_id=ctx.user.id,
        kind=kind,
        visibility=visibility,
        original_name=file_service.safe_name(file.filename),
        content_type=image.content_type,
        size_bytes=len(image.data),
        width=image.width,
        height=image.height,
        sha256=image.sha256,
        storage_key=storage_key,
        client_command_id=client_command_id,
    )
    # Bytes go to disk first; the row is committed only afterwards. Any failure removes
    # the bytes, so an incomplete upload never leaves an accessible record (SEC-04).
    file_service.store(storage_key, image.data)
    try:
        try:
            async with db.begin_nested():
                db.add(record)
                await db.flush()
        except IntegrityError as exc:
            if "uq_evidence_command" not in str(exc.orig):
                raise
            file_service.discard(storage_key)
            if (response := await replayed()) is not None:
                return response
            raise
        audit(
            db,
            org_id=ctx.org_id,
            actor_id=ctx.user.id,
            action="evidence.uploaded",
            target_type="evidence_file",
            target_id=record.id,
            request_id=req.id,
            summary=f"{ctx.user.full_name} added a {kind.value.lower()} image",
            after={"kind": kind.value, "size_bytes": record.size_bytes},
            is_public=visibility == NoteVisibility.PUBLIC,
        )
        await svc.publish_request_event(db, req, "evidence_added", (ctx.user.id,))
        await db.commit()
    except BaseException:
        file_service.discard(storage_key)
        raise
    return JSONResponse(_file_view(record, ctx.user.full_name), status_code=201)


@router.get(
    "/files/{file_id}/content",
    summary="Download evidence (authenticated and authorized on every request)",
    response_class=FileResponse,
)
async def download_file(file_id: uuid.UUID, ctx: CurrentCtx, db: DB) -> FileResponse:
    record = (
        await db.execute(
            select(EvidenceFile).where(
                EvidenceFile.id == file_id, EvidenceFile.org_id == ctx.org_id
            )
        )
    ).scalar_one_or_none()
    not_found = NotFound("File not found.", code="FILE_NOT_FOUND")
    if record is None:
        raise not_found
    try:
        await svc.get_request(db, ctx, record.request_id)
    except NotFound:
        raise not_found from None
    if ctx.is_requester and record.visibility != NoteVisibility.PUBLIC:
        raise not_found
    path = file_service.path_for(record.storage_key)
    if not path.is_file():
        raise NotFound("File content is missing from storage.", code="FILE_CONTENT_MISSING")
    return FileResponse(
        path,
        media_type=record.content_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )


__all__ = ["AssignmentStatus", "router"]
