"""Prompt Firewall - analyzes final assembled prompts before LLM execution.

This layer checks the complete prompt (system + user input) for injection attempts.
"""

import logging
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class FirewallDecision:
    """Decision from prompt firewall."""

    action: Literal["allow", "block", "warn"]
    reason: str
    threat_score: float  # 0-1
    modified_prompt: str | None = None


class PromptFirewall:
    """Analyzes assembled prompts before sending to LLM."""

    # Patterns that indicate delimiter escape attempts
    ESCAPE_PATTERNS = [
        "</user_input>",
        "</candidate_input>",
        "</learner_input>",
        "</context>",
        "<system>",
        "<|endoftext|>",
        "[/INST]",
        "```end",
    ]

    # Patterns indicating instruction override in assembled prompt
    OVERRIDE_PATTERNS = [
        "ignore the above",
        "disregard previous",
        "new instructions:",
        "updated instructions:",
        "system override",
    ]

    def analyze(self, prompt: str, user_input: str) -> FirewallDecision:
        """Analyze the assembled prompt for injection attacks.

        Args:
            prompt: The complete assembled prompt
            user_input: The original user input (for reference)

        Returns:
            FirewallDecision with action to take
        """
        threat_score = 0.0
        reasons = []

        # Check 1: Delimiter escape attempts
        for escape in self.ESCAPE_PATTERNS:
            if escape.lower() in user_input.lower():
                threat_score += 0.5
                reasons.append(f"Delimiter escape attempt: {escape}")
                logger.warning(f"Firewall: Delimiter escape detected: {escape}")

        # Check 2: Instruction override in user section
        for override in self.OVERRIDE_PATTERNS:
            if override.lower() in user_input.lower():
                threat_score += 0.4
                reasons.append(f"Instruction override: {override}")

        # Check 3: Role confusion (multiple "You are" statements)
        you_are_count = prompt.lower().count("you are")
        if you_are_count > 2:  # System prompt + 1 acceptable reference
            threat_score += 0.3
            reasons.append(f"Multiple role definitions detected ({you_are_count})")

        # Check 4: Unusual prompt structure (trying to break out of context)
        newline_count = user_input.count("\n\n\n")  # Excessive newlines
        if newline_count > 2:
            threat_score += 0.2
            reasons.append("Excessive whitespace (structure manipulation)")

        # Decide action
        if threat_score >= 0.7:
            return FirewallDecision(
                action="block",
                reason="; ".join(reasons),
                threat_score=threat_score,
            )
        elif threat_score >= 0.4:
            return FirewallDecision(
                action="warn",
                reason="; ".join(reasons),
                threat_score=threat_score,
            )
        else:
            return FirewallDecision(
                action="allow",
                reason="No threats detected",
                threat_score=threat_score,
            )


# Global instance
_firewall = None


def get_firewall() -> PromptFirewall:
    """Get singleton firewall instance."""
    global _firewall
    if _firewall is None:
        _firewall = PromptFirewall()
    return _firewall
