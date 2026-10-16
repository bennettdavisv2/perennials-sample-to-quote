"""System adapters. Each mock exposes the same methods a real adapter would.

Swap MockCRM for a SalesforceCRM / HubSpotCRM and MockERP for a NetSuiteERP that
implement the same methods; the workflow does not change.
"""
from .crm import MockCRM
from .erp import MockERP

__all__ = ["MockCRM", "MockERP"]
