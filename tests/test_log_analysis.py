"""Unit tests for cross-language log extraction."""

import pytest

from agents.log_analysis_agent import LogAnalysisAgent


@pytest.fixture
def agent() -> LogAnalysisAgent:
    return LogAnalysisAgent()


def test_python_traceback(agent):
    result = agent.predict('''Traceback (most recent call last):
  File "/srv/auth/service.py", line 42, in login
    user.name
AttributeError: user is None''')
    assert result.language == "Python"
    assert result.exception_type == "AttributeError"
    assert result.file == "/srv/auth/service.py"
    assert result.line == 42
    assert result.function == "login"


def test_nested_python_uses_root_exception(agent):
    result = agent.predict('''Traceback (most recent call last):
  File "app.py", line 2, in run
    int("x")
ValueError: invalid

During handling of the above exception, another exception occurred:
Traceback (most recent call last):
  File "app.py", line 5, in run
    raise RuntimeError("failed")
RuntimeError: failed''')
    assert result.root_exception == "RuntimeError"
    assert result.line == 5


def test_java_trace(agent):
    result = agent.predict('''java.lang.NullPointerException: session is null
    at com.acme.auth.LoginService.authenticateUser(LoginService.java:108)
    at com.acme.web.LoginController.login(LoginController.java:44)''')
    assert result.language == "Java"
    assert result.exception_type == "NullPointerException"
    assert result.file == "LoginService.java"
    assert result.line == 108
    assert result.function == "authenticateUser"


def test_java_nested_cause(agent):
    result = agent.predict('''java.lang.RuntimeException: wrapper
    at com.acme.App.run(App.java:9)
Caused by: java.sql.SQLException: connection refused
    at com.acme.Db.open(Db.java:21)''')
    assert result.root_exception == "SQLException"


def test_node_trace(agent):
    result = agent.predict('''ReferenceError: user is not defined
    at authenticate (/srv/auth.js:25:11)
    at main (/srv/index.js:4:2)''')
    assert result.language in {"NodeJS", "JavaScript"}
    assert result.exception_type == "ReferenceError"
    assert result.function == "authenticate"
    assert result.line == 25


def test_malformed_log(agent):
    result = agent.predict("2026-01-01 FATAL service failed unexpectedly")
    assert result.error_message
    assert result.confidence >= 0
    assert result.warnings


def test_empty_log(agent):
    result = agent.predict("")
    assert result.exception_type is None
    assert result.confidence == 5
    assert result.warnings


def test_large_log_is_bounded(agent):
    frames = "\n".join(f'  File "/app/f{i}.py", line {i + 1}, in f{i}' for i in range(1_200))
    result = agent.predict(f"Traceback (most recent call last):\n{frames}\nValueError: bad")
    assert len(result.call_stack) <= 200
    assert result.exception_type == "ValueError"

