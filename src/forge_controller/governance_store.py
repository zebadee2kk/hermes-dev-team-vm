from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .governance import (
    DenialOutcome,
    DenialPolicy,
    DenialState,
    record_policy_denial,
    record_safe_alternative_success,
)
from .persistence import GovernanceDenialStateRow, ensure_utc, utcnow


class GovernanceDenialStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def record_denial(
        self,
        *,
        project_id: str,
        task_id: str,
        signature: str,
        reason: str,
        policy: DenialPolicy | None = None,
        material: bool = False,
        now: datetime | None = None,
    ) -> DenialOutcome:
        try:
            return await self._record_denial_once(
                project_id=project_id,
                task_id=task_id,
                signature=signature,
                reason=reason,
                policy=policy,
                material=material,
                now=now,
            )
        except IntegrityError:
            # Two first observations can race to create the same scoped row. The unique constraint
            # rejects one insert; retry against the now-existing row rather than losing recurrence.
            return await self._record_denial_once(
                project_id=project_id,
                task_id=task_id,
                signature=signature,
                reason=reason,
                policy=policy,
                material=material,
                now=now,
            )

    async def _record_denial_once(
        self,
        *,
        project_id: str,
        task_id: str,
        signature: str,
        reason: str,
        policy: DenialPolicy | None,
        material: bool,
        now: datetime | None,
    ) -> DenialOutcome:
        async with self.sessions.begin() as session:
            row = await self._row_for_update(session, project_id, task_id, signature)
            state = self._state(row, signature)
            outcome = record_policy_denial(
                state,
                reason=reason,
                policy=policy,
                material=material,
                now=now,
            )
            self._persist(session, row, project_id, task_id, outcome.state)
            return outcome

    async def record_safe_alternative(
        self,
        *,
        project_id: str,
        task_id: str,
        signature: str,
    ) -> DenialState:
        async with self.sessions.begin() as session:
            row = await self._row_for_update(session, project_id, task_id, signature)
            if row is None:
                return DenialState(signature=signature)
            state = record_safe_alternative_success(self._state(row, signature))
            self._persist(session, row, project_id, task_id, state)
            return state

    async def get_state(
        self,
        *,
        project_id: str,
        task_id: str,
        signature: str,
    ) -> DenialState:
        async with self.sessions() as session:
            stmt = select(GovernanceDenialStateRow).where(
                GovernanceDenialStateRow.project_id == project_id,
                GovernanceDenialStateRow.task_id == task_id,
                GovernanceDenialStateRow.signature == signature,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return self._state(row, signature)

    @staticmethod
    async def _row_for_update(
        session: AsyncSession,
        project_id: str,
        task_id: str,
        signature: str,
    ) -> GovernanceDenialStateRow | None:
        stmt = (
            select(GovernanceDenialStateRow)
            .where(
                GovernanceDenialStateRow.project_id == project_id,
                GovernanceDenialStateRow.task_id == task_id,
                GovernanceDenialStateRow.signature == signature,
            )
            .with_for_update()
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    def _state(row: GovernanceDenialStateRow | None, signature: str) -> DenialState:
        if row is None:
            return DenialState(signature=signature)
        return DenialState(
            signature=row.signature,
            consecutive=row.consecutive,
            total=row.total,
            last_reason=row.last_reason,
            last_denied_at=ensure_utc(row.last_denied_at),
        )

    @staticmethod
    def _persist(
        session: AsyncSession,
        row: GovernanceDenialStateRow | None,
        project_id: str,
        task_id: str,
        state: DenialState,
    ) -> None:
        values = {
            "project_id": project_id,
            "task_id": task_id,
            "signature": state.signature,
            "consecutive": state.consecutive,
            "total": state.total,
            "last_reason": state.last_reason,
            "last_denied_at": state.last_denied_at,
            "updated_at": utcnow(),
        }
        if row is None:
            session.add(GovernanceDenialStateRow(state_id=str(uuid4()), **values))
            return
        for key, value in values.items():
            setattr(row, key, value)
