"""RED-first tests for the real byte-level `MaskTransform` (scratch-DB round trip).

A `pg_dump --format=custom` archive is opaque: its rows cannot be rewritten in
place. So masking restores the captured dump into a THROWAWAY container,
applies one `UPDATE` per `AnonymizationRule` there, re-dumps, and stages the
masked bytes under a new digest. The raw bytes therefore never reach the
delivery target — the anonymize-before-delivery contract holds.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import IO, NoReturn, cast

import pytest

from odoo_forge.anonymization.policy import AnonymizationRule, MaskStrategy
from odoo_forge.data_artifacts.contracts import (
    ArtifactComponentKind,
    ArtifactDigest,
    RestoreSetComponent,
)
from odoo_forge.data_artifacts.staging import StagedArtifactStore
from odoo_forge_postgres_docker.mask_transform import (
    DockerMaskRunner,
    MaskBinaryUnavailableError,
    MaskColumnTypeUnsupportedError,
    MaskCommandFailedError,
    MaskNotNullColumnError,
    MaskPersistenceError,
    MaskScratchNotIsolatedError,
    MaskScratchUnavailableError,
    MaskSelectorNotFoundError,
    MaskTimeoutError,
    MaskUniqueColumnCollisionError,
    ScratchDatabase,
    ScratchDatabaseFactory,
    docker_scratch_database,
    make_docker_mask_transform,
)
from odoo_forge_postgres_docker.staged_store import FilesystemStagedArtifactStore

_RAW = b"raw-pii-dump-bytes"
_MASKED = b"masked-dump-bytes"


def _digest_of(payload: bytes) -> ArtifactDigest:
    return ArtifactDigest(algorithm="sha256", value=hashlib.sha256(payload).hexdigest())


def _store_with_raw(tmp_path: Path, payload: bytes = _RAW) -> FilesystemStagedArtifactStore:
    store = FilesystemStagedArtifactStore(tmp_path / "artifact-store")
    source = tmp_path / "raw-dump"
    source.write_bytes(payload)
    store.stage(_digest_of(payload), source)
    return store


def _database_component(payload: bytes = _RAW) -> RestoreSetComponent:
    return RestoreSetComponent(
        kind=ArtifactComponentKind.DATABASE,
        opaque_component_ref="database-odoo-source",
        format_version="pg_dump-custom-v1",
        digest=_digest_of(payload),
    )


def _rule(
    table: str = "res_partner",
    column: str = "email",
    strategy: MaskStrategy = MaskStrategy.HASH,
    static_value: str | None = None,
) -> AnonymizationRule:
    return AnonymizationRule(
        table=table, column=column, mask_strategy=strategy, static_value=static_value
    )


class _RecordingRunner:
    """Records every scratch-container invocation, answers schema introspection, and
    fakes the re-dump output.

    `columns` maps (table, column) -> `table|column|data_type|is_nullable|is_unique`
    facts. The default answers every selector as a nullable, non-unique `text` column,
    i.e. maskable by every strategy, so tests that are not about schema compatibility
    do not have to describe one.
    """

    def __init__(
        self,
        *,
        masked: bytes = _MASKED,
        returncode: int = 0,
        data_type: str = "text",
        is_unique: bool = False,
        is_nullable: bool = True,
        columns: dict[tuple[str, str], tuple[str, bool, bool]] | None = None,
        missing: bool = False,
    ) -> None:
        self.calls: list[list[str]] = []
        self.stdin_bytes: list[bytes] = []
        self._masked = masked
        self._returncode = returncode
        self._data_type = data_type
        self._is_unique = is_unique
        self._is_nullable = is_nullable
        self._columns = columns
        self._missing = missing

    def _introspection_rows(self, statement: str) -> bytes:
        """Answer the introspection query for whatever selectors it asked about."""
        if self._missing:
            return b""
        pairs = re.findall(r"\('([^']*)', '([^']*)'\)", statement)
        lines = []
        for table, column in pairs:
            if self._columns is not None:
                found = self._columns.get((table, column))
                if found is None:
                    continue
                data_type, is_unique, is_nullable = found
            else:
                data_type, is_unique, is_nullable = (
                    self._data_type,
                    self._is_unique,
                    self._is_nullable,
                )
            lines.append(
                f"{table}|{column}|{data_type}|"
                f"{'YES' if is_nullable else 'NO'}|{'t' if is_unique else 'f'}"
            )
        return ("\n".join(lines) + "\n").encode() if lines else b""

    def __call__(
        self,
        argv: Sequence[str],
        *,
        stdin: IO[bytes] | None = None,
        stdout: IO[bytes] | None = None,
        timeout: float,
    ) -> subprocess.CompletedProcess[bytes]:
        self.calls.append(list(argv))
        if stdin is not None:
            self.stdin_bytes.append(stdin.read())
        if stdout is not None:
            payload = (
                self._introspection_rows(argv[argv.index("-tAc") + 1])
                if "-tAc" in argv
                else self._masked
            )
            stdout.write(payload)
            stdout.flush()
        return subprocess.CompletedProcess(list(argv), self._returncode)

    def statements(self) -> list[str]:
        """Every `-c <sql>` payload, in invocation order (introspection uses `-tAc`)."""
        return [argv[argv.index("-c") + 1] for argv in self.calls if "-c" in argv]


def _scratch_factory(
    opened: list[str] | None = None, closed: list[str] | None = None
) -> ScratchDatabaseFactory:
    @contextmanager
    def _factory() -> Iterator[ScratchDatabase]:
        scratch = ScratchDatabase(container="odoo-forge-mask-test", database="maskdb")
        if opened is not None:
            opened.append(scratch.container)
        try:
            yield scratch
        finally:
            if closed is not None:
                closed.append(scratch.container)

    return _factory


class _StageFailingStore:
    """A store that resolves raw bytes fine but cannot take custody of masked ones."""

    def __init__(self, inner: FilesystemStagedArtifactStore) -> None:
        self._inner = inner

    def open_component(self, component: RestoreSetComponent) -> Path:
        return self._inner.open_component(component)

    def stage(self, digest: ArtifactDigest, source_path: Path) -> None:
        raise RuntimeError("simulated stage failure")

    def put(self, ref: object, manifest: object) -> None:
        raise NotImplementedError

    def resolve(self, ref: object) -> object:
        raise NotImplementedError

    def discard(self, ref: object) -> object:
        raise NotImplementedError


class TestEmptyPolicyIsAPureNoOp:
    """An empty policy must not round-trip through a scratch container: `pg_dump` is
    not byte-stable, so a pointless round trip would churn the digest and spin up a
    container holding raw PII for nothing."""

    def test_no_rules_returns_the_component_unchanged(self, tmp_path: Path) -> None:
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path),
            runner=runner,
            scratch_factory=_scratch_factory(),
        )
        component = _database_component()

        assert transform(component, ()) == component

    def test_no_rules_never_starts_a_scratch_container(self, tmp_path: Path) -> None:
        opened: list[str] = []
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path),
            runner=runner,
            scratch_factory=_scratch_factory(opened),
        )

        transform(_database_component(), ())

        assert opened == []
        assert runner.calls == []


class TestFilestoreComponentIsPassedThrough:
    def test_a_filestore_component_is_never_masked(self, tmp_path: Path) -> None:
        """D6: the filestore component is a metadata-only placeholder with no staged
        blob, so there is nothing to mask and `open_component` must never be called."""
        opened: list[str] = []
        component = RestoreSetComponent(
            kind=ArtifactComponentKind.FILESTORE,
            opaque_component_ref="filestore-empty-v1",
            format_version="empty-v1",
            digest=_digest_of(b""),
        )
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path),
            runner=_RecordingRunner(),
            scratch_factory=_scratch_factory(opened),
        )

        assert transform(component, (_rule(),)) == component
        assert opened == []


class TestScratchRoundTrip:
    def test_the_raw_dump_is_restored_into_the_scratch_database(self, tmp_path: Path) -> None:
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )

        transform(_database_component(), (_rule(),))

        restore_argv = next(argv for argv in runner.calls if "pg_restore" in argv)
        assert restore_argv[:4] == ["docker", "exec", "-i", "odoo-forge-mask-test"]
        assert "-d" in restore_argv and "maskdb" in restore_argv
        assert runner.stdin_bytes == [_RAW], "the staged raw bytes stream into pg_restore"

    def test_the_masked_dump_is_staged_and_returned_under_its_new_digest(
        self, tmp_path: Path
    ) -> None:
        store = _store_with_raw(tmp_path)
        transform = make_docker_mask_transform(
            store=store, runner=_RecordingRunner(), scratch_factory=_scratch_factory()
        )

        masked = transform(_database_component(), (_rule(),))

        assert masked.digest == _digest_of(_MASKED)
        assert masked.digest != _database_component().digest
        assert store.open_component(masked).read_bytes() == _MASKED

    def test_the_component_identity_and_format_survive_masking(self, tmp_path: Path) -> None:
        """Only the digest changes: the coordinator (D11) re-persists the manifest, and
        the component must stay the same component, in the same archive format."""
        original = _database_component()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path),
            runner=_RecordingRunner(),
            scratch_factory=_scratch_factory(),
        )

        masked = transform(original, (_rule(),))

        assert masked.kind is original.kind
        assert masked.opaque_component_ref == original.opaque_component_ref
        assert masked.format_version == original.format_version

    def test_the_re_dump_uses_the_same_custom_archive_format(self, tmp_path: Path) -> None:
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )

        transform(_database_component(), (_rule(),))

        dump_argv = next(argv for argv in runner.calls if "pg_dump" in argv)
        assert "--format=custom" in dump_argv

    def test_restore_masking_and_re_dump_run_in_that_order(self, tmp_path: Path) -> None:
        """Re-dumping before the UPDATEs would ship unmasked bytes under a digest that
        claims to be anonymized — the exact failure this whole path exists to prevent."""
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )

        transform(_database_component(), (_rule(),))

        stages = [
            next(tool for tool in ("pg_restore", "psql", "pg_dump") if tool in argv)
            for argv in runner.calls
            if any(tool in argv for tool in ("pg_restore", "psql", "pg_dump"))
        ]
        # restore, then schema introspection, then the rule's UPDATE, then the re-dump.
        assert stages == ["pg_restore", "psql", "psql", "pg_dump"]
        assert "-tAc" in runner.calls[1], "introspection must precede any UPDATE"
        assert "-c" in runner.calls[2]

    def test_the_scratch_container_is_torn_down_on_success(self, tmp_path: Path) -> None:
        closed: list[str] = []
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path),
            runner=_RecordingRunner(),
            scratch_factory=_scratch_factory(closed=closed),
        )

        transform(_database_component(), (_rule(),))

        assert closed == ["odoo-forge-mask-test"]

    def test_the_scratch_container_is_torn_down_when_masking_fails(self, tmp_path: Path) -> None:
        """The scratch database holds the RAW, un-anonymized data. A failure that left
        it running would leave unmasked PII in a container nobody is tracking."""
        closed: list[str] = []
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path),
            runner=_RecordingRunner(returncode=1),
            scratch_factory=_scratch_factory(closed=closed),
        )

        with pytest.raises(MaskCommandFailedError):
            transform(_database_component(), (_rule(),))

        assert closed == ["odoo-forge-mask-test"]


class TestMaskStrategySql:
    """Every `MaskStrategy` in the fixed v1 vocabulary maps to one `UPDATE`."""

    def _statement_for(self, tmp_path: Path, rule: AnonymizationRule) -> str:
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )
        transform(_database_component(), (rule,))
        return runner.statements()[0]

    def test_hash_replaces_the_value_with_a_digest_of_itself(self, tmp_path: Path) -> None:
        statement = self._statement_for(tmp_path, _rule(strategy=MaskStrategy.HASH))
        assert statement == 'UPDATE "res_partner" SET "email" = md5("email"::text)'

    def test_nullify_sets_the_column_to_null(self, tmp_path: Path) -> None:
        statement = self._statement_for(tmp_path, _rule(strategy=MaskStrategy.NULLIFY))
        assert statement == 'UPDATE "res_partner" SET "email" = NULL'

    def test_redact_replaces_the_value_with_a_fixed_marker(self, tmp_path: Path) -> None:
        statement = self._statement_for(tmp_path, _rule(strategy=MaskStrategy.REDACT))
        assert statement == 'UPDATE "res_partner" SET "email" = \'[REDACTED]\''

    def test_static_replace_uses_the_configured_value(self, tmp_path: Path) -> None:
        statement = self._statement_for(
            tmp_path,
            _rule(strategy=MaskStrategy.STATIC_REPLACE, static_value="masked@example.test"),
        )
        assert statement == 'UPDATE "res_partner" SET "email" = \'masked@example.test\''

    def test_every_v1_strategy_is_implemented(self, tmp_path: Path) -> None:
        """A new `MaskStrategy` member must not silently fall through to a no-op."""
        for strategy in MaskStrategy:
            static_value = "x" if strategy is MaskStrategy.STATIC_REPLACE else None
            statement = self._statement_for(
                tmp_path, _rule(strategy=strategy, static_value=static_value)
            )
            assert statement.startswith('UPDATE "res_partner" SET "email" = ')

    def test_one_update_is_issued_per_rule(self, tmp_path: Path) -> None:
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )

        transform(
            _database_component(),
            (
                _rule(column="email"),
                _rule(column="phone", strategy=MaskStrategy.NULLIFY),
                _rule(table="res_users", column="login", strategy=MaskStrategy.REDACT),
            ),
        )

        assert len(runner.statements()) == 3

    def test_masking_aborts_on_the_first_error_rather_than_continuing(self, tmp_path: Path) -> None:
        """`ON_ERROR_STOP` plus a nonzero exit: a rule that cannot be applied (missing
        table or column) fails the whole transform. Delivering a dump stamped
        'anonymized' with one rule silently skipped is the worst possible outcome."""
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )

        transform(_database_component(), (_rule(),))

        psql_argv = next(argv for argv in runner.calls if "psql" in argv)
        assert "ON_ERROR_STOP=1" in psql_argv


class TestUnmaskableColumnsFailClosedWithANamedReason:
    """Follow-up #175 items 1-2. These rules were already rejected — by Postgres, mid
    batch, surfacing as a generic `MaskCommandFailedError` with the real reason sent to
    `DEVNULL`. An operator got "masking command failed" and nothing to act on. Now the
    schema is read up front and each incompatibility names itself BEFORE any row is
    touched, so the scratch database is never left half-masked either."""

    def _transform_for(
        self, tmp_path: Path, runner: _RecordingRunner
    ) -> Callable[[RestoreSetComponent, tuple[AnonymizationRule, ...]], RestoreSetComponent]:
        return make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )

    def test_hash_on_a_non_text_column_names_the_type_problem(self, tmp_path: Path) -> None:
        """Verified against a real backend in the `real_docker` harness: Postgres has no
        implicit text->integer assignment cast, so `md5(col::text)` is rejected."""
        runner = _RecordingRunner(data_type="integer")
        transform = self._transform_for(tmp_path, runner)

        with pytest.raises(MaskColumnTypeUnsupportedError) as exc_info:
            transform(_database_component(), (_rule(strategy=MaskStrategy.HASH),))

        assert str(exc_info.value) == MaskColumnTypeUnsupportedError.public_detail
        assert runner.statements() == [], "no UPDATE may run once a rule is known unmaskable"

    def test_redact_on_a_unique_column_names_the_constraint_problem(self, tmp_path: Path) -> None:
        """Collapsing a UNIQUE column to one literal duplicates on the second row.
        `login` and `email` — the most obvious targets — are commonly UNIQUE."""
        runner = _RecordingRunner(is_unique=True)
        transform = self._transform_for(tmp_path, runner)

        with pytest.raises(MaskUniqueColumnCollisionError) as exc_info:
            transform(_database_component(), (_rule(strategy=MaskStrategy.REDACT),))

        assert str(exc_info.value) == MaskUniqueColumnCollisionError.public_detail
        assert runner.statements() == []

    def test_static_replace_on_a_unique_column_is_refused_too(self, tmp_path: Path) -> None:
        runner = _RecordingRunner(is_unique=True)
        transform = self._transform_for(tmp_path, runner)

        with pytest.raises(MaskUniqueColumnCollisionError):
            transform(
                _database_component(),
                (_rule(strategy=MaskStrategy.STATIC_REPLACE, static_value="x"),),
            )

    def test_hash_on_a_unique_column_is_allowed(self, tmp_path: Path) -> None:
        """HASH is deterministic and injective in practice, so distinct inputs stay
        distinct — a UNIQUE column is a legitimate HASH target and must NOT be refused."""
        runner = _RecordingRunner(is_unique=True)
        transform = self._transform_for(tmp_path, runner)

        transform(_database_component(), (_rule(strategy=MaskStrategy.HASH),))

        assert len(runner.statements()) == 1

    def test_nullify_on_a_not_null_column_names_the_constraint_problem(
        self, tmp_path: Path
    ) -> None:
        runner = _RecordingRunner(is_nullable=False)
        transform = self._transform_for(tmp_path, runner)

        with pytest.raises(MaskNotNullColumnError) as exc_info:
            transform(_database_component(), (_rule(strategy=MaskStrategy.NULLIFY),))

        assert str(exc_info.value) == MaskNotNullColumnError.public_detail

    def test_nullify_on_a_non_text_column_is_allowed(self, tmp_path: Path) -> None:
        """`NULL` is assignable to any nullable column regardless of type, so the
        text-assignability check must not over-reject."""
        runner = _RecordingRunner(data_type="integer", is_nullable=True)
        transform = self._transform_for(tmp_path, runner)

        transform(_database_component(), (_rule(strategy=MaskStrategy.NULLIFY),))

        assert len(runner.statements()) == 1

    def test_a_selector_that_does_not_exist_names_itself(self, tmp_path: Path) -> None:
        """A typo in a policy used to reach Postgres as a failing UPDATE; now it is
        caught before the round trip does any work."""
        runner = _RecordingRunner(missing=True)
        transform = self._transform_for(tmp_path, runner)

        with pytest.raises(MaskSelectorNotFoundError) as exc_info:
            transform(_database_component(), (_rule(table="no_such_table"),))

        assert str(exc_info.value) == MaskSelectorNotFoundError.public_detail
        assert runner.statements() == []

    def test_one_bad_rule_blocks_the_whole_batch(self, tmp_path: Path) -> None:
        """Fail-closed is per-BATCH, not per-rule: delivering a dump stamped
        `anonymization_applied` with one rule skipped is the worst outcome."""
        runner = _RecordingRunner(
            columns={
                ("res_partner", "email"): ("text", False, True),
                ("res_partner", "age"): ("integer", False, True),
            }
        )
        transform = self._transform_for(tmp_path, runner)

        with pytest.raises(MaskColumnTypeUnsupportedError):
            transform(
                _database_component(),
                (_rule(column="email"), _rule(column="age", strategy=MaskStrategy.HASH)),
            )

        assert runner.statements() == [], "not even the valid rule may be applied"

    def test_varchar_is_treated_as_maskable(self, tmp_path: Path) -> None:
        runner = _RecordingRunner(data_type="character varying")
        transform = self._transform_for(tmp_path, runner)

        transform(_database_component(), (_rule(strategy=MaskStrategy.REDACT),))

        assert len(runner.statements()) == 1


class TestOneSharedTimeoutBudget:
    """Follow-up #175 item 5: `timeout` was handed afresh to each of the (2 + N)
    commands, so a 20-rule policy on the 3600s default could block ~22 hours before
    anything fired. It is now one budget for the whole round trip."""

    def test_the_budget_is_drawn_down_across_commands_not_reset(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        clock = iter([100.0, 101.0, 103.0, 106.0, 110.0, 115.0, 121.0, 128.0])
        monkeypatch.setattr(
            "odoo_forge_postgres_docker.mask_transform.time.monotonic", lambda: next(clock)
        )
        seen: list[float] = []

        class _TimeoutCapturingRunner(_RecordingRunner):
            def __call__(
                self,
                argv: Sequence[str],
                *,
                stdin: IO[bytes] | None = None,
                stdout: IO[bytes] | None = None,
                timeout: float,
            ) -> subprocess.CompletedProcess[bytes]:
                seen.append(timeout)
                return super().__call__(argv, stdin=stdin, stdout=stdout, timeout=timeout)

        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path),
            runner=_TimeoutCapturingRunner(),
            scratch_factory=_scratch_factory(),
            timeout=100.0,
        )

        transform(_database_component(), (_rule(),))

        assert seen == sorted(seen, reverse=True), "each command must get LESS time, not a reset"
        assert seen[0] < 100.0

    def test_an_exhausted_budget_raises_before_issuing_another_command(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A round trip that has already spent its budget must stop, not keep issuing
        commands each with a fresh allowance."""
        clock = iter([0.0, 1.0, 500.0, 500.0, 500.0, 500.0])
        monkeypatch.setattr(
            "odoo_forge_postgres_docker.mask_transform.time.monotonic", lambda: next(clock)
        )
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path),
            runner=runner,
            scratch_factory=_scratch_factory(),
            timeout=100.0,
        )

        with pytest.raises(MaskTimeoutError):
            transform(_database_component(), (_rule(),))


