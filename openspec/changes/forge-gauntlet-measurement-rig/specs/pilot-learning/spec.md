# Spec Delta

## Purpose

Maintains separate evidence-backed playbook revisions and tests specific lessons without mistaking a game result for proven strategic improvement.

## ADDED Requirements

### Requirement: Decision-time evidence

A learning proposal SHALL identify a recorded decision and distinguish information known then from hindsight or previously hidden facts.

#### Scenario: Unsupported lesson

- **WHEN** a review asserts a mistake without a source decision or decision-time evidence
- **THEN** the proposal is rejected as unsupported

### Requirement: Versioned tentative lessons

A lesson SHALL state an alternative action and a testable expected consequence, preserve the old playbook and create a separate tentative revision for its own seat.

#### Scenario: Lesson created

- **WHEN** a valid review proposes a change
- **THEN** the old version remains available and only that seat receives the new tentative version

### Requirement: Explicit reuse of learning

The next game SHALL record and load the selected revised playbook; revisions MUST NOT be silently applied mid-match.

#### Scenario: Next game

- **WHEN** a revised playbook is selected after review
- **THEN** the next pilot session names and loads that exact version

### Requirement: Controlled lesson check

A quality claim SHALL include a controlled recorded-decision replay or rules-checked scenario showing the selected alternative and expected consequence. One win/loss alone MUST NOT establish improvement.

#### Scenario: Lesson tested

- **WHEN** a tentative revision changes an action in a controlled scenario
- **THEN** the evidence records the old/new actions and actual rules outcome, with any unproven claims labelled
