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
   - **Items,** each with an owner, a kind, a status and a planned finish date. Use `you` as the owner of the person's own tasks, and mark the item that means "finished".
     - Kinds include install, decision (a selection or sign-off), meeting (or presentation) and payment (an invoice or deposit), as well as delivery, inspection, permit and the rest.
     - Mark a date someone only estimated ("early December") with `approximate`.
     - A step that was descoped is `cancelled`. A done step whose finish date isn't known can leave `finish` empty.
     - Include every step the source has, done ones too.
   - **Dependencies.** Put a dependency in `depends_on` only when a source states it. If you're inferring it, put it in `assumed_depends_on`, so the person is asked to confirm it.
   - **A mandate template.** Start with Supervised unless they ask for more.
   - **For a backtest,** set `as_of` to the date to start from, and use only what was known then.
4. Call `start_project`. If it returns problems, fix them and call it again. Calling it again replaces the earlier draft.
   - If it returns `overlaps`, tell the person which people or parties are already on another project. If it's the same project, change that one instead.
   - If the project already exists, don't start it again. Use `edit_steps` and `edit_project`; offer `archive_project` for a duplicate.
5. Show the forecast and what sets the date. Ask the person to confirm the project in the Groundwork app; nothing is created until they do.
6. Once it's created, call `steps` and check every step against the source.
7. Don't invent dates, people or addresses. Ask instead.
