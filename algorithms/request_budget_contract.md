# Request Budget Integration Contract

Status: Proposed engineering and research specification.

This document does not establish implementation, deployment readiness, legal
compliance, accessibility, or member benefit.

## Purpose

Limit member-originated social-request volume without authorizing contact,
inferring intent, ranking people, or restricting essential service controls.

Budget admission is advisory until a durable reservation is created.
A reservation is not authorization to deliver.

Privacy, accounting correctness, authorization, accessibility, and governance
remain separate assurance obligations.

## Attribution

Contributor attribution belongs in separately configured document-credit metadata.

Attribution does not establish identity, consent, capability authorization,
execution evidence, or authority over another person or system.

## Core Invariants

- Budget evaluation does not send requests or publish private information.
- An allowed calculation does not reserve capacity.
- A reservation does not override blocking, withdrawal, or authorization.
- Private intentions and sensitive communications are not budget inputs.
- Rejected requests do not generate recipient notifications.
- Remaining allowance and internal denial reasons are not sender-facing data.
- Members may select zero social-request allowance.
- Limits do not suppress reporting, appeal, accessibility, or account recovery.
- Accounting errors do not establish misconduct.
- Results do not become trust, desirability, readiness, or reputation scores.

## Category Boundary

The evaluator applies only to explicitly designated member-originated
social-request categories.

Every counted request contributes to:

- Its sender-to-recipient count.
- The corresponding recipient-wide count.

Both counts must use the same category, window, reservation lifecycle, and
accounting rules.

### Essential Service Paths

The following do not use the social-request budget:

- Authentic platform safety notices.
- Reporting, correction, and appeal operations.
- Responses from authorized governance reviewers.
- Accessibility assistance and service notices.
- Account-security and recovery messages.
- Required legal communications.

These paths require authenticated service authority, narrow purposes, and
separate abuse protections.

A member cannot obtain an exemption by labeling an ordinary message as safety,
accessibility, governance, or legal communication.

Essential paths must not relay ordinary member-authored contact around a block.

Exemption from a social-request budget is not exemption from access control,
purpose limitation, privacy, or operational abuse protection.

## Domain Semantics

### Numeric Inputs

Counts and limits are nonnegative built-in integers.

Reject:

- Booleans.
- Floating-point values.
- Integer subclasses.
- Implicit string conversion.
- Negative values.

An adapter may explicitly convert supported external numeric types only after
checking exactness and configured bounds.

Validate an explicit set of count fields. Adding metadata must not silently
subject it to count validation.

### Count Consistency

The sender count is a subset of the recipient-wide count under the applicable
category and accounting rules:

\[
N_{\mathrm{sender}}\leq N_{\mathrm{total}}
\]

A violation means the snapshot is inconsistent with this contract.

It does not identify the cause. Diagnosis must distinguish caller misuse,
mismatched windows, stale reads, and internal defects.

### Positive Bundles

The request quantity must be a positive integer.

Zero is prohibited by this operation contract. A caller requiring a no-op must
skip evaluation rather than interpret an empty bundle as permission.

Every bundle unit must use the same:

- Sender and recipient.
- Category and window.
- Accounting rules.
- Applicable limit configuration.

Bundle allowance is an all-or-nothing calculation, not a bulk-contact feature,
cross-recipient approval, or delivery transaction.

## Effective Limits

The effective sender and recipient-wide limits are:

\[
\ell_s=\min(L_s,C_s)
\]

\[
\ell_t=\min(L_t,C_t)
\]

Member-selected limits may be stricter than platform ceilings.

Platform ceilings and their consequences must be understandable to recipients
through their settings and review interfaces.

An explanation must not disclose another member's private information.

## Remaining Allowance in a Snapshot

Use the term "remaining allowance in this snapshot," not reserved capacity.

\[
r=\max(0,\min(\ell_s-N_s,\ell_t-N_t))
\]

This value is advisory. It has no independent freshness or reservation guarantee.

Report sender and recipient-wide boundary conditions independently:

- Below the effective limit.
- Exactly at the effective limit.
- Above the effective limit.

Above-limit usage may result from an approved reduction. It is not automatically
an accounting defect or misconduct finding.

Do not clamp historical usage to a newly lowered ceiling.

## Admission Rule

For a positive quantity \(b\):

\[
\operatorname{Allow}
\iff
N_s+b\leq\ell_s
\land
N_t+b\leq\ell_t
\]

On denial:

