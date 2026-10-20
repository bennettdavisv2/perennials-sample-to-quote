"""NetSuiteERP: the production twin of s2q/adapters/erp.py MockERP. SKELETON / SPEC: not run against an account.

Same method names and return shapes as MockERP, so s2q.workflow runs unchanged. Auth: OAuth 2.0
client credentials (M2M, certificate) on a dedicated integration role (handoff N10).
REST base: https://<account>.suitetalk.api.netsuite.com/services/rest
"""
from __future__ import annotations


class NetSuiteERP:
    def __init__(self, account_id: str, access_token: str, audit_log):
        self.account, self.token, self.log = account_id, access_token, audit_log

    # ---------- items and inventory ----------
    def items(self):
        """SuiteQL (POST /query/v1/suiteql): item id, itemid (= SKU), custitem_s2q_lifecycle, base price,
           summed available quantity. Cache for a few minutes; the LLM catalog and the nightly
           Salesforce product sync both use it."""
        raise NotImplementedError

    def get_item(self, sku):
        """One row of items() for this SKU (status, list price, available yards)."""
        raise NotImplementedError

    def lots_for(self, sku):
        """SuiteQL per lot number: lot, on hand, committed. Verify which record holds lot balances in
           Perennials' account (inventory number / inventory balance; handoff N6)."""
        raise NotImplementedError

    def allocate(self, sku, yards):
        """Pure logic, unchanged from MockERP.allocate: prefer the smallest single lot that covers the line,
           else split across lots. Reads lots_for(sku)."""
        raise NotImplementedError

    def sampled_skus(self, customer_id):
        """SKUs on this customer's S2Q Sample orders (replaces the workflow reading erp.sales_orders directly;
           see README §Refactors)."""
        raise NotImplementedError

    # ---------- customers ----------
    def upsert_customer(self, account):
        """PUT /record/v1/customer/eid:{CRM Account Id}  (externalId upsert, handoff N3); returns internal id."""
        raise NotImplementedError

    # ---------- pricing ----------
    def price(self, sku, yards, is_trade):
        """POST RESTlet customscript_s2q_price  {sku, yards, is_trade}
           -> {list_price, trade_discount, volume_discount, total_discount, unit_price, yards, extended,
               cut_fee, line_total}   (same keys as s2q.pricing.price_line; netsuite/s2q_price_restlet.js)"""
        raise NotImplementedError

    # ---------- orders ----------
    def create_sample_order(self, customer_id, skus, ship_to, now):
        """POST /record/v1/salesOrder  customform = S2Q Sample, $0 price level, custbody_s2q_type = Sample,
           one memo-swatch line per SKU (handoff N7)."""
        raise NotImplementedError

    def create_reservation(self, customer_id, quote_id, lines, now):
        """The hold (handoff N8, mechanism to be decided):
             (a) POST salesOrder on the 'S2Q Quote Hold' form, approved, with inventoryDetail per lot
                 (inventoryAssignment.issueInventoryNumber = lot, quantity = yards); or
             (b) inventory transfer of those lots to the HOLD location.
           Body fields: custbody_s2q_type = Hold, custbody_s2q_sf_quote_id, custbody_s2q_hold_expires (+14 days).
           Returns {id, hold_expires, lines}."""
        raise NotImplementedError

    def release_reservation(self, so_id, reason):
        """(a) PATCH salesOrder lines isClosed = true, or (b) transfer back. Idempotent: no-op if already released."""
        raise NotImplementedError

    def create_cfa_order(self, customer_id, quote_id, alloc_plan, ship_to, now):
        """POST salesOrder  customform = S2Q CFA, $0, one cutting per held lot (inventoryDetail = that lot)."""
        raise NotImplementedError
