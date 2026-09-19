from datetime import datetime
from pathlib import Path

import pytest

from ai_workflow.config import RepositoryConfig
from ai_workflow.errors import AppError
from ai_workflow.path_authorization import RepositoryPathAuthorizer
from ai_workflow.workflow.checkpoint import (
    CheckpointRecord,
    CheckpointService,
    ImplementationBaseline,
    PathSnapshot,
)


def _scope(repo: Path):
    return RepositoryPathAuthorizer(
        repo, RepositoryConfig.load(repo)
    ).checkpoint_scope()


def test_checkpoint_uses_temporary_index_and_preserves_user_git_state(git_repo) -> None:
    service = CheckpointService(
        git_repo.root, clock=lambda: datetime(2026, 7, 19, 10, 0, 0)
    )
    before = git_repo.snapshot_git_state()
    baseline = service.capture_baseline(
        attempt_id="implement-1-abcdef",
        source_revision=git_repo.head,
        active_checkpoint=None,
    )
    git_repo.write("src/app.py", "changed\n")
    record = service.create(
        run_id="RUN-20260719-100000-abcdef",
        baseline=baseline,
        source_revision=git_repo.head,
        scope=_scope(git_repo.root),
        previous_checkpoint=None,
        no_code_delivery=False,
    )

    assert git_repo.snapshot_git_state() == before
    assert record.parent_commit == git_repo.head
    assert record.previous_checkpoint_sha is None
    assert record.included_paths == ("src/app.py",)
    assert record.hidden_ref == (
        "refs/ai-workflow/checkpoints/"
        "RUN-20260719-100000-abcdef/implement-1-abcdef"
    )
    assert git_repo.rev_parse(record.hidden_ref) == record.commit_sha
    service.validate_record(record)


def test_checkpoint_excludes_unchanged_preexisting_dirty_paths(git_repo) -> None:
    service = CheckpointService(git_repo.root)
    git_repo.write("notes.txt", "preexisting\n")
    baseline = service.capture_baseline(
        attempt_id="implement-1-abcdef",
        source_revision=git_repo.head,
        active_checkpoint=None,
    )

    git_repo.write("src/app.py", "changed\n")
    record = service.create(
        run_id="RUN-20260719-100000-abcdef",
        baseline=baseline,
        source_revision=git_repo.head,
        scope=_scope(git_repo.root),
        previous_checkpoint=None,
        no_code_delivery=False,
    )

    assert record.included_paths == ("src/app.py",)


def test_checkpoint_includes_explicitly_claimed_baseline_dirty_path(git_repo) -> None:
    service = CheckpointService(git_repo.root)
    git_repo.write("src/app.py", "preexisting implementation\n")
    git_repo.write("notes.txt", "unrelated preexisting work\n")
    baseline = service.capture_baseline(
        attempt_id="implement-1-abcdef",
        source_revision=git_repo.head,
        active_checkpoint=None,
    )
    claim = service.capture_claim(
        baseline=baseline,
        paths=("src/app.py",),
        scope=_scope(git_repo.root),
        source_failure_code="checkpoint_creation_failed",
    )

    record = service.create(
        run_id="RUN-20260719-100000-abcdef",
        baseline=baseline,
        source_revision=git_repo.head,
        scope=_scope(git_repo.root),
        previous_checkpoint=None,
        no_code_delivery=False,
        claim=claim,
    )

    assert record.included_paths == ("src/app.py",)


def test_checkpoint_paths_are_relative_to_configured_git_subdirectory(git_repo) -> None:
    server = git_repo.root / "server"
    (server / "src").mkdir(parents=True)
    (server / ".ai-workflow.yaml").write_text(
        "repository: nested-checkpoint\n"
        "protected_paths: [.git/**, .ai-workflow/**]\n",
        encoding="utf-8",
    )
    (server / "src" / "app.py").write_text("original\n", encoding="utf-8")
    git_repo.git("add", "server")
    git_repo.git("commit", "-m", "add nested repository")
    service = CheckpointService(server)
    (server / "src" / "app.py").write_text(
        "preexisting implementation\n", encoding="utf-8"
    )
    baseline = service.capture_baseline(
        attempt_id="implement-1-abcdef",
        source_revision=git_repo.head,
        active_checkpoint=None,
    )
    legacy_baseline = ImplementationBaseline(
        attempt_id=baseline.attempt_id,
        base_revision=baseline.base_revision,
        head_revision=baseline.head_revision,
        head_ref=baseline.head_ref,
        dirty_paths=("server/src/app.py",),
        dirty_snapshots=(
            PathSnapshot("server/src/app.py", "missing", None),
        ),
        captured_at=baseline.captured_at,
    )
    scope = RepositoryPathAuthorizer(
        server, RepositoryConfig.load(server)
    ).checkpoint_scope()
    claim = service.capture_claim(
        baseline=legacy_baseline,
        paths=("src/app.py",),
        scope=scope,
        source_failure_code="checkpoint_creation_failed",
    )

    record = service.create(
        run_id="RUN-20260719-100000-abcdef",
        baseline=legacy_baseline,
        source_revision=git_repo.head,
        scope=scope,
        previous_checkpoint=None,
        no_code_delivery=False,
        claim=claim,
    )

    assert baseline.dirty_paths == ("src/app.py",)
    assert record.included_paths == ("src/app.py",)
    assert git_repo.git("show", f"{record.commit_sha}:server/src/app.py") == (
        "preexisting implementation"
    )