\[
N'_s=N_s,\qquad N'_t=N_t
\]

On allowance:

\[
N'_s=N_s+b,\qquad N'_t=N_t+b
\]

The evaluator must verify these postconditions before returning.

### Denial Precedence

Recipient-total-first precedence is an explicit internal presentation policy.

When both limits would be exceeded, it selects a deterministic primary reason.
It does not establish mathematical priority, greater fault, or member intent.

Boundary conditions remain separately available to authorized administrative
consumers.

Malformed input is an error, not another admission outcome.

If denial presentation differs across experimental conditions, include that
difference in the treatment definition.

## Snapshot Versus Reservation

Projected output counts are not authoritative state.

An integrator must not persist them as authoritative merely because evaluation
returned allowance.

Authoritative accounting requires a durable reservation receipt issued by the
reservation adapter and bound to:

- The applicable parties and logical operation.
- Category and window.
- Quantity.
- Limit configuration.
- Idempotent retry semantics.
- Reservation lifecycle.

These bindings are internal and must not expose sensitive account or relationship
information.

Persisted diagnostic snapshots must retain their category, window, capture
context, and non-authoritative status.

Repeated evaluation of the same snapshot does not accumulate usage.

## Limit-Change Preview

Before commitment, an accessible preview must explain:

- The proposed effective limit.
- Whether a platform ceiling is binding.
- Whether existing usage is at or above the proposed limit.
- The effect on future requests.
- Applicable window behavior.
- The treatment of uncommitted reservations.
- How to revise the setting.

The preview need not add a modal or a separate confirmation click.

Commit the reviewed configuration atomically. Refresh the preview when relevant
configuration changes before commitment.

Do not expose sender identities or rejected attempts through the preview.

### Effects of a Change

- Historical admissions remain historical facts.
- Do not clamp usage or delete accounting history.
- Current authorization and restrictions remain necessary before delivery.
- Raising a limit does not automatically deliver previously rejected requests.
- Lowering a limit does not withdraw unrelated permissions.
- Cancellation, expiry, and reservation refund behavior must be explicit.
- No minimum openness or new-sender allowance is required.

Members may choose zero allowance for new social requests.

## Layered Interfaces

### Domain Layer

Validates snapshots, quantities, policies, and results.

It performs no external operations.

### Pure Evaluator

Accepts validated values and returns an advisory result.

It has no clock, logger, database, network, persistence, or delivery capability.

Do not inject no-op versions of forbidden capabilities.

### Durable Reservation Adapter

Atomically checks current accounting and records an allowed reservation.

Required properties:

- Durable idempotency.
- Window-bound accounting.
- Consistent updates across workers.
- Explicit expiry and cancellation rules.
- Defined retry behavior.
- Defined recovery after partial failure.
- No assumption that an uncertain outcome means successful reservation.

Refund rules must resist repeated reserve-and-cancel flooding.

The adapter must not treat an old advisory result as a substitute for checking
current state.

### Delivery Gate

Checks:

- Current action-specific authorization.
- Current blocks and restrictions.
- Withdrawal and expiry.
- Reservation validity.
- Applicable limit-change policy.
- Operation and payload binding.

A reservation never overrides another member's refusal or withdrawn permission.

The implementation defines commitment and its ordering relative to withdrawal.

A permission check followed by an independently executable send is insufficient
to establish an atomic withdrawal guarantee.

### Telemetry Adapter

Receives only approved diagnostic projections.

It must not receive raw intent histories, private message content, or unnecessary
relationship information.

Budget diagnostics do not feed advertising, ranking, or reputation.

## Errors and Compatibility

Distinguish:

- Input validation error.
- Inconsistent snapshot.
- Evaluator postcondition failure.
- Reservation conflict.
- Dependency unavailable.
- Outcome unresolved.

Do not classify every inconsistent snapshot as caller fault or misconduct.

Publish the supported public interface. Keep implementation helpers private.

Version changes to:

- Admission outcomes.
- Denial precedence.
- Quantity semantics.
- Numeric-type policy.
- Result fields.
- Accounting and refund rules.

Document migration before downstream adoption.

Unsupported contracts must not silently broaden allowance or permission.

## Administrative CLI

Keep nonnegative count parsing separate from positive quantity parsing.

Preserve whether an optional quantity argument was explicitly supplied before
applying its default.

Arguments requiring budget mode must be rejected outside that mode, including
when their supplied value equals the default.

Use the argument parser's documented error path for invalid CLI input.

