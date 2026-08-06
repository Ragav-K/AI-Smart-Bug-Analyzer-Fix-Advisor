"""Weighted keyword classifier for affected product components."""

from __future__ import annotations

import re

COMPONENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Authentication": ("login", "log in", "password", "token", "oauth", "jwt", "session", "signin"),
    "Authorization": ("permission", "forbidden", "access denied", "role", "rbac", "unauthorized"),
    "Payment": ("payment", "checkout", "card", "billing", "refund", "transaction", "gateway"),
    "Database": ("database", "sql", "query", "jdbc", "orm", "connection pool", "postgres", "mysql", "mongo"),
    "REST API": ("rest", "endpoint", "http", "controller", "api", "request", "response", "status code"),
    "Frontend": ("frontend", "react", "javascript", "typescript", "browser", "dom", "component render"),
    "UI": ("button", "screen", "css", "layout", "color", "spacing", "modal", "dropdown"),
    "UX": ("usability", "confusing", "workflow", "user experience", "navigation"),
    "Backend": ("backend", "service", "server", "worker", "microservice", "business logic"),
    "Search": ("search", "index", "elasticsearch", "solr", "query results"),
    "Notifications": ("notification", "email", "sms", "push", "webhook"),
    "Deployment": ("deploy", "deployment", "release", "ci/cd", "pipeline", "build failure"),
    "Cloud": ("aws", "azure", "gcp", "cloud", "lambda", "kubernetes"),
    "Configuration": ("config", "configuration", "environment variable", "yaml", "property"),
    "Performance": ("slow", "latency", "performance", "memory leak", "cpu", "throughput"),
    "Logging": ("logging", "logger", "log rotation", "log level"),
    "Networking": ("network", "dns", "socket", "connection refused", "tls", "proxy"),
    "Storage": ("storage", "disk", "file system", "s3", "blob", "upload"),
    "Security": ("security", "vulnerability", "xss", "csrf", "injection", "breach", "cve"),
    "Caching": ("cache", "redis", "memcached", "stale data"),
    "Analytics": ("analytics", "tracking", "metric", "telemetry"),
    "Reporting": ("report", "export", "pdf", "dashboard report"),
}


def component_scores(text: str) -> tuple[dict[str, int], dict[str, list[str]]]:
    normalized = text.lower()
    scores: dict[str, int] = {}
    evidence: dict[str, list[str]] = {}
    for component, keywords in COMPONENT_KEYWORDS.items():
        # Accept the regular plural of each keyword. Reporters write
        # "notifications" and "permissions" far more often than the singular,
        # and a strict word boundary was classifying those as "Other".
        hits = [
            keyword
            for keyword in keywords
            if re.search(rf"(?<!\w){re.escape(keyword)}e?s?(?!\w)", normalized)
        ]
        evidence[component] = hits
        scores[component] = sum(3 if " " in hit else 2 for hit in hits)
    return scores, evidence


def classify_component(text: str) -> tuple[str, list[str], int]:
    scores, evidence = component_scores(text)
    component = max(scores, key=scores.get) if scores else "Other"
    if scores.get(component, 0) == 0:
        return "Other", [], 0
    return component, evidence[component], scores[component]