class TestSqlInjectionSafety:
    def test_identifiers_are_double_quoted(self, tmp_path: Path) -> None:
        """Selectors permit `-`, which is subtraction in an unquoted identifier. The
        selector charset excludes `"`, so double-quoting cannot be escaped out of."""
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )

        transform(
            _database_component(),
            (_rule(table="res-partner", column="e-mail", strategy=MaskStrategy.NULLIFY),),
        )

        assert runner.statements()[0] == 'UPDATE "res-partner" SET "e-mail" = NULL'

    def test_a_static_value_single_quote_is_escaped(self, tmp_path: Path) -> None:
        """`static_value` is the only free-form field in a rule and is NOT covered by
        the selector charset, so it is the one real injection surface."""
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )

        transform(
            _database_component(),
            (
                _rule(
                    strategy=MaskStrategy.STATIC_REPLACE,
                    static_value="'; DROP TABLE res_users; --",
                ),
            ),
        )

        assert (
            runner.statements()[0]
            == "UPDATE \"res_partner\" SET \"email\" = '''; DROP TABLE res_users; --'"
        )

    def test_every_invocation_is_argv_only(self, tmp_path: Path) -> None:
        runner = _RecordingRunner()
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )

        transform(_database_component(), (_rule(),))

        for argv in runner.calls:
            assert all(isinstance(item, str) for item in argv)
            assert argv[0] == "docker"


