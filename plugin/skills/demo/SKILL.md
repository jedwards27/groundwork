---
description: Play Groundwork's two-minute demo on the Lake Mariner data-center project. Use when the person asks for the demo or wants to see how Groundwork works.
---

# The two-minute demo

Lake Mariner is a data-center campus in western New York. In the demo, TeraWulf owns the site, Fluidstack leases the building, and Anthropic is the end user, which reaches the utility only through both. The roles are public, and TeraWulf has given rough dates. The specific days are ours, and the people, schedule and email are synthetic.

1. **The item setting the date (about 25 seconds).** Call `status` for `lake-mariner`. Say what sets the finish date and the slack left.
2. **Play the message (about 20 seconds).** Call `play_message` for `lake-mariner` and `demo-monday`. It plays a hand-written plan, so it runs the same way every time; the gateway, ledger and report check are live.
   - **If it says the message has already been played,** the demo already ran on this computer. Don't stop: call `ledger` for `lake-mariner`, say when that run happened, and use its records for the steps below. If the ask has an `approval` record, say it was already approved rather than asking for approval again. Updating the plugin starts the demo fresh whenever the update changes it.
3. **Allow.** A routine status request to Fluidstack's project manager about a deliverable already owed. Read out the clause that allows it, and note it ran in dry run.
4. **Ask.** Asking TeraWulf, through Fluidstack, to confirm the energization date. Show the route and the clause: the mandate covers direct counterparties only. Give the Groundwork app link, and have the person approve it there. In the demo they're Jordan Brooks, Anthropic's project manager and the mandate's one approver.
5. **Deny.** The landlord also asks for a signed schedule acknowledgment. Signing is on the never list: Groundwork won't sign, no one can approve it signing, and the document goes to the person.
6. **The report beside the record (about 30 seconds).** Show that the report matched the ledger. Then call `verify_record` for a record. Explain that **Verify a receipt**, under Receipts in the project's Settings in the Groundwork app, shows Match for a true copy and Mismatch for an edited one.

Keep each step to a sentence or two, and use the words allow, ask and deny.
