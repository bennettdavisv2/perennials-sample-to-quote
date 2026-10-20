/**
 * POST /services/apexrest/s2q/convertLead   (handoff S2)
 * The REST API has no lead-convert call, so the integration service calls this endpoint.
 * Converts into an existing Account/Contact when the service found one (dedupe), otherwise creates them.
 *
 * SKELETON / SPEC: written against the documented Database.convertLead API, not yet deployed to an org.
 */
@RestResource(urlMapping='/s2q/convertLead')
global with sharing class S2QConvertLead {

    global class Request {
        public Id leadId;
        public Id accountId;        // optional: convert into this existing Account
        public Id contactId;        // optional: merge into this existing Contact (e.g. a second email address)
        public String accountType;  // for a new Account: 'Trade – Interior Designer', 'Consumer / Retail', ...
    }

    @HttpPost
    global static Map<String, Id> convert() {
        Request r = (Request) JSON.deserialize(RestContext.request.requestBody.toString(), Request.class);

        Database.LeadConvert lc = new Database.LeadConvert();
        lc.setLeadId(r.leadId);
        if (r.accountId != null) lc.setAccountId(r.accountId);
        if (r.contactId != null) lc.setContactId(r.contactId);
        lc.setDoNotCreateOpportunity(true);   // the service creates / reuses the Opportunity itself
        LeadStatus converted = [SELECT MasterLabel FROM LeadStatus WHERE IsConverted = true LIMIT 1];
        lc.setConvertedStatus(converted.MasterLabel);

        Database.LeadConvertResult res = Database.convertLead(lc);
        // TODO: if a new Account was created, set Account.Type / Trade_Status__c from r.accountType.
        return new Map<String, Id>{ 'accountId' => res.getAccountId(), 'contactId' => res.getContactId() };
    }
}