class TestFailureTaxonomy:
    def _transform(
        self, tmp_path: Path, runner: DockerMaskRunner
    ) -> Callable[[RestoreSetComponent, tuple[AnonymizationRule, ...]], RestoreSetComponent]:
        return make_docker_mask_transform(
            store=_store_with_raw(tmp_path), runner=runner, scratch_factory=_scratch_factory()
        )

    def test_a_nonzero_exit_raises_the_command_failed_error(self, tmp_path: Path) -> None:
        transform = self._transform(tmp_path, _RecordingRunner(returncode=1))

        with pytest.raises(MaskCommandFailedError) as exc_info:
            transform(_database_component(), (_rule(),))

        assert str(exc_info.value) == MaskCommandFailedError.public_detail

    def test_a_missing_docker_binary_raises_the_binary_error(self, tmp_path: Path) -> None:
        class _MissingBinaryRunner:
            def __call__(self, argv: Sequence[str], **kwargs: object) -> NoReturn:
                raise FileNotFoundError("docker")

        transform = self._transform(tmp_path, _MissingBinaryRunner())

        with pytest.raises(MaskBinaryUnavailableError) as exc_info:
            transform(_database_component(), (_rule(),))

        assert str(exc_info.value) == MaskBinaryUnavailableError.public_detail

    def test_a_timeout_raises_the_timeout_error(self, tmp_path: Path) -> None:
        class _TimeoutRunner:
            def __call__(self, argv: Sequence[str], **kwargs: object) -> NoReturn:
                raise subprocess.TimeoutExpired(list(argv), 1.0)

        transform = self._transform(tmp_path, _TimeoutRunner())

        with pytest.raises(MaskTimeoutError) as exc_info:
            transform(_database_component(), (_rule(),))

        assert str(exc_info.value) == MaskTimeoutError.public_detail

    def test_a_store_failure_raises_the_persistence_error(self, tmp_path: Path) -> None:
        transform = make_docker_mask_transform(
            store=cast("StagedArtifactStore", _StageFailingStore(_store_with_raw(tmp_path))),
            runner=_RecordingRunner(),
            scratch_factory=_scratch_factory(),
        )

        with pytest.raises(MaskPersistenceError) as exc_info:
            transform(_database_component(), (_rule(),))

        assert str(exc_info.value) == MaskPersistenceError.public_detail

    def test_an_unavailable_scratch_database_raises_its_own_error(self, tmp_path: Path) -> None:
        @contextmanager
        def _failing_factory() -> Iterator[ScratchDatabase]:
            raise MaskScratchUnavailableError()
            yield  # pragma: no cover - unreachable, keeps this a generator

        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path),
            runner=_RecordingRunner(),
            scratch_factory=_failing_factory,
        )

        with pytest.raises(MaskScratchUnavailableError):
            transform(_database_component(), (_rule(),))