def test_checkpoint_rejects_claimed_path_changed_after_authorization(git_repo) -> None:
    service = CheckpointService(git_repo.root)
    git_repo.write("src/app.py", "preexisting implementation\n")
    baseline = service.capture_baseline(
        attempt_id="implement-1-abcdef",
        source_revision=git_repo.head,
        active_checkpoint=None,
    )
    claim = service.capture_claim(
        baseline=baseline,
        paths=("src/app.py",),
        scope=_scope(git_repo.root),
        source_failure_code="checkpoint_scope_ambiguous",
    )
    git_repo.write("src/app.py", "changed after authorization\n")

    with pytest.raises(AppError) as error:
        service.create(
            run_id="RUN-20260719-100000-abcdef",
            baseline=baseline,
            source_revision=git_repo.head,
            scope=_scope(git_repo.root),
            previous_checkpoint=None,
            no_code_delivery=False,
            claim=claim,
        )

    assert error.value.code == "checkpoint_scope_ambiguous"


def test_checkpoint_rejects_dirty_overlap(git_repo) -> None:
    service = CheckpointService(git_repo.root)
    git_repo.write("src/app.py", "preexisting dirty\n")
    baseline = service.capture_baseline(
        attempt_id="implement-1-abcdef",
        source_revision=git_repo.head,
        active_checkpoint=None,
    )
    git_repo.write("src/app.py", "changed again\n")

    with pytest.raises(AppError) as error:
        service.create(
            run_id="RUN-20260719-100000-abcdef",
            baseline=baseline,
            source_revision=git_repo.head,
            scope=_scope(git_repo.root),
            previous_checkpoint=None,
            no_code_delivery=False,
        )

    assert error.value.code == "checkpoint_scope_ambiguous"


def test_checkpoint_rejects_unauthorized_paths(git_repo) -> None:
    service = CheckpointService(git_repo.root)
    baseline = service.capture_baseline(
        attempt_id="implement-1-abcdef",
        source_revision=git_repo.head,
        active_checkpoint=None,
    )
    git_repo.write(".ai-workflow/secret.txt", "no\n")

    with pytest.raises(AppError) as error:
        service.create(
            run_id="RUN-20260719-100000-abcdef",
            baseline=baseline,
            source_revision=git_repo.head,
            scope=_scope(git_repo.root),
            previous_checkpoint=None,
            no_code_delivery=False,
        )

    assert error.value.code == "path_not_authorized"


def test_second_checkpoint_parent_is_previous_active(git_repo) -> None:
    service = CheckpointService(git_repo.root)
    baseline = service.capture_baseline(
        attempt_id="implement-1-abcdef",
        source_revision=git_repo.head,
        active_checkpoint=None,
    )
    git_repo.write("src/app.py", "first\n")
    first = service.create(
        run_id="RUN-20260719-100000-abcdef",
        baseline=baseline,
        source_revision=git_repo.head,
        scope=_scope(git_repo.root),
        previous_checkpoint=None,
        no_code_delivery=False,
    )
    second_baseline = service.capture_baseline(
        attempt_id="implement-2-abcdef",
        source_revision=git_repo.head,
        active_checkpoint=first,
    )
    git_repo.write("src/app.py", "second\n")

    second = service.create(
        run_id="RUN-20260719-100000-abcdef",
        baseline=second_baseline,
        source_revision=git_repo.head,
        scope=_scope(git_repo.root),
        previous_checkpoint=first,
        no_code_delivery=False,
    )

    assert second.parent_commit == first.commit_sha
    assert second.previous_checkpoint_sha == first.commit_sha
    assert git_repo.rev_parse(second.hidden_ref) == second.commit_sha


def test_no_code_delivery_uses_base_without_hidden_ref(git_repo) -> None:
    service = CheckpointService(git_repo.root)
    baseline = service.capture_baseline(
        attempt_id="implement-1-abcdef",
        source_revision=git_repo.head,
        active_checkpoint=None,
    )

    record = service.create(
        run_id="RUN-20260719-100000-abcdef",
        baseline=baseline,
        source_revision=git_repo.head,
        scope=_scope(git_repo.root),
        previous_checkpoint=None,
        no_code_delivery=True,
    )

    assert record.commit_sha == git_repo.head
    assert record.parent_commit == git_repo.head
    assert record.hidden_ref is None
    assert record.included_paths == ()
    service.validate_record(record)


def test_existing_checkpoint_ref_is_immutable(git_repo) -> None:
    service = CheckpointService(git_repo.root)
    baseline = service.capture_baseline(
        attempt_id="implement-1-abcdef",
        source_revision=git_repo.head,
        active_checkpoint=None,
    )
    git_repo.write("src/app.py", "first\n")
    first = service.create(
        run_id="RUN-20260719-100000-abcdef",
        baseline=baseline,
        source_revision=git_repo.head,
        scope=_scope(git_repo.root),
        previous_checkpoint=None,
        no_code_delivery=False,
    )
    git_repo.write("src/app.py", "second\n")

    with pytest.raises(AppError) as error:
        service.create(
            run_id="RUN-20260719-100000-abcdef",
            baseline=baseline,
            source_revision=git_repo.head,
            scope=_scope(git_repo.root),
            previous_checkpoint=None,
            no_code_delivery=False,
        )

    assert error.value.code == "checkpoint_creation_failed"
    assert git_repo.rev_parse(first.hidden_ref) == first.commit_sha


def test_checkpoint_record_rejects_invalid_shape() -> None:
    payload = {
        "commit_sha": "a" * 40,
        "tree_sha": "b" * 40,
        "hidden_ref": None,
        "source_revision": "c" * 40,
        "parent_commit": "c" * 40,
        "implementation_attempt_id": "implement-1-abcdef",
        "included_paths": [],
        "previous_checkpoint_sha": None,
        "created_at": "2026-07-19T10:00:00",
        "unexpected": True,
    }

    with pytest.raises(AppError) as error:
        CheckpointRecord.from_dict(payload)

    assert error.value.code == "invalid_state"
