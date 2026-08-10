"""HTTP API for statement-to-ledger reconciliation."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError

from finance_api.deps import get_conn, get_settings
from finance_api.deps_ledger import require_ledger_writes
from finance_api.schemas.recon import (
    AdjustmentBody,
    AdjustmentResponse,
    ConfirmMatchBody,
    ConfirmMatchResponse,
    IgnoreLineBody,
    MatchProposalResponse,
    MatchResponse,
    MatchSuggestionsResponse,
    PeriodStatusResponse,
    StatementCreate,
    StatementCreated,
    StatementLineResponse,
    StatementResponse,
    StatementWorkspaceResponse,
)
from finance_api.services.transaction_import_service import load_rows_from_upload
from finance_api.settings import ApiSettings
from finance_common.parsing.bank_statement_pdf import (
    BankStatementPdfError,
    pdf_bytes_to_import_rows,
)
from finance_common.parsing.transaction_import import (
    ParsedImportRow,
    canonical_row_for_import,
    parse_import_row,
)
from finance_common.recon.models import NewStatement, ReconMatch, ReconStatement, ReconStatementLine
from finance_common.recon.service import PeriodStatus, ReconciliationError, ReconciliationService
from finance_common.repositories import recon as recon_repo

router = APIRouter(prefix="/recon", tags=["reconciliation"])


def _statement_response(statement: ReconStatement) -> StatementResponse:
    return StatementResponse(
        id=statement.id,
        account_id=statement.account_id,
        period_start=statement.period_start,
        period_end=statement.period_end,
        opening_balance_paise=statement.opening_balance_paise,
        closing_balance_paise=statement.closing_balance_paise,
        status=statement.status,
        source=statement.source,
        filename=statement.filename,
        created_at=statement.created_at,
        updated_at=statement.updated_at,
    )


def _line_response(line: ReconStatementLine) -> StatementLineResponse:
    return StatementLineResponse(
        id=line.id,
        statement_id=line.statement_id,
        tx_date=line.tx_date,
        amount_paise=line.amount_paise,
        direction=line.direction,
        payee=line.payee,
        narration=line.narration,
        external_key=line.external_key,
        status=line.status,
        ignore_reason=line.ignore_reason,
        created_at=line.created_at,
        updated_at=line.updated_at,
    )


def _match_response(match: ReconMatch) -> MatchResponse:
    return MatchResponse(
        id=match.id,
        line_id=match.line_id,
        ledger_transaction_id=match.ledger_transaction_id,
        method=match.method,
        confirmed_at=match.confirmed_at,
    )


def _period_status_response(status: PeriodStatus) -> PeriodStatusResponse:
    return PeriodStatusResponse(
        statement_id=status.statement_id,
        ledger_balance_paise=status.ledger_balance_paise,
        statement_closing_balance_paise=status.statement_closing_balance_paise,
        balance_difference_paise=status.balance_difference_paise,
        unmatched_line_count=status.unmatched_line_count,
        unmatched_ledger_count=status.unmatched_ledger_count,
        is_balanced=status.is_balanced,
        can_soft_close=status.can_soft_close,
    )


def _recon_error(exc: ReconciliationError) -> HTTPException:
    status_code = 404 if str(exc).endswith("does not exist") else 422
    return HTTPException(status_code=status_code, detail=str(exc))


def _statement_model(data: dict[str, Any]) -> StatementCreate:
    try:
        return StatementCreate.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


def _period_bounds(period: str) -> tuple[date, date]:
    for separator in ("/", "..", ",", " to "):
        if separator in period:
            start, end = (part.strip() for part in period.split(separator, maxsplit=1))
            try:
                return date.fromisoformat(start), date.fromisoformat(end)
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail="period must contain two ISO dates",
                ) from exc
    raise HTTPException(status_code=422, detail="period must contain a start and end date")


def _parsed_rows(rows: list[dict[str, str]]) -> list[ParsedImportRow]:
    parsed: list[ParsedImportRow] = []
    for index, raw in enumerate(rows, start=2):
        canonical = canonical_row_for_import(raw)
        if "date" not in canonical or "amount" not in canonical:
            raise HTTPException(
                status_code=422,
                detail=f"row {index}: could not find date and amount columns",
            )
        try:
            parsed.append(parse_import_row(canonical))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"row {index}: {exc}") from exc
    return parsed


async def _create_from_upload(
    request: Request,
    conn: aiosqlite.Connection,
    settings: ApiSettings,
) -> StatementCreated:
    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "read") or not hasattr(upload, "filename"):
        raise HTTPException(status_code=422, detail="file is required for multipart import")

    account_id = form.get("account_id")
    period = form.get("period")
    if account_id is None or period is None:
        raise HTTPException(status_code=422, detail="account_id and period are required")
    period_start, period_end = _period_bounds(str(period))
    model = _statement_model(
        {
            "account_id": account_id,
            "period_start": period_start,
            "period_end": period_end,
            "opening_balance_paise": form.get("opening_balance_paise"),
            "closing_balance_paise": form.get("closing_balance_paise"),
            "source": form.get("source") or "upload",
            "filename": upload.filename,
        }
    )
    content = await upload.read()
    filename = upload.filename or "statement"
    password_value = form.get("password")
    password = password_value if isinstance(password_value, str) else None
    try:
        if filename.lower().endswith(".pdf"):
            rows = await pdf_bytes_to_import_rows(content, settings, password=password)
        else:
            rows = load_rows_from_upload(filename, content, password=password)
    except (BankStatementPdfError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    statement_id = await ReconciliationService(conn).import_rows(
        NewStatement(
            account_id=model.account_id,
            period_start=model.period_start,
            period_end=model.period_end,
            opening_balance_paise=model.opening_balance_paise,
            closing_balance_paise=model.closing_balance_paise,
            source=model.source,
            filename=model.filename,
        ),
        _parsed_rows(rows),
    )
    return StatementCreated(id=statement_id, line_count=len(rows))


@router.get("/statements", response_model=list[StatementResponse])
async def list_statements(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    account_id: int = Query(gt=0),
) -> list[StatementResponse]:
    statements = await recon_repo.list_statements_by_account(conn, account_id)
    return [_statement_response(row) for row in statements]


@router.post("/statements", response_model=StatementCreated, status_code=201)
async def create_statement(
    request: Request,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    settings: Annotated[ApiSettings, Depends(get_settings)],
) -> StatementCreated:
    """Create an empty workspace from JSON, or import lines from a multipart statement."""
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        return await _create_from_upload(request, conn, settings)
    try:
        data = await request.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="Expected statement JSON or multipart upload",
        ) from exc
    model = _statement_model(data)
    statement_id = await ReconciliationService(conn).import_rows(
        NewStatement(
            account_id=model.account_id,
            period_start=model.period_start,
            period_end=model.period_end,
            opening_balance_paise=model.opening_balance_paise,
            closing_balance_paise=model.closing_balance_paise,
            source=model.source,
            filename=model.filename,
        ),
        (),
    )
    return StatementCreated(id=statement_id, line_count=0)


@router.get("/statements/{statement_id}", response_model=StatementWorkspaceResponse)
async def get_statement(
    statement_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> StatementWorkspaceResponse:
    service = ReconciliationService(conn)
    try:
        workspace = await service._workspace(statement_id)
        status = await service.period_status(statement_id)
    except ReconciliationError as exc:
        raise _recon_error(exc) from exc
    return StatementWorkspaceResponse(
        statement=_statement_response(workspace.statement),
        lines=[_line_response(line) for line in workspace.lines],
        matches=[_match_response(match) for match in workspace.matches],
        period_status=_period_status_response(status),
    )


@router.post("/statements/{statement_id}/suggest", response_model=MatchSuggestionsResponse)
async def suggest_matches(
    statement_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> MatchSuggestionsResponse:
    try:
        proposals = await ReconciliationService(conn).suggest_matches(statement_id)
    except ReconciliationError as exc:
        raise _recon_error(exc) from exc
    return MatchSuggestionsResponse(
        proposals=[
            MatchProposalResponse(
                line_id=proposal.line_id,
                ledger_transaction_id=proposal.ledger_transaction_id,
                score=proposal.score,
                reasons=list(proposal.reasons),
            )
            for proposal in proposals
        ]
    )


@router.post(
    "/statements/{statement_id}/lines/{line_id}/confirm",
    response_model=ConfirmMatchResponse,
)
async def confirm_match(
    statement_id: int,
    line_id: int,
    body: ConfirmMatchBody,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> ConfirmMatchResponse:
    try:
        match_id = await ReconciliationService(conn).confirm_match(
            statement_id,
            line_id,
            body.ledger_transaction_id,
            method=body.method,
        )
    except ReconciliationError as exc:
        raise _recon_error(exc) from exc
    return ConfirmMatchResponse(match_id=match_id, line_status="matched")


@router.post("/statements/{statement_id}/lines/{line_id}/unmatch", status_code=204)
async def unmatch(
    statement_id: int,
    line_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> Response:
    try:
        await ReconciliationService(conn).unmatch(statement_id, line_id)
    except ReconciliationError as exc:
        raise _recon_error(exc) from exc
    return Response(status_code=204)


@router.post("/statements/{statement_id}/lines/{line_id}/ignore", status_code=204)
async def ignore_line(
    statement_id: int,
    line_id: int,
    body: IgnoreLineBody,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> Response:
    try:
        await ReconciliationService(conn).ignore_line(statement_id, line_id, body.reason)
    except ReconciliationError as exc:
        raise _recon_error(exc) from exc
    return Response(status_code=204)


@router.post("/statements/{statement_id}/adjust", response_model=AdjustmentResponse)
async def create_adjustment(
    statement_id: int,
    body: AdjustmentBody,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    _: Annotated[None, Depends(require_ledger_writes)],
) -> AdjustmentResponse:
    try:
        transaction_id = await ReconciliationService(conn).create_adjustment(
            statement_id,
            body.line_id,
            counterpart_account_id=body.counterpart_account_id,
            category=body.category,
            payee=body.payee,
            notes=body.notes,
        )
    except ReconciliationError as exc:
        raise _recon_error(exc) from exc
    return AdjustmentResponse(ledger_transaction_id=transaction_id, line_id=body.line_id)


@router.post("/statements/{statement_id}/soft-close", response_model=PeriodStatusResponse)
async def soft_close(
    statement_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> PeriodStatusResponse:
    try:
        status = await ReconciliationService(conn).soft_close(statement_id)
    except ReconciliationError as exc:
        raise _recon_error(exc) from exc
    return _period_status_response(status)


@router.post("/statements/{statement_id}/reopen", status_code=204)
async def reopen(
    statement_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> Response:
    try:
        await ReconciliationService(conn).reopen(statement_id)
    except ReconciliationError as exc:
        raise _recon_error(exc) from exc
    return Response(status_code=204)
