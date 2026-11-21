"""Anti-cheating detection and integrity scoring service.

This module provides server-side processing of proctoring events and
calculates integrity scores based on detected violations.

The detection itself happens on the client-side (camera/microphone analysis)
or through behavioral analysis of candidate responses. This service:
1. Receives and validates cheat flags from the avatar service
2. Calculates severity weights and integrity scores
3. Generates integrity reports at interview conclusion
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from brain.state import CheatFlag, IntegrityReport, InterviewState

logger = logging.getLogger(__name__)


# =============================================================================
# Severity Weights and Thresholds
# =============================================================================

# Weight multipliers for each flag type (higher = more severe impact on score)
FLAG_TYPE_WEIGHTS: dict[str, float] = {
    "multiple_faces": 0.15,  # High concern - someone else present
    "no_face": 0.05,  # Low concern - could be camera issue
    "phone_detected": 0.12,  # High concern - looking up answers
    "earphone_detected": 0.10,  # Medium concern - possible coaching
    "tab_switch": 0.08,  # Medium concern - could be checking notes
    "screen_share": 0.15,  # High concern - sharing questions
    "voice_change": 0.12,  # High concern - different speaker
    "copy_paste": 0.10,  # Medium concern - using prepared answers
    "ai_assistance": 0.15,  # High concern - AI-generated responses
    "suspicious_timing": 0.05,  # Low concern - needs context
    "blocked_app": 0.12,  # High concern - remote control, AI or recording app open
    "second_screen": 0.12,  # High concern - another screen in reach
    "app_closed": 0.12,  # High concern - left before submitting, could be a crash
    "exit_attempt": 0.02,  # Low concern - often an accident
    "emergency_exit": 0.08,  # Medium concern - may be a real emergency
    "lock_expired": 0.01,  # Low concern - a time limit, not the candidate's action
    "browser_mode": 0.05,  # Low concern - allowed, but with fewer safeguards
}

# Severity multipliers
SEVERITY_MULTIPLIERS: dict[str, float] = {
    "low": 0.5,
    "medium": 1.0,
    "high": 1.5,
    "critical": 2.0,
}

# Thresholds for integrity recommendations
INTEGRITY_THRESHOLDS = {
    "proceed": 0.85,  # >= 85% integrity
    "review": 0.70,  # 70-85% needs review
    "flag": 0.50,  # 50-70% significant issues
    # < 50% = reject
}


# =============================================================================
# Anti-Cheat Service
# =============================================================================


class AntiCheatService:
    """Service for processing anti-cheating events and calculating integrity."""

    def __init__(self):
        self.flag_weights = FLAG_TYPE_WEIGHTS
        self.severity_multipliers = SEVERITY_MULTIPLIERS

    def create_cheat_flag(
        self,
        flag_type: str,
        severity: str,
        confidence: float,
        description: str,
        turn_number: int,
        evidence: str | None = None,
    ) -> CheatFlag:
        """Create a new cheat flag with validation.

        Args:
            flag_type: Type of cheating detected
            severity: Severity level (low, medium, high, critical)
            confidence: Detection confidence (0-1)
            description: Human-readable description
            turn_number: Interview turn when detected
            evidence: Optional additional evidence
        """
        return CheatFlag(
            id=str(uuid.uuid4()),
            flag_type=flag_type,  # type: ignore
            severity=severity,  # type: ignore
            confidence=max(0.0, min(1.0, confidence)),
            description=description,
            evidence=evidence,
            timestamp=datetime.now(timezone.utc).isoformat(),
            turn_number=turn_number,
        )

    def calculate_integrity_score(self, flags: list[CheatFlag]) -> float:
        """Calculate overall integrity score based on accumulated flags.

        The score starts at 1.0 and decreases based on:
        - Flag type weight
        - Severity multiplier
        - Detection confidence
        - Diminishing returns for repeated flags of same type

        Args:
            flags: List of detected cheat flags
        """
        if not flags:
            return 1.0

        # Track flags by type for diminishing returns
        type_counts: dict[str, int] = {}
        total_penalty = 0.0

        for flag in flags:
            flag_type = flag["flag_type"]
            severity = flag["severity"]
            confidence = flag["confidence"]

            # Get base weight for this flag type
            base_weight = self.flag_weights.get(flag_type, 0.05)

            # Apply severity multiplier
            severity_mult = self.severity_multipliers.get(severity, 1.0)

            # Apply confidence scaling
            confidence_mult = confidence

            # Apply diminishing returns for repeated flags of same type
            type_counts[flag_type] = type_counts.get(flag_type, 0) + 1
            repetition_factor = 1.0 / (1.0 + 0.3 * (type_counts[flag_type] - 1))

            # Calculate penalty for this flag
            penalty = base_weight * severity_mult * confidence_mult * repetition_factor
            total_penalty += penalty

        # Score is 1.0 minus penalties, clamped to [0, 1]
        score = max(0.0, min(1.0, 1.0 - total_penalty))
        return round(score, 3)

    def add_flag_to_state(
        self,
        state: InterviewState,
        flag: CheatFlag,
    ) -> InterviewState:
        """Add a cheat flag to the interview state and recalculate integrity.

        Args:
            state: Current interview state
            flag: New cheat flag to add
        """
        # Add flag to list
        cheat_flags = list(state.get("cheat_flags", []))
        cheat_flags.append(flag)
        state["cheat_flags"] = cheat_flags

        # Recalculate integrity score
        state["integrity_score"] = self.calculate_integrity_score(cheat_flags)

        logger.info(
            f"Cheat flag added: {flag['flag_type']} ({flag['severity']}) - "
            f"integrity now {state['integrity_score']:.2f}"
        )

        return state

    def generate_integrity_report(self, state: InterviewState) -> IntegrityReport:
        """Generate a comprehensive integrity report for the interview.

        Args:
            state: Final interview state
        """
        flags = state.get("cheat_flags", [])
        integrity_score = state.get("integrity_score", 1.0)

        # Count flags by type
        flags_by_type: dict[str, int] = {}
        for flag in flags:
            flag_type = flag["flag_type"]
            flags_by_type[flag_type] = flags_by_type.get(flag_type, 0) + 1

        # Count flags by severity
        flags_by_severity: dict[str, int] = {}
        for flag in flags:
            severity = flag["severity"]
            flags_by_severity[severity] = flags_by_severity.get(severity, 0) + 1

        # Get critical incidents (high/critical severity)
        critical_incidents = [flag for flag in flags if flag["severity"] in ("high", "critical")]

        # Determine recommendation
        recommendation = self._get_recommendation(
            integrity_score, flags_by_severity, critical_incidents
        )

        # Generate summary
        summary = self._generate_summary(flags, integrity_score, flags_by_type, recommendation)

        report = IntegrityReport(
            integrity_score=integrity_score,
            total_flags=len(flags),
            flags_by_type=flags_by_type,
            flags_by_severity=flags_by_severity,
            critical_incidents=critical_incidents,
            timeline=sorted(flags, key=lambda f: f["timestamp"]),
            recommendation=recommendation,
            summary=summary,
        )

        logger.info(
            f"Integrity report generated: score={integrity_score:.2f}, "
            f"recommendation={recommendation}"
        )

        return report

    def _get_recommendation(
        self,
        integrity_score: float,
        flags_by_severity: dict[str, int],
        critical_incidents: list[CheatFlag],
    ) -> Literal["proceed", "review", "flag", "reject"]:
        """Determine the integrity recommendation based on score and flags."""
        # Immediate rejection for multiple critical flags
        if flags_by_severity.get("critical", 0) >= 2:
            return "reject"

        # Check for specific high-concern combinations
        high_count = flags_by_severity.get("high", 0)
        critical_count = flags_by_severity.get("critical", 0)

        if critical_count >= 1 and high_count >= 2:
            return "reject"

        # Score-based recommendation
        if integrity_score >= INTEGRITY_THRESHOLDS["proceed"]:
            return "proceed"
        elif integrity_score >= INTEGRITY_THRESHOLDS["review"]:
            return "review"
        elif integrity_score >= INTEGRITY_THRESHOLDS["flag"]:
            return "flag"
        else:
            return "reject"

    def _generate_summary(
        self,
        flags: list[CheatFlag],
        integrity_score: float,
        flags_by_type: dict[str, int],
        recommendation: str,
    ) -> str:
        """Generate a human-readable summary of integrity concerns."""
        if not flags:
            return "No integrity issues detected during the interview."

        parts = []

        # Overall assessment
        if integrity_score >= 0.9:
            parts.append("Minor integrity concerns were detected during the interview.")
        elif integrity_score >= 0.7:
            parts.append("Moderate integrity concerns were detected during the interview.")
        elif integrity_score >= 0.5:
            parts.append("Significant integrity concerns were detected during the interview.")
        else:
            parts.append("Critical integrity violations were detected during the interview.")

        # Specific issues
        issues = []
        if flags_by_type.get("multiple_faces", 0) > 0:
            count = flags_by_type["multiple_faces"]
            issues.append(f"multiple faces detected {count} time(s)")
        if flags_by_type.get("phone_detected", 0) > 0:
            count = flags_by_type["phone_detected"]
            issues.append(f"mobile phone visible {count} time(s)")
        if flags_by_type.get("earphone_detected", 0) > 0:
            count = flags_by_type["earphone_detected"]
            issues.append(f"earphone/earbud detected {count} time(s)")
        if flags_by_type.get("tab_switch", 0) > 0:
            count = flags_by_type["tab_switch"]
            issues.append(f"browser tab switched {count} time(s)")
        if flags_by_type.get("ai_assistance", 0) > 0:
            count = flags_by_type["ai_assistance"]
            issues.append(f"suspected AI assistance {count} time(s)")

        if issues:
            parts.append(f"Issues include: {', '.join(issues)}.")

        # Recommendation
        if recommendation == "proceed":
            parts.append("Recommendation: Proceed with candidate evaluation.")
        elif recommendation == "review":
            parts.append("Recommendation: Human review of flagged incidents advised.")
        elif recommendation == "flag":
            parts.append(
                "Recommendation: Interview integrity may be compromised. Detailed review required."
            )
        else:
            parts.append(
                "Recommendation: Significant integrity violations. Consider interview invalid."
            )

        return " ".join(parts)


# =============================================================================
# Singleton Instance
# =============================================================================

anti_cheat_service = AntiCheatService()
