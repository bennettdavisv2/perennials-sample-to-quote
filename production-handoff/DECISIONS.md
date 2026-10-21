# Decisions needed

Questions only Perennials can answer. Each has a recommended default, so work can start, and the roadmap step it blocks. Answer D1–D5 in [phase 0](ROADMAP.md#phase-0-decide-and-set-up); the rest can wait until the step that needs them.

| # | Decision | Recommended default | Why | Who decides | Blocks |
|---|---|---|---|---|---|
| D1 | **How does a quote hold work in NetSuite?** A *Pending Approval* sales order doesn't commit inventory by default. | An approved sales order on a "Quote Hold" form with lot-level inventory detail | Commits the exact dye lots and is easy to reverse; a transfer to a HOLD location is the alternative | NetSuite admin + order ops | 5.1 (decide in phase 0: it shapes the NetSuite design) |
| D2 | **Is there already a Salesforce–NetSuite connector** (Celigo, Breadwinner…)? | Assume no | If yes, reuse it for the customer link and product sync instead of building them | IT / systems owner | 1.2, 4.1 |
| D3 | **Where is Do Not Sell kept today?** | An account-level field, `Account.Trade_Status__c` | One place the qualification policy can read | Sales ops | 1.3 |
| D4 | **Do samples require a trade login, or is guest checkout allowed?** | Keep guest checkout; add logged-in matching later | Matches the PoC; with a login, matching becomes exact (W4) | E-commerce owner | 2.1 (matching), Later (W4) |
| D5 | **Are dye lots tracked as lot numbers in NetSuite?** | Yes | Dye-lot allocation and holds depend on it | NetSuite admin | 1.5, 2.4 |
| D6 | **What quote total needs a manager's approval?** | $20,000 | The PoC setting `manager_approval_over` | Sales leadership | 4.4 |
| D7 | **Do volume discounts add to the trade discount (15% + 5% = 20%) or compound?** | Add | README assumption 1; it changes every quote over 50 yd | Sales leadership / finance | 4.2 |
| D8 | **Who works the review queue:** a shared inside-sales queue or each account owner? | Shared queue first, then the account owner | New senders need fast qualification; the owner knows the account | Sales leadership | 3.2 |
| D9 | **Is quotes@perennialsfabrics.com on Google Workspace?** | Yes | Decides Gmail vs Microsoft Graph for email intake | IT | 2.2 |
| D10 | **Claude through the Anthropic API or AWS Bedrock?** | Anthropic API | Bedrock keeps data inside AWS if that's a requirement | IT / security | 2.3 |
| D11 | **Shadow and review exit thresholds** (95% extraction agreement; 90% of quotes approved unchanged) | As stated | Sets when each phase switches on | Sales ops | 2.5, 4.6 |
| D12 | **Do we give reps an AI assistant connected to Salesforce and NetSuite through their MCP servers?** | Yes, once phase 4 is live: read-only first, as the rep's own Salesforce user and a NetSuite custom role without admin rights | Speeds up the review queue without automating any decision; IT / security must accept that the data the assistant reads goes to the AI provider ([REFERENCE §7](REFERENCE.md#7-mcp-servers-where-they-fit)) | Sales leadership + IT / security | Later (rep assistant) |
