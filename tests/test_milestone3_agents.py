"""Comprehensive unit tests for the Milestone 3 analysis agents."""

from agents.duplicate_agent import DuplicateDetectionAgent
from agents.remediation_agent import RemediationAgent
from agents.root_cause_agent import RootCauseAgent
from utils.scoring import normalized_similarity, stack_similarity


def context_with_match(similarity=0.86):
    """Return a representative shared context with grounded history."""
    return {
        "triage": {
            "severity": "High",
            "priority": "P1",
            "component": "Authentication",
        },
        "log_analysis": {
            "exception_type": "NullPointerException",
            "root_exception": "NullPointerException",
            "confidence": 91,
            "file": "UserService.java",
            "call_stack": [{"file": "UserService.java"}],
            "call_stack_summary": [
                "authenticate at UserService.java:108",
                "login at LoginController.java:44",
            ],
            "probable_cause": "An authentication object is null before access.",
        },
        "retrieved_bugs": [
            {
                "bug_id": "BUG-91",
                "title": "NullPointerException in authentication",
                "description": "UserService authentication object was not initialized.",
                "root_cause": "Authentication object was not initialized before user access.",
                "resolution": "Add a null guard and validate the JWT before accessing the user.",
                "status": "Resolved",
                "priority": "High",
                "similarity": similarity,
                "similarity_percentage": round(similarity * 100),
                "match_reasons": ["Semantic match", "UserService.java"],
            }
        ],
    }


def test_root_cause_is_grounded_and_structured():
    result = RootCauseAgent().predict(context_with_match())
    assert "not initialized" in result.root_cause
    assert result.confidence >= 70
    assert result.matched_bug_ids == ["BUG-91"]
    assert result.supporting_evidence[0].bug_id == "BUG-91"
    assert result.reasoning


def test_root_cause_without_history_is_conservative():
    context = context_with_match()
    context["retrieved_bugs"] = []
    result = RootCauseAgent().predict(context)
    assert "Insufficient grounded evidence" in result.root_cause
    assert result.confidence < 40
    assert result.supporting_evidence == []


def test_root_cause_can_infer_conservatively_from_recorded_resolution():
    context = context_with_match()
    context["retrieved_bugs"][0]["root_cause"] = ""
    result = RootCauseAgent().predict(context)
    assert "historical fix" in result.root_cause
    assert "null guard" in result.root_cause


def test_root_cause_uses_current_diagnostic_only_with_retrieved_context():
    context = context_with_match()
    context["retrieved_bugs"][0]["root_cause"] = ""
    context["retrieved_bugs"][0]["resolution"] = ""
    result = RootCauseAgent().predict(context)
    assert result.root_cause == context["log_analysis"]["probable_cause"]


def test_cause_from_resolution_handles_unknown_diagnostics():
    cause = RootCauseAgent._cause_from_resolution("Guard the value.", None, None)
    assert cause.startswith("The failure")


def test_duplicate_agent_reranks_diagnostic_agreement():
    result = DuplicateDetectionAgent().predict(context_with_match(0.72))
    assert result.candidates_evaluated == 1
    assert result.duplicates[0].bug_id == "BUG-91"
    assert result.duplicates[0].similarity >= 65
    assert "Exception type matches" in result.duplicates[0].match_reasons


def test_duplicate_agent_ignores_weak_match():
    context = context_with_match(0.12)
    context["retrieved_bugs"][0].update(
        title="Unrelated layout issue",
        description="Button spacing is wrong",
        root_cause="",
        priority="Low",
    )
    result = DuplicateDetectionAgent().predict(context)
    assert result.duplicates == []


def test_remediation_uses_historical_resolution():
    context = context_with_match()
    context["root_cause"] = {
        "root_cause": "Authentication object was not initialized.",
        "confidence": 88,
    }
    context["duplicate_detection"] = {
        "duplicates": [{"bug_id": "BUG-91", "similarity": 91}]
    }
    result = RemediationAgent().predict(context)
    assert "null guard" in result.recommended_fix
    assert result.evidence_bug_ids == ["BUG-91"]
    assert result.files_likely_affected == ["UserService.java"]
    assert len(result.steps) >= 4
    assert result.confidence >= 80


def test_remediation_never_claims_history_without_a_resolution():
    """Without a recorded resolution the agent may still recommend a repair,
    but it must fall back to diagnostics and claim no historical evidence."""
    context = context_with_match()
    context["retrieved_bugs"][0]["resolution"] = ""
    context["root_cause"] = {"confidence": 50}
    context["duplicate_detection"] = {"duplicates": []}
    result = RemediationAgent().predict(context)
    assert result.basis != "historical"
    assert result.evidence_bug_ids == []
    assert "No retrieved historical defect recorded a resolution" in result.historical_resolution
    assert result.confidence <= 55


def test_remediation_best_practice_variants():
    assert "timeouts" in RemediationAgent._best_practice("Add timeout and retry")
    assert "dependency" in RemediationAgent._best_practice("Upgrade dependency version")
    assert "regression test" in RemediationAgent._best_practice("Refactor the parser")


def test_similarity_percentage_and_empty_stack_edge_cases():
    assert normalized_similarity({"similarity_percentage": 82}) == 0.82
    assert stack_similarity({"title": "login"}, []) == 0
    assert stack_similarity({"title": "login"}, ["1 2"]) == 0
