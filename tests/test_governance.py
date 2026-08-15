from datetime import UTC, datetime

import pytest

from forge_controller.assurance import DecisionRecord, DecisionStatus
from forge_controller.governance import (
    DecisionDisposition,
    DenialDirective,
    DenialPolicy,
    DenialState,
    GovernanceError,
    apply_owner_action,
    build_decision_prompt,
    record_policy_denial,
    record_safe_alternative_success,
)
from forge_controller.models import AuthorityLevel, DecisionAction, DecisionClassification

NOW = datetime(2026, 8, 15, 23, 35, tzinfo=UTC)


def _record(level: AuthorityLevel = AuthorityLevel.L2) -> DecisionRecord:
    return DecisionRecord(
        decision_id="decision-1",
        project_id="forge",
        task_id="task-1",
        question="Deploy this material architecture change?",
        recommendation="YES — evidence is current.",
        authority=level,
        status=DecisionStatus.OPEN,
    )


def _classification(
    level: AuthorityLevel = AuthorityLevel.L2,
    *,
    defer_allowed: bool = True,
) -> DecisionClassification:
    return DecisionClassification(
        authority=level,
        autonomous=level in {AuthorityLevel.L0, AuthorityLevel.L1},
        defer_allowed=defer_allowed,
        score=0.8,
    )


def test_prompt_exposes_only_four_owner_choices_and_l3_omits_defer() -> None:
    prompt = build_decision_prompt(
        _record(),
        _classification(),
        why_now="Implementation is blocked on one material choice.",
        yes_effect="Proceed with the recommended architecture.",
        no_effect="Reject it and re-plan.",
    )
    assert prompt.options == (
        DecisionAction.YES,
        DecisionAction.NO,
        DecisionAction.DEFER,
        DecisionAction.MORE_INFO,
    )

    l3 = build_decision_prompt(
        _record(AuthorityLevel.L3),
        _classification(AuthorityLevel.L3, defer_allowed=False),
        why_now="A mandatory security boundary change needs approval.",
        yes_effect="Grant the bounded capability.",
        no_effect="Keep the capability denied.",
    )
    assert DecisionAction.DEFER not in l3.options
    assert set(l3.options) == {DecisionAction.YES, DecisionAction.NO, DecisionAction.MORE_INFO}


def test_yes_and_no_resolve_and_release_the_block() -> None:
    yes = apply_owner_action(_record(), _classification(), DecisionAction.YES, now=NOW)
    assert yes.disposition is DecisionDisposition.APPROVED
    assert yes.record.status is DecisionStatus.RESOLVED
    assert yes.record.owner_action is DecisionAction.YES
    assert yes.resume_task is True
    assert yes.keep_blocked is False

    no = apply_owner_action(_record(), _classification(), DecisionAction.NO, now=NOW)
    assert no.disposition is DecisionDisposition.DENIED
    assert no.record.status is DecisionStatus.RESOLVED
    assert no.record.owner_action is DecisionAction.NO
    assert no.resume_task is True


def test_defer_and_more_info_keep_decision_open_and_task_blocked() -> None:
    deferred = apply_owner_action(_record(), _classification(), DecisionAction.DEFER, now=NOW)
    assert deferred.disposition is DecisionDisposition.DEFERRED
    assert deferred.record.status is DecisionStatus.OPEN
    assert deferred.keep_blocked is True
    assert deferred.resume_task is False

    more = apply_owner_action(_record(), _classification(), DecisionAction.MORE_INFO, now=NOW)
    assert more.disposition is DecisionDisposition.NEEDS_INFO
    assert more.record.status is DecisionStatus.OPEN
    assert more.request_more_info is True
    assert more.keep_blocked is True


def test_l3_defer_is_rejected() -> None:
    with pytest.raises(GovernanceError, match="DEFER"):
        apply_owner_action(
            _record(AuthorityLevel.L3),
            _classification(AuthorityLevel.L3, defer_allowed=False),
            DecisionAction.DEFER,
            now=NOW,
        )


def test_deny_and_continue_only_interrupts_after_recurrence_or_material_denial() -> None:
    state = DenialState(signature="github:default-branch-push")
    policy = DenialPolicy(consecutive_before_escalate=3, total_before_escalate=5)

    first = record_policy_denial(state, reason="default branch denied", policy=policy, now=NOW)
    assert first.directive is DenialDirective.RETRY_SAFER_ALTERNATIVE
    assert first.owner_interrupt_required is False

    second = record_policy_denial(
        first.state,
        reason="default branch denied again",
        policy=policy,
        now=NOW,
    )
    assert second.directive is DenialDirective.RETRY_SAFER_ALTERNATIVE

    third = record_policy_denial(
        second.state,
        reason="third identical denial",
        policy=policy,
        now=NOW,
    )
    assert third.directive is DenialDirective.ESCALATE_HUMAN
    assert third.owner_interrupt_required is True

    material = record_policy_denial(
        DenialState(signature="prod-delete"),
        reason="irreversible production delete requested",
        policy=policy,
        material=True,
        now=NOW,
    )
    assert material.owner_interrupt_required is True


def test_safe_alternative_breaks_consecutive_streak_but_keeps_recurrence_count() -> None:
    state = DenialState(
        signature="github:push",
        consecutive=2,
        total=4,
        last_reason="unsafe push",
        last_denied_at=NOW,
    )
    reset = record_safe_alternative_success(state)
    assert reset.consecutive == 0
    assert reset.total == 4
    assert reset.last_reason is None
