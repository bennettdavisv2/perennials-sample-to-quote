"""SalesforceCRM: the production twin of s2q/adapters/crm.py MockCRM. SKELETON / SPEC: not run against an org.

Same method names and return shapes as MockCRM, so s2q.workflow runs unchanged. Every method
records its call in the audit log, as the mock does. Auth: OAuth 2.0 JWT bearer flow with the
integration user (handoff S8). Field and object names: REFERENCE.md §3.1.
"""
from __future__ import annotations

API = "/services/data/v62.0"  # pin the API version the org supports


class SalesforceCRM:
    def __init__(self, instance_url: str, access_token: str, audit_log):
        self.base, self.token, self.log = instance_url, access_token, audit_log

    # ---------- lookups (SOQL: GET {API}/query?q=...) ----------
    def account(self, account_id):
        """SELECT Id, Name, Type, Trade_Status__c FROM Account WHERE Id = :id"""
        raise NotImplementedError

    def contact_by_email(self, email):
        """SELECT Id, AccountId, Name, Email, Alternate_Email__c FROM Contact
           WHERE Email = :email OR Alternate_Email__c = :email LIMIT 1"""
        raise NotImplementedError

    def contacts_by_domain(self, domain):
        """SELECT ... FROM Contact WHERE Email LIKE :'%@' + domain  (skip free-mail domains before calling)"""
        raise NotImplementedError

    def lead_by_email(self, email):
        """SELECT Id, Status, ConvertedContactId, ... FROM Lead WHERE Email = :email ORDER BY CreatedDate DESC LIMIT 1"""
        raise NotImplementedError

    def account_by_name(self, name):
        """Exact normalized-name match; Duplicate Rules are the backstop (S3)."""
        raise NotImplementedError

    # Lookups the workflow needs once it stops reading the mock's in-memory lists (README §Refactors).
    def get_lead(self, lead_id): raise NotImplementedError          # GET {API}/sobjects/Lead/{id}
    def get_contact(self, contact_id): raise NotImplementedError    # GET {API}/sobjects/Contact/{id}
    def get_opportunity(self, opp_id): raise NotImplementedError    # GET {API}/sobjects/Opportunity/{id}
    def get_quote(self, quote_id): raise NotImplementedError        # GET {API}/sobjects/Quote/{id} + QuoteLineItems

    # ---------- leads ----------
    def create_lead(self, req, segment_hint, project):
        """Upsert on the external id (idempotent): PATCH {API}/sobjects/Lead/Source_Request_Id__c/{req id}
           LeadSource = 'Web Sample Request' | 'Email Quote', Project_Name__c, Project_Type__c, Description = message."""
        raise NotImplementedError

    def set_lead_status(self, lead, status, reason):
        """PATCH {API}/sobjects/Lead/{id}  {Status, Qualification_Reason__c}"""
        raise NotImplementedError

    def convert_lead(self, lead, account, contact, new_account=None):
        """POST /services/apexrest/s2q/convertLead  (Apex class S2QConvertLead, handoff S2)
           {leadId, accountId?, contactId?, newAccountName?, newAccountType?} -> {accountId, contactId}"""
        raise NotImplementedError

    def add_alt_email(self, contact, email):
        """PATCH {API}/sobjects/Contact/{id}  {Alternate_Email__c}"""
        raise NotImplementedError

    # ---------- opportunities ----------
    def open_opportunity(self, account_id):
        """SELECT ... FROM Opportunity WHERE AccountId = :id AND IsClosed = false ORDER BY CreatedDate DESC LIMIT 1"""
        raise NotImplementedError

    def create_opportunity(self, account, contact, name, stage, now):
        """Composite: POST Opportunity (Pricebook2Id = standard) + OpportunityContactRole"""
        raise NotImplementedError

    def update_opportunity(self, opp, **fields):
        """PATCH {API}/sobjects/Opportunity/{id}  (StageName, Amount, Sample_Order_Ids__c)"""
        raise NotImplementedError

    # ---------- quotes ----------
    def open_quote(self, opp_id):
        """SELECT ... FROM Quote WHERE OpportunityId = :id AND Status NOT IN ('Superseded','Rejected')
           ORDER BY CreatedDate DESC LIMIT 1"""
        raise NotImplementedError

    def create_quote(self, opp, lines, total, flags, status, now, valid_days, budgetary, revision_of):
        """Composite request (allOrNone):
             1. if revision_of: PATCH old Quote Status = 'Superseded'
             2. POST Quote {OpportunityId, Name, Status, ExpirationDate, Version__c, Review_Flags__c, Budgetary__c}
             3. POST QuoteLineItem per line {PricebookEntryId (by ProductCode = SKU), Quantity = yards,
                UnitPrice = net price, Discount, Requested_Yards__c, Dye_Lots__c}
           Needs every SKU as Product2 + standard PricebookEntry (nightly sync, handoff S1)."""
        raise NotImplementedError

    def set_quote_status(self, q, status):
        """PATCH {API}/sobjects/Quote/{id}  {Status}"""
        raise NotImplementedError

    # ---------- human review ----------
    def create_task(self, subject, related_to, owner="Sales rep"):
        """POST {API}/sobjects/Task  {Subject, WhatId, OwnerId = 'Sample-to-Quote Review' queue,
           Description = drafted customer message}  (handoff S4)"""
        raise NotImplementedError

    # ---------- customer email (S7) ----------
    def send_email(self, contact_id, subject, body):
        """POST {API}/actions/standard/emailSimple  from the org-wide quotes@perennialsfabrics.com address (logged on the Contact)"""
        raise NotImplementedError
