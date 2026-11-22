# Member-Controlled Connection Contracts

Status: Proposed engineering and research specification.

This document does not establish implementation, legal compliance, member
comprehension, accessibility, relationship benefit, or deployment readiness.

## Purpose

Hearthline supports adult-controlled friendship, conversation, dating, romance,
consensual intimacy, and shared activities.

Privacy, authorization, discovery, accessibility, security, and evaluation are
separate assurance obligations. Passing one does not compensate for failing
another.

Each proposed interaction must be understandable and optional. Members may
withdraw future platform authorization. Information already delivered or copied
may not be recoverable.

## Attribution

Retain the contributor's designated attribution in separately configured
document-credit metadata only.

Attribution does not establish identity, consent, authorization, execution
evidence, or authority over another person or system.

## Core Invariants

- Private edits do not publish information or initiate contact.
- Intentions change only through explicit member action.
- Discovery eligibility does not authorize contact or disclosure.
- Shared snapshots describe dated statements, not current consent.
- Empty intentions never become an unrestricted invitation.
- Clarification is private, optional, dismissible, and non-notifying.
- Blocking does not require a finding of misconduct.
- Reports are not automatic proof of misconduct.
- Housing, income, skills, disability, and social experience do not determine
  relationship worth.
- Sensitive records do not become desirability, readiness, attendance, criminal
  intent, or trust scores.
- Core participation has usable text-first, non-camera, and non-AR paths.

## Private Intent State

Private intent state distinguishes:

- Unset: the member has not made a selection.
- None selected: the member explicitly selected no intentions.
- Selected: the member explicitly selected one or more intentions.

Unset and none selected both contain an empty selection, but remain distinct
states. Neither means open to anything.

Private state also carries a concurrency revision. The revision is not exposed
through public responses, recipient notifications, or public cache validators.

Saving privately does not authorize discovery use, disclosure, or notification.

### Concurrent Edits

Every edit supplies the revision the member reviewed.

- A matching revision permits an atomic update.
- A stale revision returns a conflict without overwriting newer state.
- An identical edit against the current revision is a no-op.
- No-op edits do not advance the revision.
- Stale writes remain conflicts even when their content matches current state.
- Conflict resolution requires accessible member review.
- Automatic reconciliation must not merge intentions or publish a combined set.

Silent last-write-wins behavior is prohibited.

## Shared Snapshots

A snapshot contains only explicitly approved content for a defined recipient
scope.

Required properties:

- Author.
- Recipient scope.
- Approved fields and values.
- Member-confirmed statement time.
- Freshness policy.
- Applicable contract version.
- Supersession relationship where relevant.

The author approves disclosure of their information. Receiving a statement does
not grant the recipient authority over it.

Creating a snapshot does not authorize serving it.

### Statement Time and Freshness

- Statement time records member confirmation, not the latest retrieval.
- Private edits do not update shared timestamps.
- Private edits do not announce that a shared statement may be stale.
- Consumers present approved statement-time information with the statement.
- Expired freshness prevents further serving under the applicable contract.
- Supersession does not independently grant or withdraw permission.
- Freshness policies must not create recurring pressure to disclose.
- No consumer may treat a snapshot as current consent.

An author may separately update a statement or withdraw future platform access.

## Action-Specific Authorization

Authorization is separate from both private state and shared statements.

A protected operation requires current permission specifying:

- Authorizing member.
- Action.
- Recipient scope.
- Approved fields and values.
- Applicable statement version.
- Purpose.
- Validity conditions.
- Withdrawal state.

Permission to view a statement is not permission to export it. Permission for a
text exchange is not permission for a call, location sharing, recording, sexual
discussion, or continued contact.

### Disclosure Ceiling

For each protected read:

\[
\text{served content}
\subseteq
\text{approved snapshot content}
\cap
\text{currently authorized field scope}
\]

This ceiling is necessary but not sufficient. The operation also requires current
authorization and applicable platform permission.

## Private-Edit Noninterference

A private edit must not alter another member's permitted observation trace.

\[
\operatorname{Observe}_{r}
\left(T_{\mathrm{private}}(s,i)\right)
=
\operatorname{Observe}_{r}(s)
\]

For randomized implementations, compare the distributions of observation traces
under the defined public state, inputs, observer capabilities, and time window.

Observation surfaces include:

- Content.
- Notifications.
- Discovery membership, ordering, and counts.
- Recipient-visible eligibility results.
- Public revision markers.
- Response sizes and public cache validators.
- Recipient-visible errors.
- Aggregate announcements.
- Relevant timing and rate-limit behavior.

Private selections and published discovery inputs remain separate. A private
edit must not silently change discovery participation.

