# 0011: Changing a project after it starts

**Status:** accepted (Nov 4, 2026).

## Context

The first real project loaded through the plugin was a home-interiors job: 52 steps over almost two years, most of them done. Using it turned up gaps that a fixture never shows.
- **Steps went missing from view.** The chart showed six weeks back, so 46 of the 52 steps were hidden, and nothing listed them all.
- **Nothing could be fixed once created.** After `start_project`, a wrong step, a new step or a renamed party had no tool.
- **No way out.** A duplicate project (created twice under two names) couldn't be removed.
- **Real schedules are messier than the model.** Some steps were descoped, some dates were guesses, some done steps had no known finish date, and kinds like "install" or "payment" didn't exist.
- **The designer was on both projects,** so her mail matched two projects.
- **A step 91 days late with no word** still showed the finish "on time", with a range of one day.

## Decision

**Every change is a draft the person confirms in the app,** like new projects and mandates.
- Claude drafts with `edit_steps` (add, change, cancel or remove steps), `edit_project` (name, location, finish, parties, the project it follows on from), `archive_project` and `delete_project`.
- Each draft is applied first to an in-memory copy of the project and run through the engine. A draft that would break the project is refused before the person sees it: an unknown key, a loop in the links, or removing or cancelling the finish step. The draft shows the forecast before and after.
- Confirming checks again against the project as it is then, and writes one ledger record.

**Cancel, don't remove.** A descoped step gets status `cancelled`. It stays on record, but nothing waits on it and the forecast ignores it: the engine treats it as finished by today at the latest. Removing a step is for one entered by mistake. A step whose dates a message moved can't be removed, because the ledger points at it.

**Archive, then delete.**
- Archiving is reversible. It takes the project off home and out of mail routing, and the ledger records it.
- Deleting removes the project, its messages and its ledger, after the person types the project's key.
- A ledger can't record its own deletion. So a line goes to `deleted.jsonl` in the Groundwork home folder instead: what was deleted, by whom, why, and the ledger's last hash. A receipt someone kept can still be matched to that hash.
- The Lake Mariner demo can be archived but not deleted.
- The hosted demo has neither: a visitor's copy is deleted when it expires.

**Estimated dates are marked.** A step can say its date is an estimate (`~Dec 4`). A done step with no known finish keeps a placeholder date, marked as an estimate.

**Silence is a risk.** A step past its planned finish, with no message about it since, keeps its middle case: it starts today, as before. Its late case slips it as much again. The finish range widens when such a step is on the finish's path, and status lists such steps either way.

**Routing with shared people.**
1. The email thread decides first.
2. Then the people on the message.
3. If those people are on more than one active project, the project whose name the subject or body mentions wins.
4. Otherwise Groundwork asks.

Starting a project warns when its people or parties are already on another project.

**The project's first record keeps a snapshot:** its steps, finish and parties, and a hash of them. Later records show what changed from there.

## Consequences

- The agent still never changes a project on its own. The tools that change things only draft, and a test lists every tool.
- The engine checks each edit, so a broken draft is caught before it reaches the person, not after.
- A deleted project leaves only its log line. That is the person's call on their own computer. With a shared, hosted version, deletion would need a retention policy instead.
- Silence widens the range only when the silent step is on the finish's path. A late step that nothing waits on is flagged, but it can't move the date. Its links may be missing, and the person is the one to say.
