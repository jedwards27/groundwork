# Lake Mariner fixture (CB-5, end-user posture)

A site folder in the layout `groundwork inspect` and `groundwork seed` read. Use it as the template for loading your own site.

**Posture.** The agent works for Anthropic as the end user. TeraWulf (Lake Mariner Data LLC) is landlord, developer and interconnection customer; Fluidstack is the lessee; Anthropic is not a party to the lease. Routing is data: each party's `reached_via` says who you go through to reach it, and the gateway derives every action's path from that.

**Provenance.** Every row says `public` (with a URL), `synthetic` (written for the demo) or `assumption_to_verify`. The `source` column on schedule rows points at the synthetic status report the schedule was transcribed from, or at a public URL. Questions that would confirm the assumptions are in `docs/PRACTITIONER-QUESTIONS.md`.

| File | What it is | Provenance |
|---|---|---|
| `site.yaml` | Org, site, CB-5 and its milestones, parties with roles and routing, demo personas, site facts | Facts and roles public with URLs; personas fictional (`.example` addresses) |
| `schedule.csv` | 26 items, 31 links (predecessor column, e.g. `to_accept FS+15bd`) | Dates synthetic, transcribed from the status report; several items public |
| `status-report-2026-10-30.md` | The landlord's weekly report the schedule is transcribed from | Synthetic |
| `events.yaml` | Playable events: two schedule changes, an expedite offer, two public evidence items, an auto-reply, two injection attempts | Synthetic except the two public items |
| `inbox/*.eml` | The messages behind the events | Synthetic |
| `evidence/*.yaml` | Structured evidence: the IE's quote, the vendor's expedite offer | Synthetic |
| `reference_projects.csv` | Comparable items for forecasting (shared across orgs) | Public, several via secondary sources (marked) |

**What is deliberately absent.** NYPA's allocation gates nothing on CB-5's chain and is a site fact, not an item. Fiber gates compute online, not energization, so it is not on this chain. The 180-day delivery remedy reported for some Fluidstack leases is not verified for Lake Mariner and is not used.

**The schedule's computed gate** is NYSEG's acceptance of the protection settings (`to_accept`), with three business days of float to the February 22 delivery date. Christmas falls inside the 15-business-day notice NYSEG needs between acceptance and the witness test, which the engine reports as a calendar loss on the critical path.

**What is public about the dates, and what is ours.** TeraWulf has said CB-5's first data hall is expected to begin energizing in very early January 2027 (CTO on the Q2 2026 call, via a secondary summary) and that CB-5 is targeted to begin phased delivery in early 2027 (Q2 2026 release). It has not published a delivery date. The fixture models energization as the end of NYSEG's witness test on Jan 6, sizes NYSEG's settings review (seven weeks) so that it lands there, and puts L4 delivery on Feb 17 against a Feb 22 lease date by following CB-4's public pace of about six weeks from L3 start-up to L4. Every one of those choices is an assumption to verify.
