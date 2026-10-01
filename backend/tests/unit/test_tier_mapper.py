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
        TierMapper.classify("get_users", "function", "src/v1/users.py")
        == TaskCategory.CONTRACT_API
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
        TierMapper.classify("dockerfile", "file", "Dockerfile")
        == TaskCategory.DOCUMENTATION_CONFIG
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
