"""Unit tests for TierMapper."""

from trace.analysis.planner.tier_mapper import TierMapper
from trace.domain.plan import TaskCategory


def test_classify_endpoints_and_routes() -> None:
    assert (
        TierMapper.classify("PaymentAPI", "endpoint", "src/api/payment.py")
        == TaskCategory.CONTRACT_API
    )
    assert (
        TierMapper.classify("checkout", "route", "src/routes/checkout.py")
        == TaskCategory.CONTRACT_API
    )
    assert (
        TierMapper.classify("get_users", "function", "src/v1/users.py") == TaskCategory.CONTRACT_API
    )


def test_classify_models_and_databases() -> None:
    assert (
        TierMapper.classify("UserOrm", "class", "src/models/user.py") == TaskCategory.DATA_MAPPING
    )
    assert (
        TierMapper.classify("payment_table", "table", "src/database/tables.py")
        == TaskCategory.DATA_MAPPING
    )
    assert (
        TierMapper.classify("migration_001", "function", "alembic/versions/001.py")
        == TaskCategory.DATA_MAPPING
    )


def test_classify_handlers_and_workers() -> None:
    assert (
        TierMapper.classify("payment_webhook", "function", "src/handlers/webhook.py")
        == TaskCategory.CONSUMER_HANDLER
    )
    assert (
        TierMapper.classify("send_email_task", "task", "src/workers/mailer.py")
        == TaskCategory.CONSUMER_HANDLER
    )
    assert (
        TierMapper.classify("OrderEventListener", "class", "src/events/listener.py")
        == TaskCategory.CONSUMER_HANDLER
    )


def test_classify_ui_and_frontend() -> None:
    assert TierMapper.classify("DashboardView", "view", "frontend/app.py") == TaskCategory.CLIENT_UI
    assert (
        TierMapper.classify("NavbarComponent", "component", "frontend/src/nav.jsx")
        == TaskCategory.CLIENT_UI
    )


def test_classify_tests() -> None:
    assert (
        TierMapper.classify("test_payment_api", "test", "tests/test_payment.py")
        == TaskCategory.INTEGRATION_TEST
    )
    assert (
        TierMapper.classify("test_checkout", "function", "src/payments/test_checkout.py")
        == TaskCategory.INTEGRATION_TEST
    )


def test_classify_docs_and_configs() -> None:
    assert TierMapper.classify("README", "file", "README.md") == TaskCategory.DOCUMENTATION_CONFIG
    assert (
        TierMapper.classify("workflow", "file", ".github/workflows/ci.yml")
        == TaskCategory.DOCUMENTATION_CONFIG
    )
    assert (
        TierMapper.classify("dockerfile", "file", "Dockerfile") == TaskCategory.DOCUMENTATION_CONFIG
    )


def test_classify_core_logic_fallback() -> None:
    assert (
        TierMapper.classify("calculate_tax", "function", "src/services/tax.py")
        == TaskCategory.CORE_LOGIC
    )
    assert (
        TierMapper.classify("OrderDomain", "class", "src/domain/order.py")
        == TaskCategory.CORE_LOGIC
    )


def test_classify_backend_app_py_as_core_logic() -> None:
    # Backend application entrypoints and functions in app.py must NOT be classified as Client/UI
    assert (
        TierMapper.classify("request_context", "function", "src/flask/app.py")
        == TaskCategory.CORE_LOGIC
    )
    assert (
        TierMapper.classify("test_request_context", "function", "src/flask/app.py")
        == TaskCategory.CORE_LOGIC
    )
    assert (
        TierMapper.classify("create_app", "function", "backend/app.py") == TaskCategory.CORE_LOGIC
    )


def test_classify_documentation_diff() -> None:
    # 1. Real Flask docstring Sphinx role diff
    flask_doc_diff = """
- :data:`.session`, :data:`g:`, and :data:`.current_app` become available.
+ :data:`.session`, :data:`g`, and :data:`.current_app` become available.
"""
    assert TierMapper.is_documentation_diff(flask_doc_diff) is True
    assert (
        TierMapper.classify(
            "test_request_context",
            "function",
            "src/flask/app.py",
            diff_snippet=flask_doc_diff,
        )
        == TaskCategory.DOCUMENTATION_CONFIG
    )

    # 2. Comment-only diff
    comment_diff = """
- # Old note on business logic
+ # Updated note on business logic
"""
    assert TierMapper.is_documentation_diff(comment_diff) is True
    assert (
        TierMapper.classify(
            "calculate_tax",
            "function",
            "src/services/tax.py",
            diff_snippet=comment_diff,
        )
        == TaskCategory.DOCUMENTATION_CONFIG
    )

    # 3. Code diff with statement logic must NOT be classified as doc
    code_diff = """
- def calculate_tax(amount):
-     return amount * 0.10
+ def calculate_tax(amount, tax_rate):
+     return amount * tax_rate
"""
    assert TierMapper.is_documentation_diff(code_diff) is False
    assert (
        TierMapper.classify(
            "calculate_tax",
            "function",
            "src/services/tax.py",
            diff_snippet=code_diff,
        )
        == TaskCategory.CORE_LOGIC
    )
