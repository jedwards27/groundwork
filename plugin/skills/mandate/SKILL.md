---
description: Write or change a project's mandate in plain words with Groundwork. Use when the person wants to grant, widen, narrow, pause, extend or revoke what Groundwork may do on a project.
---

# Write a mandate in plain words

A mandate says what Groundwork may do on its own (allow), what it must ask a person about (ask), and what it may never do (deny), with limits, approvers and an expiry date.

1. Call `status` for the project and read its current mandate lines.
2. Ask the person what they want, in their own words. For example: "chase vendors weekly, ask me before anything over $500, never sign".
3. Turn their words into terms:
   - **template:** Supervised, Standard or Auto.
   - **Spend limits** per action and per day.
   - **Messages further along:** whether routine messages may ask a party further along the route.
   - **Extra kinds to deny.**
   - **Approvers** and an **expiry date**.
   - **Pause or revoke.**

   Paying, signing and deleting are always denied.
4. Call `draft_mandate` with their exact words and the terms. Show the lines added and removed, and any notes.
5. Ask them to confirm in the Groundwork app. You can never confirm, issue or widen a mandate yourself. When they confirm, actions still waiting are decided again under the new version.