### Limits of Evidence

Tests must state their observer model, channels, duration, detection sensitivity,
and untested surfaces.

Failure to detect a difference is not proof of identical distributions.

Timing, infrastructure contention, aggregate leakage, and distributed-cache
behavior require dedicated analysis beyond pure-state unit tests.

## Discovery Eligibility

Criterion evaluation distinguishes:

- Not selected: no constraint was imposed.
- Satisfied: a selected constraint passes.
- Not satisfied: a selected constraint fails.
- Unknown: a selected constraint cannot be evaluated.

An absent criterion imposes no constraint. It does not indicate attraction,
consent, or willingness to disclose.

An empty intention selection is not an absent criterion. These states must remain
separate throughout validation, serialization, and evaluation.

### Restrictions

Restriction decisions include:

- Allowed or restricted status.
- Direction and scope.
- Internal reason category.
- Member-safe explanation category.
- Applicable policy version.
- Evaluation time and expiry where relevant.
- Correction or review route.

Explanations must not reveal another member's private information or unnecessarily
confirm that a particular person blocked someone.

Expired disclosure permission belongs to the authorization gate, not the
criterion evaluator.

### Advisory Results

Eligibility returns one of:

- Eligible.
- Excluded.
- Needs private clarification.

Every result is advisory and carries its evaluation context. No result authorizes
delivery or disclosure.

Mutual-introduction symmetry is an explicit discovery policy, not a universal
property. Directional restrictions remain directional.

## Private Clarification

- Clarification does not generate outgoing messages or notifications.
- Dismissal creates no penalty or visibility reduction.
- Dismissed prompts do not automatically reopen.
- Expiry removes pending clarification rather than granting permission.
- Reopening requires member action or a separately requested evaluation.
- Missing information must not be used to infer its cause.
- Clarification history must not enter ranking or reputation features.

The eligibility component accepts immutable inputs and returns data. It receives
no network, delivery, notification, or persistence capability.

## Withdrawal and Commitment

For a protected operation:

\[
\text{withdrawal precedes commitment}
\Rightarrow
\text{the operation must not commit}
\]

The implementation must define an authoritative ordering and commitment boundary.

At execution:

- Recheck applicable restrictions.
- Recheck current authorization.
- Recheck statement and field scope.
- Recheck expiry and withdrawal.
- Commit only within the documented ordering protocol.

Queued jobs, retries, resumed sessions, and worker restarts repeat these checks.

An earlier approval cannot restore withdrawn permission through replay.
A separate check followed by an unprotected action is not an atomic guarantee.

Withdrawal cannot undo an already completed disclosure.

## Approved-Source Lineage

Discovery readers consume purpose-approved published inputs, not private
workspace tables.

For every discovery artifact:

\[
\text{personal-data sources}
\subseteq
\text{sources currently approved for the discovery purpose}
\]

Processing code, policies, and configuration require their own approval records;
they are not personal disclosure sources.

Lineage must cover creation, updates, serving, expiration, withdrawal, and
deletion. Derived artifacts must stop being served when their required source
authorization no longer applies.

Lineage records themselves require access controls and retention limits.

Recipient-scoped snapshots and clarification records must not feed ranking or
reputation pipelines. Any approved use of explicit discovery inputs must remain
separate from those records.

## Integration Contracts

### Private State Store

Precondition: validated input and expected revision.

Postcondition: atomic private update or explicit conflict.

Forbidden effects: publication, discovery changes, notifications, and unapproved
writes to shared caches.

### Authorization Gate

Precondition: authenticated actor, explicit operation scope, and current policy.

Postcondition: narrowly scoped permission or denial.

Forbidden effects: inferred permission, automatic scope expansion, and disclosure
through detailed denial messages.

### Delivery Boundary

Precondition: current restrictions and action authorization.

Postcondition: only the approved operation commits.

Forbidden effects: stale approval reuse and replay-based restoration.

### Cache Invalidation

Precondition: classified mutation and approved cache scope.

Postcondition: only permitted artifacts are changed or invalidated.

Forbidden effects: private edits causing observable shared-cache activity.

### Notification Emitter

Precondition: an explicitly authorized notification operation.

Postcondition: approved content reaches only approved recipients.

Forbidden effects: notifications generated merely because private state changed.

### Leakage Instrumentation

Precondition: approved diagnostic purpose, access, and retention.

Postcondition: sufficient evidence to evaluate defined channels.

Forbidden effects: unrestricted raw payload capture and publication through
diagnostic output.

## Diagnostic Minimization

Choose telemetry against a defined defect suite and a prespecified detection
requirement.

Prefer evidence about operations and policy outcomes over raw intent histories.

