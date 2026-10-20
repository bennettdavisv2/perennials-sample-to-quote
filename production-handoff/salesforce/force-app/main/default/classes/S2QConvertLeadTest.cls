/** SKELETON / SPEC: test outline for S2QConvertLead (Salesforce requires coverage to deploy). */
@IsTest
private class S2QConvertLeadTest {

    @IsTest static void convertsIntoNewAccountAndContact() {
        // TODO: insert a Lead; set RestContext.request.requestBody = {"leadId": ...};
        //       call S2QConvertLead.convert(); assert a new Account + Contact and Lead.IsConverted.
    }

    @IsTest static void convertsIntoExistingContact() {
        // TODO: insert Account + Contact (dana@...), a Lead from d.ruiz@... (the WEB-003 case);
        //       convert with accountId + contactId; assert no new Contact was created.
    }
}
