"""Defect pattern analytics across every analyzed submission.

The five pipeline agents answer questions about one defect. This agent answers
questions about the portfolio: which failures keep coming back, which
components absorb them, and which problems are systemic rather than isolated.

Detection is rule-based and fully traceable. Every systemic pattern carries the
counts that triggered it, so a reviewer can verify the claim instead of
trusting a generated sentence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from models.analytics_models import (
    ComponentHotspot,
    DefectAnalyticsResult,
    DefectTheme,
    SystemicPattern,
)
from utils.defect_analytics import (
    COMPONENT_HOTSPOT_MINIMUM,
    COMPONENT_HOTSPOT_SHARE,
    EXCEPTION_PATTERN_SHARE,
    MIN_OCCURRENCES_FOR_THEME,
    MIN_SUBMISSIONS_FOR_PATTERNS,
    UNCLASSIFIED_EXCEPTION,
    component_groups,
    distribution,
    duplicate_rate,
    extract_facts,
    percentage,
    recurrence_rate,
    repeated_failure_points,
    theme_groups,
)
from utils.logging_config import get_agent_logger


class DefectPatternAnalyticsAgent:
    """Summarize recurring themes, hotspots, and systemic issues."""

    def __init__(self, max_themes: int = 8, max_hotspots: int = 6) -> None:
        self.max_themes = max_themes
        self.max_hotspots = max_hotspots
        self.logger = get_agent_logger(__name__)

    def predict(self, reports: list[dict[str, Any]]) -> DefectAnalyticsResult:
        """Build the portfolio view from saved submission records."""
        reports = list(reports or [])
        facts = extract_facts(reports)
        result = DefectAnalyticsResult(
            generated_at=datetime.now(UTC).isoformat(),
            submissions_analyzed=len(reports),
            submissions_with_pipeline_output=len(facts),
            knowledge_base_entries=self._knowledge_base_entries(),
        )
        if not facts:
            result.notes.append(
                "No submission carries agent output yet, so no defect pattern can be measured."
            )
            return result

        result.themes = self._themes(facts)
        result.component_hotspots = self._hotspots(facts)
        result.severity_distribution = distribution(facts, "severity")
        result.priority_distribution = distribution(facts, "priority")
        result.exception_distribution = distribution(facts, "exception")
        result.remediation_basis_distribution = distribution(facts, "remediation_basis")
        result.recurrence_rate = recurrence_rate(facts)
        result.duplicate_rate = duplicate_rate(facts)
        result.systemic_patterns = self._systemic_patterns(facts)

        if len(facts) < MIN_SUBMISSIONS_FOR_PATTERNS:
            result.notes.append(
                f"Systemic pattern detection needs at least {MIN_SUBMISSIONS_FOR_PATTERNS} "
                f"analyzed submissions; {len(facts)} available."
            )
        if len(reports) != len(facts):
            result.notes.append(
                f"{len(reports) - len(facts)} submission(s) had no agent output and were excluded."
            )
        self.logger.info(
            "Defect pattern analytics completed",
            extra={
                "agent": "DefectPatternAnalytics",
                "submissions": len(facts),
                "themes": len(result.themes),
                "patterns": len(result.systemic_patterns),
            },
        )
        return result

    def _themes(self, facts: list[dict[str, Any]]) -> list[DefectTheme]:
        return [
            DefectTheme(
                theme=group["theme"],
                exception=group["exception"],
                component=group["component"],
                occurrences=group["occurrences"],
                share_percentage=group["share_percentage"],
                first_seen=group["timestamps"][0] if group["timestamps"] else None,
                last_seen=group["timestamps"][-1] if group["timestamps"] else None,
                example_submission_ids=group["submission_ids"][:5],
            )
            for group in theme_groups(facts)[: self.max_themes]
        ]

    def _hotspots(self, facts: list[dict[str, Any]]) -> list[ComponentHotspot]:
        return [
            ComponentHotspot(
                component=group["component"],
                defect_count=group["defect_count"],
                share_percentage=group["share_percentage"],
                high_impact_count=group["high_impact_count"],
                top_exceptions=group["top_exceptions"],
                example_submission_ids=group["submission_ids"][:5],
            )
            for group in component_groups(facts)[: self.max_hotspots]
        ]

    def _systemic_patterns(self, facts: list[dict[str, Any]]) -> list[SystemicPattern]:
        """Apply each detection rule, keeping only those with enough evidence."""
        if len(facts) < MIN_SUBMISSIONS_FOR_PATTERNS:
            return []
        patterns = [
            *self._recurring_exception_patterns(facts),
            *self._component_hotspot_patterns(facts),
            *self._repeated_failure_point_patterns(facts),
            *self._duplicate_influx_pattern(facts),
            *self._knowledge_gap_pattern(facts),
        ]
        patterns.sort(key=lambda pattern: -pattern.affected_submissions)
        return patterns

    @staticmethod
    def _recurring_exception_patterns(facts: list[dict[str, Any]]) -> list[SystemicPattern]:
        """Flag one failure mode that dominates the portfolio."""
        patterns: list[SystemicPattern] = []
        for exception, count in distribution(facts, "exception").items():
            share = percentage(count, len(facts))
            if (
                exception == UNCLASSIFIED_EXCEPTION
                or count < MIN_OCCURRENCES_FOR_THEME
                or share < EXCEPTION_PATTERN_SHARE
            ):
                continue
            components = sorted(
                {fact["component"] for fact in facts if fact["exception"] == exception}
            )
            patterns.append(
                SystemicPattern(
                    pattern_id=f"recurring-exception:{exception}",
                    title=f"{exception} is a recurring failure mode",
                    detail=(
                        f"{exception} accounts for {count} of {len(facts)} analyzed defects "
                        f"({share}%), spanning {len(components)} component(s)."
                    ),
                    affected_submissions=count,
                    evidence=[
                        f"Components affected: {', '.join(components)}",
                        *[
                            f"{fact['submission_id']}: {fact['title']}"
                            for fact in facts
                            if fact["exception"] == exception
                        ][:5],
                    ],
                    recommendation=(
                        f"Treat {exception} as a class of defect rather than a series of "
                        "incidents: add a shared guard or validation utility at the component "
                        "boundary and a lint or test rule that catches the pattern before release."
                    ),
                )
            )
        return patterns

    @staticmethod
    def _component_hotspot_patterns(facts: list[dict[str, Any]]) -> list[SystemicPattern]:
        """Flag a component absorbing a disproportionate share of defects."""
        patterns: list[SystemicPattern] = []
        for group in component_groups(facts):
            if (
                group["defect_count"] < COMPONENT_HOTSPOT_MINIMUM
                or group["share_percentage"] < COMPONENT_HOTSPOT_SHARE
            ):
                continue
            exceptions = group["top_exceptions"] or ["no classified exception"]
            patterns.append(
                SystemicPattern(
                    pattern_id=f"component-hotspot:{group['component']}",
                    title=f"{group['component']} concentrates defects",
                    detail=(
                        f"{group['component']} carries {group['defect_count']} of "
                        f"{len(facts)} analyzed defects ({group['share_percentage']}%), of "
                        f"which {group['high_impact_count']} are Critical or High severity."
                    ),
                    affected_submissions=group["defect_count"],
                    evidence=[
                        f"Dominant exceptions: {', '.join(exceptions)}",
                        f"Example submissions: {', '.join(group['submission_ids'][:5])}",
                    ],
                    recommendation=(
                        f"Prioritise a focused review of {group['component']}: raise its test "
                        "coverage, audit its input validation, and require a regression test for "
                        "each defect closed against it."
                    ),
                )
            )
        return patterns

    @staticmethod
    def _repeated_failure_point_patterns(facts: list[dict[str, Any]]) -> list[SystemicPattern]:
        """Flag a single code location reached by several distinct defects."""
        patterns: list[SystemicPattern] = []
        for point, count in repeated_failure_points(facts)[:3]:
            submissions = [
                fact["submission_id"] for fact in facts if fact["failure_point"] == point
            ]
            patterns.append(
                SystemicPattern(
                    pattern_id=f"repeated-failure-point:{point}",
                    title="One code location fails repeatedly",
                    detail=(
                        f"{count} separate submissions failed at {point}, which indicates an "
                        "unresolved defect rather than independent incidents."
                    ),
                    affected_submissions=count,
                    evidence=[f"Submissions: {', '.join(submissions[:5])}"],
                    recommendation=(
                        f"Re-open the investigation at {point}. Verify that the previously "
                        "applied fix addressed the cause rather than the symptom, and add a "
                        "regression test that reproduces the original failure."
                    ),
                )
            )
        return patterns

    @staticmethod
    def _duplicate_influx_pattern(facts: list[dict[str, Any]]) -> list[SystemicPattern]:
        """Flag a high proportion of defects already present in history."""
        rate = duplicate_rate(facts)
        if rate < 30:
            return []
        matched = [fact for fact in facts if fact["has_duplicate"]]
        return [
            SystemicPattern(
                pattern_id="duplicate-influx",
                title="Known defects keep being re-reported",
                detail=(
                    f"{len(matched)} of {len(facts)} analyzed defects ({rate}%) matched a "
                    "high-confidence historical duplicate, so reporting effort is being spent "
                    "on failures the organisation has already seen."
                ),
                affected_submissions=len(matched),
                evidence=[
                    f"{fact['submission_id']} duplicates {fact['duplicate_bug_id']} "
                    f"at {fact['duplicate_similarity']}%"
                    for fact in matched[:5]
                ],
                recommendation=(
                    "Surface the duplicate check at report time and confirm that the matched "
                    "historical fixes were actually released; a duplicate that keeps recurring "
                    "usually means the original fix was incomplete."
                ),
            )
        ]

    @staticmethod
    def _knowledge_gap_pattern(facts: list[dict[str, Any]]) -> list[SystemicPattern]:
        """Flag remediation that is mostly inferred rather than evidence-backed.

        This is the measurement the knowledge base growth mechanism is meant to
        move: as confirmed fixes are fed back, the historical share should rise.
        """
        ungrounded = [fact for fact in facts if fact["remediation_basis"] != "historical"]
        share = percentage(len(ungrounded), len(facts))
        if share < 50:
            return []
        return [
            SystemicPattern(
                pattern_id="knowledge-base-gap",
                title="Recommendations are rarely grounded in a recorded fix",
                detail=(
                    f"{len(ungrounded)} of {len(facts)} recommendations ({share}%) were inferred "
                    "from diagnostics because no retrieved defect carried a recorded resolution."
                ),
                affected_submissions=len(ungrounded),
                evidence=[
                    f"{fact['submission_id']}: basis '{fact['remediation_basis']}'"
                    for fact in ungrounded[:5]
                ],
                recommendation=(
                    "Confirm the fix on resolved submissions so they are written back into the "
                    "Historical Defect Knowledge Base. Each confirmed fix converts a future "
                    "diagnostic guess into an evidence-backed recommendation."
                ),
            )
        ]

    @staticmethod
    def _knowledge_base_entries() -> int:
        """Report how many confirmed fixes have been learned so far."""
        try:
            from utils.knowledge_base import learned_entry_count

            return learned_entry_count()
        except Exception:  # analytics must never fail on an unreadable side file
            return 0
