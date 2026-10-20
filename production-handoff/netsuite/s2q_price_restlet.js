/**
 * customscript_s2q_price: pricing RESTlet (handoff N5). Called by NetSuiteERP.price().
 * POST {sku, yards, is_trade} -> {list_price, trade_discount, volume_discount, total_discount,
 *                                 unit_price, yards, extended, cut_fee, line_total}
 *
 * SKELETON / SPEC: not deployed. priceLine() ports s2q/pricing.py price_line(); it must agree with
 * these test vectors from tests/test_workflow.py before go-live:
 *   trade, 80 yd, list $98   -> 20% off (15% trade + 5% volume, additive), $78.40/yd, $6,272.00
 *   trade, 3 yd,  list $78   -> 15% off, 3 x $66.30 + $25 cut fee
 *   non-trade, 120 yd, $64   -> 0% (volume tiers are trade-only), $64/yd
 *
 * @NApiVersion 2.1
 * @NScriptType Restlet
 */
define(['N/query'], (query) => {

    /** Rules come from customrecord_s2q_pricing_rule (N4) so merchandising can change them. */
    const loadRules = () => {
        // TODO: SuiteQL over customrecord_s2q_pricing_rule; cache in N/cache for a few minutes.
        // Shape: {tradeDiscount: 0.15, nonTradeDiscount: 0, volumeTiers: [[100, 0.10], [50, 0.05]],
        //         cutFee: 25, cutFeeUnderYards: 5}
        throw new Error('TODO: load pricing rules');
    };

    const listPrice = (sku) => {
        // TODO: SuiteQL: base price of the item whose itemid = sku.
        throw new Error('TODO: look up list price');
    };

    const round2 = (x) => Math.round(x * 100) / 100;

    /** Same arithmetic as s2q/pricing.py price_line. */
    const priceLine = (list, yards, isTrade, rules) => {
        const base = isTrade ? rules.tradeDiscount : rules.nonTradeDiscount;
        let vol = 0;
        if (isTrade) {                                   // tiers are on top of trade, trade only, additive
            const tier = rules.volumeTiers.find(([minYards]) => yards >= minYards);   // highest tier first
            vol = tier ? tier[1] : 0;
        }
        const unit = round2(list * (1 - (base + vol)));
        const extended = round2(unit * yards);
        const cutFee = yards > 0 && yards < rules.cutFeeUnderYards ? rules.cutFee : 0;
        return { list_price: list, trade_discount: base, volume_discount: vol, total_discount: base + vol,
                 unit_price: unit, yards, extended, cut_fee: cutFee, line_total: round2(extended + cutFee) };
    };

    const post = (body) => priceLine(listPrice(body.sku), Number(body.yards), Boolean(body.is_trade), loadRules());

    return { post };
});
