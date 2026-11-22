# Member-Controlled Connection Model

Status: Proposed design and research framework; not a validated intervention,
relationship-benefit claim, trust assessment, or legal-compliance certification.

## Purpose

Hearthline expands adult choice in friendship, conversation, dating, romance,
consensual intimacy, and shared activities.

Each proposed step must be understandable and optional. Members can withdraw
future platform authorization. Before an action, Hearthline explains consequences
that cannot reliably be undone, including information already delivered or copied.

No member must progress toward meetings, sex, partnership, or greater disclosure.

## Member-Controlled Choice Cycle

Members may enter, skip, repeat, pause, or leave optional activities:

1. Private preparation: clarify intentions, learn communication skills, rehearse,
   and compare options.
2. Discovery: browse chronologically or use explicitly selected criteria.
3. Proposal: prepare a bounded Connection Envelope.
4. Authorization: review specific recipients, actions, and disclosures.
5. Interaction: participate through an agreed, accessible format.
6. Optional reflection: privately consider whether the interaction was wanted
   and what, if anything, should change.

These operations are not stages of personal development or relationship success.
Optional research responses must not affect discovery eligibility.

## Operating Principles

- Member statements govern intentions; behavior must not be used to infer them.
- Discovery eligibility does not authorize contact or disclosure.
- Permission for one action does not authorize another.
- Silence, prior participation, and previous permission are not current permission.
- Coaching supports member authorship; it does not impersonate members.
- Housing, income, household skills, and social experience do not determine worth
  or eligibility for connection.
- Text-first, non-camera, low-bandwidth, and non-AR alternatives must support
  relevant core tasks.
- Security controls constrain harmful operations, not presumed character.
- No desirability, readiness, attendance, criminal-intent, or trust score is used.
- Optional infrastructure must not require public relationship records or
  member-managed cryptographic complexity for core access.

## Connection Envelope

An envelope describes one proposed interaction. It is not a contract, a consent
substitute, or blanket authorization.

Include only relevant, member-selected information:

- Purpose and format.
- Topics, media preferences, and contact boundaries.
- Optional duration, cost, access details, and scheduling overlap.
- Proposed recipients and disclosures.
- Available decline, revision, withdrawal, block, report, and deletion controls.

Each participant controls their own contributions. An envelope's overall display
status must never substitute for action-specific authorization.

## Separate Records

Maintain distinct records for:

| Record | Purpose |
| --- | --- |
| Proposal | Describe the interaction and its reviewed version. |
| Disclosure authorization | Specify information that may be revealed to named recipients. |
| Action authorization | Permit a particular protected operation within a defined scope. |
| Enforcement state | Apply blocks, restrictions, expiration, and platform rules. |
| Private workspace | Hold member-controlled drafts, practice, and reflections. |
| Reporting evidence | Support purpose-limited review under documented retention rules. |

Shared proposal content must not expose private practice or reflections.
Withdrawal does not imply that independently held copies can be erased.

## Authorization Invariant

A protected action may execute only when platform rules permit it and every
required participant has current authorization for the applicable scope.

Authorization must identify:

- Authorizing member.
- Action and recipients.
- Information or media covered.
- Relevant proposal version.
- Expiration or other validity conditions.
- Withdrawal state.

Engineering requirements:

- Changes to approved scope require renewed approval.
- Unrelated private edits must not announce changes or invalidate other permissions.
- Queued jobs and retries recheck current authorization.
- Withdrawal takes precedence over work not yet committed.
- Earlier approvals cannot restore withdrawn permissions through replay.
- Blocking prevents subsequent member-contact delivery, including queued delivery.
- Already delivered information is distinguished from future platform access.

The execution boundary and concurrency behavior must be specified and tested.
These requirements are not implementation guarantees until verified.

## Privacy and Security

For each data class, document purpose, permission or other applicable processing
basis, recipients, access controls, retention, deletion, correction, and review owner.

Security processing must be necessary, disclosed, and purpose-limited. Security
records must not feed dating rankings, advertising, or inferred-intent profiles.

Member content is untrusted input, not authority to access data or invoke tools.
The assistant must not disclose another member's private information in response
to instructions embedded in profiles, messages, links, or attachments.

Do not publish relationship metadata or place sensitive connection records on an
immutable ledger.

## Assistance and Review

Members can block or restrict contact without proving misconduct.

Reports trigger appropriate assistance and evidence review, not automatic findings
of guilt. Consequential restrictions require documented rules, proportionate
decisions, correction routes, and accessible appeal.

Immediate technical containment must be scoped to the specific security concern.
Any legally required disclosure requires a documented, jurisdiction-specific
process; do not promise absolute confidentiality.

## Evaluation

Prespecify:

- Member need and hypothesized mechanism.
- Minimum necessary research data.
- Rights-respecting comparison, where appropriate.
- Separate clarity, autonomy, accessibility, pressure, and unwanted-contact measures.
- Missing-response handling and uncertainty.
- Release-blocking defects, stopping conditions, and rollback responsibility.
- Retention, deletion, review ownership, and appeal procedures.

Distinguish voluntary withdrawal from inability to complete a task. Report both
without treating either as an individual deficit. Interpret time and assistance
alongside member preferences.

Do not combine outcomes into a personal success score or claim relationship
benefits from feature use alone.

## Initial Prototype

Scope: private preparation and a text-only invitation with purpose, optional
duration, cost, access details, and an easy decline.

Exclude credentials, precise location, recording, and decentralized infrastructure.

Test whether members understand:

1. What they are proposing.
2. Who receives which information.
3. What they have and have not authorized.
4. How to revise or withdraw.
5. What cannot be undone after sending.

Test blocked delivery, queued-operation withdrawal, stale approvals, accessible
authentication and recovery, and private-edit leakage.

Release requires documented test results and review, not merely an accepted
proposal or passing interface demonstration.
