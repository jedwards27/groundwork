---
description: Start tracking a new project in Groundwork from what the person says, a tracker spreadsheet or their email. Use when the person wants Groundwork to follow a project of their own.
---

# Start a project

1. Make sure `setup` has been done (call `projects`; if `you` is empty, run setup first).
2. Gather the project from the person, in whatever form they have it:
   - **A few sentences.** Ask what finishing means, the target date, who the outside parties are (contractor, designer, permit office, inspector, landlord, vendors) and what each owes.
   - **A tracker spreadsheet.** Read it with their own file or Drive connector, read-only.
   - **Email threads.** Read them with their own email connector, read-only, and pick out the parties, people's emails, commitments and dates.
3. Build the draft:
   - **Parties,** with their people's emails; routing depends on them.
   - **People on the person's own side,** such as a partner, in `your_side`.
   - **Items,** each with an owner, a status and a planned finish date. Use `you` as the owner of the person's own tasks, and mark the item that means "finished".
   - **Dependencies.** Put a dependency in `depends_on` only when a source states it. If you're inferring it, put it in `assumed_depends_on`, so the person is asked to confirm it.
   - **A mandate template.** Start with Supervised unless they ask for more.
   - **For a backtest,** set `as_of` to the date to start from, and use only what was known then.
4. Call `start_project`. If it returns problems, fix them and call it again. Calling it again replaces the earlier draft.
5. Show the forecast and what sets the date. Ask the person to confirm the project in the Groundwork app; nothing is created until they do.
6. Don't invent dates, people or addresses. Ask instead.