class TestStagedTempFileCleanup:
    def test_the_re_dump_temp_file_is_removed_on_success(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """On success the store MOVES the file into custody; the transform's `finally`
        must find nothing left to clean, and leave no second copy behind."""
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path),
            runner=_RecordingRunner(),
            scratch_factory=_scratch_factory(),
        )

        transform(_database_component(), (_rule(),))

        assert list(tmp_path.glob("odoo-forge-mask-*")) == []

    def test_the_re_dump_temp_file_is_removed_when_the_dump_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        transform = make_docker_mask_transform(
            store=_store_with_raw(tmp_path),
            runner=_RecordingRunner(returncode=1),
            scratch_factory=_scratch_factory(),
        )

        with pytest.raises(MaskCommandFailedError):
            transform(_database_component(), (_rule(),))

        assert list(tmp_path.glob("odoo-forge-mask-*")) == []


class TestDefaultScratchDatabaseFactory:
    """The default factory owns a real throwaway container end to end."""

    def test_it_starts_waits_for_readiness_and_always_removes_the_container(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[list[str]] = []

        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            calls.append(list(argv))
            # `docker inspect` reports the container's networks; empty means isolated.
            return subprocess.CompletedProcess(list(argv), 0, stdout=b"")

        monkeypatch.setattr(subprocess, "run", _fake_run)

        with docker_scratch_database() as scratch:
            assert scratch.container.startswith("odoo-forge-mask-")

        tools = [argv[1] for argv in calls]
        assert tools[0] == "run"
        assert tools[-1] == "rm"
        assert "-f" in calls[-1]
        # Readiness is a real query against the TARGET database, deliberately not
        # `pg_isready`: the postgres entrypoint runs a temporary bootstrap server
        # during initdb, so `pg_isready` reports ready before `POSTGRES_DB` exists and
        # the pg_restore that follows would hit a database that is not there yet.
        assert "pg_isready" not in calls[1]
        assert calls[1][3] == "psql"
        assert "maskdb" in calls[1]
        assert calls[1][-1] == "SELECT 1"

    def test_the_scratch_container_has_no_network_interface(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Review R1-001 (CRITICAL): without `--network none` the container attaches to
        Docker's default bridge, where any neighbouring container can reach its 5432
        directly — no published port needed. This container holds the RAW, unmasked
        database, so the flag is the thing that makes the module's no-network-exposure
        claim true rather than aspirational."""
        calls: list[list[str]] = []

        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            calls.append(list(argv))
            # `docker inspect` reports the container's networks; empty means isolated.
            return subprocess.CompletedProcess(list(argv), 0, stdout=b"")

        monkeypatch.setattr(subprocess, "run", _fake_run)

        with docker_scratch_database():
            pass

        run_argv = calls[0]
        assert "--network" in run_argv
        assert run_argv[run_argv.index("--network") + 1] == "none"

    def test_no_password_is_ever_passed_in_the_container_argv(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Review R1-001 (CRITICAL): a fixed password in `docker run` argv is a
        hardcoded secret readable via `docker inspect`, which `provider.py`'s
        credential contract forbids (secrets reach Postgres only via a bind-mounted
        `POSTGRES_PASSWORD_FILE`). With `--network none` nothing can connect from
        outside, so trust auth carries no secret at all."""
        calls: list[list[str]] = []

        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            calls.append(list(argv))
            # `docker inspect` reports the container's networks; empty means isolated.
            return subprocess.CompletedProcess(list(argv), 0, stdout=b"")

        monkeypatch.setattr(subprocess, "run", _fake_run)

        with docker_scratch_database():
            pass

        run_argv = calls[0]
        assert not any("POSTGRES_PASSWORD" in item for item in run_argv)
        assert "POSTGRES_HOST_AUTH_METHOD=trust" in run_argv

    def test_a_failing_docker_run_is_reported_and_still_cleaned_up(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Follow-up #175 items 3-4: a nonzero `docker run` (bad image, daemon out of
        resources) used to be ignored, burning the whole 60-attempt readiness loop
        before reporting a misleading "never became ready". And because the start call
        sat outside the `try`, nothing guaranteed cleanup of a container the daemon may
        have finished creating anyway."""
        calls: list[list[str]] = []

        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            calls.append(list(argv))
            returncode = 1 if argv[1] == "run" else 0
            return subprocess.CompletedProcess(list(argv), returncode, stdout=b"")

        monkeypatch.setattr(subprocess, "run", _fake_run)

        with pytest.raises(MaskScratchUnavailableError), docker_scratch_database():
            pytest.fail("the body must never run when the container failed to start")

        tools = [argv[1] for argv in calls]
        assert tools == ["run", "rm"], "no readiness polling after a failed start"
        assert calls[-1][1] == "rm", "a failed start is still cleaned up"

    def test_a_client_side_start_failure_still_removes_the_container(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The start call is inside the `try`, so even a client-side raise (the daemon
        may still have created the container) reaches the teardown `finally`."""
        calls: list[list[str]] = []

        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            calls.append(list(argv))
            if argv[1] == "run":
                raise subprocess.TimeoutExpired(list(argv), 1.0)
            return subprocess.CompletedProcess(list(argv), 0, stdout=b"")

        monkeypatch.setattr(subprocess, "run", _fake_run)

        with pytest.raises(MaskTimeoutError), docker_scratch_database():
            pytest.fail("the body must never run when the container failed to start")

        assert calls[-1][1] == "rm"

    def test_the_container_is_removed_even_when_the_body_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[list[str]] = []

        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            calls.append(list(argv))
            # `docker inspect` reports the container's networks; empty means isolated.
            return subprocess.CompletedProcess(list(argv), 0, stdout=b"")

        monkeypatch.setattr(subprocess, "run", _fake_run)

        with pytest.raises(RuntimeError), docker_scratch_database():
            raise RuntimeError("simulated masking failure")

        assert calls[-1][1] == "rm"

    def test_a_container_that_never_becomes_ready_is_reported_and_removed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[list[str]] = []

        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            calls.append(list(argv))
            returncode = 0 if argv[1] in ("run", "rm") else 1
            return subprocess.CompletedProcess(list(argv), returncode, stdout=b"")

        monkeypatch.setattr(subprocess, "run", _fake_run)
        monkeypatch.setattr("time.sleep", lambda _seconds: None)

        with (
            pytest.raises(MaskScratchUnavailableError),
            docker_scratch_database(readiness_attempts=3),
        ):
            pytest.fail("the body must never run for an unready scratch database")

        assert calls[-1][1] == "rm", "an unready container is still removed"

    def test_a_container_attached_to_a_network_is_refused_before_yielding(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Follow-up #175 item 9: trust auth is safe ONLY because of `--network none`.
        That pairing was enforced by a docstring and two argv tests — nothing failed
        closed at runtime if a refactor dropped the flag while keeping trust auth,
        which would leave an unauthenticated database full of raw PII reachable from
        the default bridge. The daemon is now asked what actually happened."""

        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            stdout = b"bridge " if argv[1] == "inspect" else b""
            return subprocess.CompletedProcess(list(argv), 0, stdout=stdout)

        monkeypatch.setattr(subprocess, "run", _fake_run)

        with pytest.raises(MaskScratchNotIsolatedError), docker_scratch_database():
            pytest.fail("raw data must never enter a reachable scratch container")

    def test_an_unreadable_isolation_check_fails_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ "Cannot tell" must read as "not proven isolated", not as "fine"."""

        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            returncode = 1 if argv[1] == "inspect" else 0
            return subprocess.CompletedProcess(list(argv), returncode, stdout=b"")

        monkeypatch.setattr(subprocess, "run", _fake_run)

        with pytest.raises(MaskScratchNotIsolatedError), docker_scratch_database():
            pytest.fail("an unverifiable isolation check must not admit raw data")

    def test_an_isolated_container_passes_the_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`--network none` reports the single network literally named `none`."""

        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            stdout = b"none " if argv[1] == "inspect" else b""
            return subprocess.CompletedProcess(list(argv), 0, stdout=stdout)

        monkeypatch.setattr(subprocess, "run", _fake_run)

        with docker_scratch_database() as scratch:
            assert scratch.database == "maskdb"

    def test_each_scratch_container_gets_a_unique_safe_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        names: list[str] = []

        def _fake_run(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            return subprocess.CompletedProcess(list(argv), 0, stdout=b"")

        monkeypatch.setattr(subprocess, "run", _fake_run)

        for _ in range(2):
            with docker_scratch_database() as scratch:
                names.append(scratch.container)

        assert len(set(names)) == 2
        for name in names:
            assert len(name) <= 64
            assert all(character.isalnum() or character == "-" for character in name)
