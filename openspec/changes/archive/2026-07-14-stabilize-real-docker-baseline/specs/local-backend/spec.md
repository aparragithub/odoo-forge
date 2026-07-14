# Delta for Local Docker Backend

## ADDED Requirements

### Requirement: Real-Docker baseline provides opt-in lifecycle evidence

The integration evidence MUST remain opt-in and MUST validate the canonical local Docker lifecycle without changing production lifecycle, volume, image, credential, or status semantics. The evidence MUST use an isolated project-factory Odoo image and a pinned official PostgreSQL image.

#### Scenario: Prerequisites are unavailable

- GIVEN Docker executable or daemon access is unavailable
- WHEN the explicitly selected integration test starts
- THEN it is skipped with a clear prerequisite reason and no lifecycle failure is reported

#### Scenario: Prerequisites are available

- GIVEN Docker access, the project-factory Odoo image, and the pinned official PostgreSQL image are available
- WHEN the opt-in test executes
- THEN failures after prerequisite detection fail the test rather than being skipped

#### Scenario: Required images and identity are used

- GIVEN an isolated test fixture
- WHEN the lifecycle is provisioned
- THEN Odoo uses the project-factory image, PostgreSQL uses the pinned official image, and every resource has a unique test-owned identity

#### Scenario: Secrets remain safe

- GIVEN credentials are required by the disposable fixture
- WHEN commands, assertions, diagnostics, and verification evidence are produced
- THEN secret values are absent from arguments, logs, output, committed fixtures, and recorded evidence

#### Scenario: Host ports are collision-resistant

- GIVEN the lifecycle is provisioned on a host with unrelated services
- WHEN containers are started
- THEN host ports are allocated ephemerally and the observed mappings are used for assertions

#### Scenario: Readiness is bounded

- GIVEN a cold image boot or a service that never becomes ready
- WHEN lifecycle startup is attempted
- THEN readiness waits are bounded, successful startup proves both database reachability and Odoo health, and timeout failure is reported

#### Scenario: Run, status, and stop complete

- GIVEN startup reaches readiness
- WHEN the test performs `run`, `status`, and `stop`
- THEN `run` returns a reachable instance, `status` reports its live running state, and `stop` completes successfully

#### Scenario: Stop preserves lifecycle volumes

- GIVEN the test-owned instance has named lifecycle volumes
- WHEN `stop` removes the instance
- THEN the named lifecycle volumes remain present, while containers and the lifecycle network are absent

#### Scenario: Cleanup is ownership-scoped

- GIVEN setup succeeds, partially succeeds, or fails
- WHEN final test cleanup runs
- THEN cleanup is unconditional, deletes only uniquely test-owned disposable resources, and never deletes pre-existing or unrelated resources

#### Scenario: Residual checks are independent

- GIVEN lifecycle execution or cleanup reports an error
- WHEN residual checks run
- THEN independent label/name-based checks identify any remaining test-owned containers, networks, or disposable resources without treating preserved lifecycle volumes as leaks

#### Scenario: The default suite remains daemon-independent

- GIVEN the repository's default test command is executed
- WHEN tests are collected and run
- THEN this integration evidence is excluded; an explicit integration command is required to exercise Docker

#### Scenario: Verification records evidence

- GIVEN the baseline test has been exercised
- WHEN verification is completed
- THEN the receipt records Docker client/server versions, exact commands and results, readiness outcome, stop-preservation result, cleanup result, and residual checks

#### Scenario: Production defects are extracted

- GIVEN the real-Docker evidence exposes a defect in production behavior
- WHEN verification classifies the finding
- THEN this change fails or stops without masking the defect, and the defect is recorded as a separate SDD change rather than changing production code here
