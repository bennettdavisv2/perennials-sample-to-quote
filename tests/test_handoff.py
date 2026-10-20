"""Guards for production-handoff/: the skeleton adapters must keep the same interface as the mocks
the workflow is tested against, so swapping them in can't silently miss a method."""
import base64
import hashlib
import hmac
import importlib.util
import inspect
from pathlib import Path

from s2q.adapters import MockCRM, MockERP

SERVICE = Path(__file__).resolve().parent.parent / "production-handoff" / "integration-service"


def _load(rel):
    spec = importlib.util.spec_from_file_location(rel.replace("/", "_"), SERVICE / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _public(cls):
    return {n for n, f in inspect.getmembers(cls, inspect.isfunction) if not n.startswith("_")}


def test_salesforce_adapter_covers_every_mock_crm_method():
    missing = _public(MockCRM) - _public(_load("adapters/salesforce.py").SalesforceCRM)
    assert not missing, f"SalesforceCRM is missing {missing}"


def test_netsuite_adapter_covers_every_mock_erp_method():
    missing = _public(MockERP) - _public(_load("adapters/netsuite.py").NetSuiteERP)
    assert not missing, f"NetSuiteERP is missing {missing}"


def test_woocommerce_signature_check():
    handlers = _load("handlers.py")
    body, secret = b'{"id": 48213}', "s3cret"
    good = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    assert handlers.verify_woocommerce_signature(body, good, secret)
    assert not handlers.verify_woocommerce_signature(body + b" ", good, secret)
    assert not handlers.verify_woocommerce_signature(body, "", secret)
