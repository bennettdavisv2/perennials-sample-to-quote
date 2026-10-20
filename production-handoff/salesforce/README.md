# Salesforce building blocks

**Skeleton / spec.** Source-format metadata (deploy with `sf project deploy start` to a sandbox first). Nothing here has been deployed to an org. Handoff items S1–S8 are in [`../README.md`](../README.md) §3.

| Path | What it is | Handoff |
|---|---|---|
| `force-app/main/default/classes/S2QConvertLead.cls` | Apex REST endpoint wrapping `Database.convertLead`; converts into an existing Account/Contact when the service matched one | S2 |
| `.../classes/S2QConvertLeadTest.cls` | Test outline (coverage is required to deploy) | S2 |
| `.../objects/Lead/fields/Source_Request_Id__c.field-meta.xml` | One field as deployable metadata, as the pattern for the rest | §3.1 |

## Fields to add (same pattern as the example)
See the table in [`../README.md` §3.1](../README.md#31-fields-and-picklists): Lead `Source_Request_Id__c`, `Qualification_Reason__c`, `Project_Type__c`, `Project_Name__c`; Contact `Alternate_Email__c`; Account `NetSuite_Customer_Id__c`, `Trade_Status__c`; Opportunity `Sample_Order_Ids__c`; Quote `Version__c`, `Review_Flags__c`, `Budgetary__c`, `NetSuite_Hold_SO__c`, `Hold_Expires__c`, `CFA_Order__c`; QuoteLineItem `Dye_Lots__c`, `Requested_Yards__c`; Task `Drafted_Message__c`; plus picklist values on Lead.Status and Quote.Status.

## Automation (build in Setup; specs below)

**Review queue (S4).** Queue `Sample-to-Quote Review` (Tasks). The service creates a Task per review: Subject = reason, WhatId = Lead or Quote, `Drafted_Message__c` = the customer email it drafted.

**Quote approval (S5).** Approval Process on Quote. Entry: `Status = 'Pending Rep Review'`. Step 1: the account owner (or the queue). Step 2, only if `GrandTotal > 20000`: sales manager. Approve sets Status = `Approved`; reject sets `Rejected`.

**Callback Flow (S6).** Record-triggered Flow `S2Q Decision Callback`:
- Triggers: Quote after update, when Status changes to `Approved` / `Rejected`; Task after update, when Status changes to `Completed` with `Decision__c` set (Approve / Reject / Ask).
- Action: HTTP Callout through Named Credential `S2Q_Service` → `POST /callbacks/salesforce` with `{record_id, decision, user}`.
- Fault path: create a Task for the admin; the service also reconciles daily.

**Task quick actions.** On the review Task's page: **Approve**, **Send question**, **Reject**. Each sets `Decision__c` and completes the Task, which fires the Flow.

**Customer email (S7).** Org-wide email address quotes@perennialsfabrics.com (verified). The service sends through the standard `emailSimple` action so each email is logged on the Contact. Quote PDF template: line items, total, valid-until, hold expiry.

**Integration user (S8).** Salesforce Integration user licence; External Client App with OAuth 2.0 JWT bearer flow; permission set `S2Q_Integration`: CRUD on Lead, Contact, Account, Opportunity, OpportunityContactRole, Quote, QuoteLineItem, Task; read Product2/PricebookEntry; Apex class access to `S2QConvertLead`.
