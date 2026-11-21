"""Background claim verification service.

Runs claim verification asynchronously without blocking the conversation flow.
Results are stored in Redis and merged into state on the next turn.

Architecture:
    Fast Brain completes
           |
           +---> Response returned to user (no delay)
           |
           +---> asyncio.create_task(run_background_verification(...))
                        |
                        v
                 verify claims asynchronously
                        |
                        v
                 Results stored to Redis: verified_results:{session_id}
                        |
                        v
                 Next turn: input_processor_node merges results into state
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from core.redis import redis_client

logger = logging.getLogger(__name__)

# Redis key patterns
VERIFIED_RESULTS_KEY = "verified_results:{session_id}"
VERIFICATION_LOCK_KEY = "verification_lock:{session_id}"

# Configuration
RESULTS_TTL_SECONDS = 3600  # 1 hour TTL for results
LOCK_TTL_SECONDS = 60  # 1 minute lock to prevent duplicate verifications


async def run_background_verification(
    session_id: str,
    claims: list[dict[str, Any]],
    candidate_profile: dict[str, Any] | None,
) -> None:
    """Run claim verification in the background.

    Verifies claims against the candidate profile and stores results in Redis
    for later retrieval by the input processor.

    Args:
        session_id: The interview session ID
        claims: List of Claim dicts to verify
        candidate_profile: Candidate profile data for verification
    """
    if not claims:
        return

    logger.info(f"[BG_VERIFY] Session {session_id}: Starting verification of {len(claims)} claims")

    try:
        # Import here to avoid circular imports
        from brain.brains.slow_brain import _calculate_trust_score, _verify_single_claim
        from brain.state import VerificationResult

        # Acquire lock to prevent duplicate verification runs
        async with redis_client() as redis:
            lock_key = VERIFICATION_LOCK_KEY.format(session_id=session_id)
            lock_acquired = await redis.set(lock_key, "1", nx=True, ex=LOCK_TTL_SECONDS)
            if not lock_acquired:
                logger.debug(f"[BG_VERIFY] Session {session_id}: Verification already in progress")
                return

        # Check all claims against the background in one model call; claims it
        # didn't answer (or if it failed) get the simple keyword check
        from brain.candidate_background import verify_claims

        verified_claims: list[dict[str, Any]] = list(await verify_claims(claims, candidate_profile) or [])
        done = {str((r.get("claim") or {}).get("id")) for r in verified_claims}

        for claim in [c for c in claims if str(c.get("id")) not in done]:
            try:
                if candidate_profile:
                    result = await _verify_single_claim(claim, candidate_profile)
                else:
                    # No profile data - mark as unverified (no trust penalty)
                    result = VerificationResult(
                        claim=claim,
                        evidence=[],
                        verdict="unverified",
                        confidence=0.0,
                        reasoning="No candidate profile data available for verification",
                        suggested_followup=None,
                    )
                verified_claims.append(dict(result))
            except Exception as e:
                logger.error(
                    f"[BG_VERIFY] Session {session_id}: Failed to verify claim "
                    f"{claim.get('id', 'unknown')}: {e}"
                )
                # Mark as unverified on error
                verified_claims.append(
                    {
                        "claim": claim,
                        "evidence": [],
                        "verdict": "unverified",
                        "confidence": 0.0,
                        "reasoning": f"Verification error: {str(e)[:100]}",
                        "suggested_followup": None,
                    }
                )

        # Calculate trust score from newly verified claims
        trust_score = _calculate_trust_score(verified_claims)

        # Store results in Redis
        async with redis_client() as redis:
            results_key = VERIFIED_RESULTS_KEY.format(session_id=session_id)

            # Check if there are existing results to merge with
            existing_data = await redis.get(results_key)
            if existing_data:
                existing = json.loads(existing_data)
                existing_claims = existing.get("verified_claims", [])
                # Merge new claims with existing
                all_claims = existing_claims + verified_claims
                # Recalculate trust score with all claims
                trust_score = _calculate_trust_score(all_claims)
                verified_claims = all_claims

            results_data = {
                "verified_claims": verified_claims,
                "trust_score": trust_score,
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "claim_count": len(verified_claims),
            }
            await redis.set(results_key, json.dumps(results_data), ex=RESULTS_TTL_SECONDS)

            # Release lock
            lock_key = VERIFICATION_LOCK_KEY.format(session_id=session_id)
            await redis.delete(lock_key)

        logger.info(
            f"[BG_VERIFY] Session {session_id}: Verified {len(claims)} claims, "
            f"total verified: {len(verified_claims)}, trust_score={trust_score:.2f}"
        )

    except Exception as e:
        logger.error(f"[BG_VERIFY] Session {session_id}: Verification failed: {e}")
        # Clean up lock on failure
        try:
            async with redis_client() as redis:
                lock_key = VERIFICATION_LOCK_KEY.format(session_id=session_id)
                await redis.delete(lock_key)
        except Exception:
            pass


async def get_pending_verification_results(session_id: str) -> dict[str, Any] | None:
    """Retrieve and clear pending verification results from Redis.

    This is called by input_processor_node to merge background verification
    results into the conversation state.

    Args:
        session_id: The interview session ID

    Returns:
        Dict containing verified_claims, trust_score, etc. or None if no results.
    """
    try:
        async with redis_client() as redis:
            results_key = VERIFIED_RESULTS_KEY.format(session_id=session_id)

            # Get and delete atomically using pipeline
            pipe = redis.pipeline()
            pipe.get(results_key)
            pipe.delete(results_key)
            results = await pipe.execute()

            results_data = results[0]
            if results_data:
                return json.loads(results_data)
            return None

    except Exception as e:
        logger.error(f"[BG_VERIFY] Failed to get results for {session_id}: {e}")
        return None


def trigger_background_verification(
    session_id: str,
    claims: list[dict[str, Any]],
    candidate_profile: dict[str, Any] | None,
) -> None:
    """Trigger background verification as an async task.

    This is the main entry point called from fast_brain's respond_node.
    It spawns a background task that runs verification without blocking.

    Args:
        session_id: The interview session ID
        claims: List of Claim dicts to verify
        candidate_profile: Candidate profile data for verification
    """
    if not claims:
        return

    # Create background task
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(
            run_background_verification(session_id, claims, candidate_profile),
            name=f"bg_verify_{session_id}",
        )
        logger.debug(
            f"[BG_VERIFY] Triggered background verification for {session_id} "
            f"with {len(claims)} claims"
        )
    except RuntimeError:
        # No running event loop - this shouldn't happen in normal operation
        logger.error(f"[BG_VERIFY] No event loop for background verification in {session_id}")


async def clear_verification_results(session_id: str) -> None:
    """Clear any pending verification results for a session.

    Called when an interview ends to clean up Redis state.

    Args:
        session_id: The interview session ID
    """
    try:
        async with redis_client() as redis:
            results_key = VERIFIED_RESULTS_KEY.format(session_id=session_id)
            lock_key = VERIFICATION_LOCK_KEY.format(session_id=session_id)
            await redis.delete(results_key, lock_key)
            logger.debug(f"[BG_VERIFY] Cleared verification state for {session_id}")
    except Exception as e:
        logger.error(f"[BG_VERIFY] Failed to clear state for {session_id}: {e}")
