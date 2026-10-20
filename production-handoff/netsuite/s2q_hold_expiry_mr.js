/**
 * customscript_s2q_hold_expiry: daily Map/Reduce that releases expired quote holds (handoff N9).
 *
 * SKELETON / SPEC: not deployed. Which way a hold is released depends on the N8 decision:
 *   (a) hold = approved sales order on the S2Q Quote Hold form -> close its lines
 *   (b) hold = transfer to the HOLD location                   -> transfer the lots back
 *
 * @NApiVersion 2.1
 * @NScriptType MapReduceScript
 */
define(['N/search', 'N/record', 'N/https', 'N/runtime'], (search, record, https, runtime) => {

    /** Open hold orders whose custbody_s2q_hold_expires is before today. */
    const getInputData = () => search.create({
        type: search.Type.SALES_ORDER,
        filters: [
            ['mainline', 'is', 'T'], 'and',
            ['custbody_s2q_type', 'anyof', runtime.getCurrentScript().getParameter({ name: 'custscript_s2q_hold_type_id' })], 'and',
            ['custbody_s2q_hold_expires', 'before', 'today'], 'and',
            ['status', 'noneof', ['SalesOrd:H']],          // H = Closed; verify status codes in the account
        ],
        columns: ['internalid', 'custbody_s2q_sf_quote_id'],
    });

    const map = (ctx) => {
        const row = JSON.parse(ctx.value);
        // TODO (a): record.load salesOrder row.id; set every line's isclosed = true; save.
        // TODO (b): create an inventory transfer HOLD -> main location for the held lots.
        // Then tell the service, so the Salesforce Quote shows the hold as released:
        // https.post({ url: <service>/callbacks/netsuite, body: JSON.stringify({ so: row.id, event: 'hold_expired' }) })
        ctx.write({ key: row.id, value: row.values.custbody_s2q_sf_quote_id });
    };

    const summarize = (summary) => {
        // TODO: log counts; surface map errors (summary.mapSummary.errors) to the admin.
    };

    return { getInputData, map, summarize };
});
