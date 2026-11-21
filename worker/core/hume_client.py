"""Hume.AI API client for emotional analysis.

Provides wrapper around Hume.AI Expression Measurement Batch API
for analyzing voice prosody in interview recordings.
"""

import logging
from typing import Any

from hume import AsyncHumeClient
from hume.expression_measurement.batch import Models, Prosody

from core.config import settings

logger = logging.getLogger(__name__)


class HumeEmotionalAnalyzer:
    """Client for Hume.AI voice prosody analysis."""

    def __init__(self, api_key: str | None = None):
        """Initialize Hume client.

        Args:
            api_key: Optional API key override (defaults to settings)
        """
        key = api_key or settings.hume_api_key
        if not key:
            raise ValueError("Hume API key not configured. Set HUME_API_KEY environment variable.")

        self.client = AsyncHumeClient(api_key=key)

    async def submit_video_for_analysis(
        self, video_url: str, session_id: str, callback_url: str | None = None
    ) -> str:
        """Submit video to Hume for voice prosody analysis.

        Args:
            video_url: Public URL of the video file to analyze
            session_id: Interview session ID for tracking
            callback_url: Optional webhook URL for completion notification

        Returns:
            job_id: Hume job ID for polling status
        """
        try:
            # Configure prosody model (voice analysis)
            prosody_config = Prosody()

            # Create models configuration
            models = Models(prosody=prosody_config)

            # Submit job
            logger.info(
                f"[HUME_DEBUG] Submitting video to Hume.AI for session {session_id}: {video_url}"
            )

            job_id = await self.client.expression_measurement.batch.start_inference_job(
                urls=[video_url],
                models=models,
                callback_url=callback_url or settings.hume_callback_url,
            )

            logger.info(
                f"[HUME_DEBUG] Hume job submitted successfully: session={session_id}, job_id={job_id}"
            )
            return job_id

        except Exception as e:
            logger.error(f"[HUME_DEBUG] Failed to submit video to Hume.AI: {e}", exc_info=True)
            raise

    async def get_job_status(self, job_id: str) -> str:
        """Check job status.

        Args:
            job_id: Hume job ID

        Returns:
            Status string: QUEUED, IN_PROGRESS, COMPLETED, FAILED
        """
        try:
            logger.info(f"[HUME_DEBUG] Getting job status for {job_id}")
            job_details = await self.client.expression_measurement.batch.get_job_details(job_id)
            status = job_details.state.status
            logger.info(f"[HUME_DEBUG] Job {job_id} status: {status}")
            return status

        except Exception as e:
            logger.error(
                f"[HUME_DEBUG] Failed to get Hume job status for {job_id}: {e}", exc_info=True
            )
            raise

    async def get_results(self, job_id: str) -> list[dict[str, Any]]:
        """Fetch emotional analysis results.

        Args:
            job_id: Hume job ID

        Returns:
            List of prediction results with emotional scores
        """
        try:
            logger.info(f"[HUME_DEBUG] Fetching results for Hume job {job_id}")
            predictions = await self.client.expression_measurement.batch.get_job_predictions(job_id)
            logger.info(
                f"[HUME_DEBUG] Got predictions for job {job_id}: "
                f"{len(predictions) if predictions else 0} items"
            )

            # Convert to dict format for easier processing
            return predictions

        except Exception as e:
            logger.error(
                f"[HUME_DEBUG] Failed to fetch Hume results for {job_id}: {e}", exc_info=True
            )
            raise

    async def close(self):
        """Close the Hume client connection."""
        # AsyncHumeClient doesn't require explicit cleanup in current version
        pass


# Global client instance (lazy-loaded)
_hume_client: HumeEmotionalAnalyzer | None = None


async def get_hume_client() -> HumeEmotionalAnalyzer:
    """Get singleton Hume client instance.

    Returns:
        Initialized HumeEmotionalAnalyzer instance
    """
    global _hume_client
    if _hume_client is None:
        _hume_client = HumeEmotionalAnalyzer()
    return _hume_client