Document distinct outcomes for:

- Help.
- Allowed calculation.
- Denied calculation.
- Invalid input.
- Passing tests.
- Failing tests.

The CLI is administrative by intended use, not by authentication. Its invocation,
output capture, and deployment environment require separate controls.

Use a stable interpreter-version API for reproducibility.

## Logging

Logging remains outside evaluation.

The emitting application controls:

- Handler configuration.
- Propagation.
- Destinations.
- Metadata enrichment.
- Access.
- Retention.
- Deletion.

A permitted summary may contain an admission boolean and fixed explanatory text.

It must not contain remaining allowance, counts, denial reasons, account details,
or sensitive operation context.

A named logger alone does not guarantee single emission or privacy-safe handling.

Even Boolean summaries can reveal activity patterns when combined with timing
or other records.

## Explanations and Contestability

### Sender-Facing

Do not reveal:

- Recipient remaining allowance.
- Recipient private settings.
- Another member's block.
- Whether a particular recipient changed limits.

Provide an understandable, privacy-preserving explanation and a correction route
for suspected platform or accounting errors.

### Recipient-Facing

Explain the member's own effective settings, binding platform ceilings, and
consequences of changes.

Provide review for platform-imposed restrictions and correction for accounting
errors.

An appeal cannot override another member's refusal or compel contact.

Reporting, appeal, accessibility assistance, and account recovery remain available
when social-request allowance is zero.

## Research Requirements

Evaluate the combined system:

- Per-sender limits.
- Recipient-wide aggregation.
- Retry deduplication.
- Reservation lifecycle.
- Delivery protections.
- Member understanding of settings.

Prespecify:

- Flood-containment outcomes.
- Exposure denominators.
- Optional recipient-reported wantedness.
- Capacity-capture scenarios.
- Missing-response handling.
- Uncertainty.
- Policy-change governance.

Sender disappointment is not evidence of a false positive.

Do not expose suppressed senders merely to obtain wantedness labels.

Suppression findings do not automatically justify weaker limits. Policy
relaxation requires separate review and must not silently raise member-selected
limits.

## Conformance and Testing

Required layers:

- Unit and decision-table tests.
- Property-based tests.
- Shared-fixture conformance.
- Reservation integration tests.
- Concurrent history checking.
- Failure injection.
- Window-boundary tests.
- Retry and cancellation-abuse tests.
- Flood and capacity-capture simulation.
- Accessible settings and recovery tests.
- Essential-path isolation tests.

Assert the bounded enumeration size:

\[
\left(\sum_{t=0}^{4}(t+1)\right)
\times4\times4\times3
=720
\]

Record:

- Runtime.
- Runner.
- Dependencies.
- Configuration.
- Reproduction seeds.
- Tested scope.
- Limitations.

A bounded enumeration supports only its tested domain. Property-based testing
also requires a stated generator scope and does not establish universal
correctness.

## Continuous Integration

Applicable tests must run on relevant changes and block acceptance on failure.

A manually available self-test is not evidence that a CI gate exists.

Changes to accounting, category routing, authorization, delivery, or telemetry
must trigger the relevant integration and regression suites.

## Nonfunctional Requirements

Before release, assign owners and acceptance criteria for:

- Admission and reservation latency under stated load.
- Timeout and retry behavior.
- Counter consistency across workers.
- Idempotency retention.
- Failure recovery.
- Window-clock authority.
- Input-size bounds.
- Diagnostic access and retention.
- Evidence invalidation after architectural changes.

A timeout must not default to allowance.

An unresolved reservation outcome must be reconciled before retrying in a way
that could duplicate accounting or delivery.

Essential service paths retain separate availability requirements.

## Release Assurance

Release evidence must establish the reviewed implementation boundary.

Required evidence includes:

- Correct category routing.
- Atomic reservation behavior.
- Retry deduplication.
- Current delivery checks.
- Withdrawal ordering.
- Accessible controls.
- Privacy-preserving explanations.
- Essential-path availability.
- Restricted diagnostics.
- Applicable CI results.

Evidence must remain current for the reviewed build, configuration, and
architecture.

## Claim Limits

Evaluator isolation is not a safety guarantee for the surrounding system.

Passing local tests does not establish atomic reservation, production flood
containment, fairness, accessibility, legal compliance, or member benefit.

No calculation or reservation grants permission to contact another person.

The accountable object is the system and its operations—not a member's worth,
desirability, or progress toward partnership.
