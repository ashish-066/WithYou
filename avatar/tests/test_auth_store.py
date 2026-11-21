"""Postgres-backed auth store behaviour that HTTP tests can't easily force."""

import asyncio
from datetime import timedelta

import pytest

from core.auth import AuthStore


async def make_invite(store: AuthStore):
    org_id = await store.create_org("Acme")
    user_id = await store.create_user(
        email="a@acme.test", name="A", password="correct-horse-1", org_id=org_id, role="admin"
    )
    invite_id, _, _ = await store.create_invite(
        org_id=org_id, created_by=user_id, ttl=timedelta(hours=1),
        candidate_name="Cara", interview_mode="round1",
    )
    return invite_id


async def test_concurrent_invite_claims_only_one_wins(db):
    store = AuthStore()
    invite_id = await make_invite(store)

    results = await asyncio.gather(
        *(store.consume_invite(invite_id, f"session-{i}") for i in range(10))
    )

    assert results.count(True) == 1
    winner = f"session-{results.index(True)}"
    assert (await store.get_invite(invite_id))["used_session_id"] == winner


async def test_release_lets_the_invite_be_used_again(db):
    store = AuthStore()
    invite_id = await make_invite(store)
    assert await store.consume_invite(invite_id, "session-1")

    await store.release_invite(invite_id)

    assert await store.consume_invite(invite_id, "session-2")


async def test_email_is_unique_case_insensitively(db):
    store = AuthStore()
    org_id = await store.create_org("Acme")
    await store.create_user(
        email="Ann@Acme.test", name="A", password="correct-horse-1", org_id=org_id, role="admin"
    )
    with pytest.raises(ValueError):
        await store.create_user(
            email="ann@acme.TEST", name="B", password="correct-horse-1", org_id=org_id, role="admin"
        )
    assert await store.authenticate("ANN@acme.test", "correct-horse-1")