Document:

- Collected fields.
- Detection purpose.
- Access.
- Retention.
- Deletion.
- Export restrictions.
- Residual privacy risks.

Security telemetry must not become dating analytics, advertising input, or a
relationship history.

## Accessible Control

Use distinct operations for:

- Save privately.
- Review sharing.
- Withdraw future access.

Test comprehension and recovery, not labels alone.

Include mistaken sharing, interrupted withdrawal, shared-device use,
authentication failure, low bandwidth, and assistive-technology pathways.

Report absolute comprehension, uncertainty, nonresponse, and pathway disparity.
Equal misunderstanding is not success.

## Errors and Compatibility

Distinguish invalid state, revision conflict, unsupported version, authorization
denial, expired scope, withdrawn scope, restricted operation, and unavailable
dependency.

Member-facing errors must preserve other members' privacy.

Changes affecting disclosure, permission, or default interpretation require
explicit migration review. Unsupported contracts must not silently adopt broader
permissions.

## Research Contract

### Member-Valued Outcomes

Follow-up volume is not intrinsically beneficial.

Measure clarity, autonomy, accessibility, pressure, unwanted contact, and
member-reported wanted participation separately.

Declining, pausing, or leaving may be a wanted outcome. Nonresponse remains
unknown and must not become a personal deficit.

### Network-Aware Estimand

Specify how outcomes depend on a member's assignment and exposure to others'
assignments:

\[
Y_u = Y_u(z_u,g_u)
\]

Define the exposure mapping before analysis.

A direct-effect estimand under a prespecified exposure distribution may be:

\[
\Delta_Y(q)
=
\mathbb E_{g\sim q}
\left[Y(1,g)-Y(0,g)\right]
\]

A whole-policy comparison requires an estimand that includes the policies'
different induced exposures.

### Analysis Plan

Prespecify:

- Population and assignment unit.
- Comparison conditions.
- Outcome windows and exposure denominators.
- Superiority and noninferiority hypotheses.
- Meaningful margins.
- Multiplicity and gatekeeping.
- Safety stopping rules.
- Withdrawal, blocking, switching, and format-change handling.
- Assignment-based and per-protocol analyses.
- Missing-data bounds and tipping-point sensitivity.
- Consistency, exchangeability, positivity, and interference assumptions.

Do not assume missing at random without justification.

Use a shared exposure-definition register for trial and safety reporting.
Explain denominator changes rather than silently comparing unlike rates.

Simulate candidate assignment strategies before recruitment without collecting
additional real relationship graphs solely for that purpose.

## Conformance Requirements

The suite must cover:

- Private-edit content and key-set preservation.
- Absence of publication events.
- No-op edits.
- Concurrent and out-of-order writes.
- Serialization and validated immutable reconstruction.
- Distinct empty, unset, absent, and unknown states.
- Restriction precedence.
- Eligibility capability isolation.
- Field-scoped disclosure.
- Snapshot misuse as authorization.
- Withdrawal during retries and partial failures.
- Replay resistance.
- Derived-cache invalidation.
- Prohibited ranking and reputation paths.
- Diagnostic-channel leakage.

Use property-based tests, decision tables, integration probes, and adversarial
schedules.

Record runtime, runner, dependencies, configuration, seeds, limitations, and
reproduction steps.

## Assumption Register

Each assumption requires an owner and revalidation trigger.

Required assumptions include:

- Unselected criteria impose no constraint.
- Mutual-introduction symmetry has a limited scope.
- Private edits use optimistic concurrency.
- Empty intentions mean none selected.
- Snapshots are dated statements.
- Eligibility is advisory.
- Clarification is non-notifying.
- Sensitive records stay outside ranking and reputation.

Unassigned ownership blocks release.

## Release Assurance

Every mandatory obligation must pass and remain applicable:

\[
\operatorname{ReleaseEligible}
=
\bigwedge_k
\left(
\operatorname{Pass}_k
\land
\operatorname{Current}_k
\right)
\]

Evidence records include scope, owner, reference, limitations, review time,
expiration, and invalidation conditions.

Architecture or configuration changes can invalidate evidence before expiration.

Missing, failed, expired, invalidated, ambiguous, or scope-mismatched evidence
blocks release eligibility.

Passing this gate does not itself execute deployment.

## Claim Limits

Reference-model tests do not establish production non-leakage.

Technical conformance does not establish member comprehension, welfare,
accessibility, legal compliance, or relationship benefit.

Absence of observed leaks is a bounded observation, not proof of universal
non-leakage.

The accountable object is the system and its operations—not a member's perceived
worthiness, desirability, or progress toward partnership.
