from __future__ import annotations

from types import SimpleNamespace

import pytest

import scripts.deploy_latex_compiler_space as compiler_deploy
from scripts.deploy_latex_compiler_space import (
    _assemble,
    _authenticated_hub_token,
    _validate_space_id,
    _verify_staging_identity,
    compiler_image_reference,
    provision_compiler_image,
)


def test_private_space_assembly_includes_the_shared_contract(tmp_path) -> None:
    _assemble(tmp_path)

    assert (tmp_path / "Dockerfile").is_file()
    assert (tmp_path / "latex_compiler_space" / "app.py").is_file()
    assert (tmp_path / "latex_compiler_space" / "workspace_runner.py").is_file()
    assert (tmp_path / "latex_compiler_contract" / "__init__.py").is_file()


def test_private_builder_uses_the_protected_staging_token_without_printing_it(
    monkeypatch,
) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setenv("PWC_HF_TOKEN", "staging-token")
    monkeypatch.setattr(
        compiler_deploy,
        "get_token",
        lambda: pytest.fail("must prefer the protected staging environment"),
    )

    assert _authenticated_hub_token() == "staging-token"


def test_private_builder_refuses_a_non_staging_authenticated_identity() -> None:
    class Api:
        def whoami(self) -> dict[str, str]:
            return {"name": "another-account"}

    with pytest.raises(RuntimeError, match="approved staging account"):
        _verify_staging_identity(Api())


@pytest.mark.parametrize(
    "space_id",
    [
        "namespace/compiler",
        "namespace/compiler-production",
        "namespace//compiler-staging",
        "other/pwc-latex-compiler-sandbox-staging",
    ],
)
def test_private_space_deploy_refuses_non_staging_ids(space_id: str) -> None:
    with pytest.raises(ValueError):
        _validate_space_id(space_id)


def test_compiler_image_reference_requires_a_hugging_face_registry_digest() -> None:
    space_id = "nielsr/pwc-latex-compiler-sandbox-staging"
    digest = "sha256:" + "a" * 64

    assert compiler_image_reference(space_id, digest) == (
        "registry.hf.space/nielsr-pwc-latex-compiler-sandbox-staging@" + digest
    )

    with pytest.raises(ValueError, match="immutable"):
        compiler_image_reference(space_id, "latest")


def test_private_compiler_provision_uploads_waits_pins_and_pauses() -> None:
    calls: list[tuple[str, object]] = []

    class Api:
        def create_repo(self, **kwargs: object) -> None:
            calls.append(("create", kwargs))

        def update_repo_settings(self, **kwargs: object) -> None:
            calls.append(("private", kwargs))

        def space_info(self, **kwargs: object) -> SimpleNamespace:
            calls.append(("info", kwargs))
            return SimpleNamespace(private=True, sha="builder-source-commit")

        def upload_folder(self, **kwargs: object) -> SimpleNamespace:
            calls.append(("upload", kwargs))
            return SimpleNamespace(oid="builder-source-commit")

        def pause_space(self, **kwargs: object) -> None:
            calls.append(("pause", kwargs))

    def wait(api: Api, space_id: str) -> None:
        assert space_id == "nielsr/pwc-latex-compiler-sandbox-staging"
        calls.append(("wait", space_id))

    def registry_digest(space_id: str) -> str:
        assert space_id == "nielsr/pwc-latex-compiler-sandbox-staging"
        calls.append(("digest", space_id))
        return "sha256:" + "a" * 64

    identity = provision_compiler_image(
        "nielsr/pwc-latex-compiler-sandbox-staging",
        api=Api(),
        wait_for_runtime=wait,
        resolve_registry_digest=registry_digest,
    )

    assert identity.space_id == "nielsr/pwc-latex-compiler-sandbox-staging"
    assert identity.source_revision == "builder-source-commit"
    assert identity.image == (
        "registry.hf.space/nielsr-pwc-latex-compiler-sandbox-staging@sha256:" + "a" * 64
    )
    assert calls[0][0] == "create"
    assert calls[0][1]["private"] is True
    assert calls[0][1]["space_sdk"] == "docker"
    assert calls[1][0] == "private"
    assert [name for name, _ in calls][-3:] == ["wait", "digest", "pause"]


def test_private_compiler_provision_pauses_the_builder_when_upload_fails() -> None:
    calls: list[str] = []

    class Api:
        def create_repo(self, **kwargs: object) -> None:
            calls.append("create")

        def update_repo_settings(self, **kwargs: object) -> None:
            calls.append("private")

        def space_info(self, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(private=True)

        def upload_folder(self, **kwargs: object) -> None:
            calls.append("upload")
            raise RuntimeError("synthetic upload failure")

        def pause_space(self, **kwargs: object) -> None:
            calls.append("pause")

    with pytest.raises(RuntimeError, match="synthetic upload failure"):
        provision_compiler_image(
            "nielsr/pwc-latex-compiler-sandbox-staging",
            api=Api(),
        )

    assert calls == ["create", "private", "upload", "pause"]


def test_private_compiler_provision_pauses_the_builder_when_privacy_setup_fails() -> (
    None
):
    """A partially configured builder cannot remain reachable after a setup error."""

    calls: list[str] = []

    class Api:
        def create_repo(self, **kwargs: object) -> None:
            calls.append("create")

        def update_repo_settings(self, **kwargs: object) -> None:
            calls.append("private")
            raise RuntimeError("synthetic privacy setup failure")

        def pause_space(self, **kwargs: object) -> None:
            calls.append("pause")

    with pytest.raises(RuntimeError, match="synthetic privacy setup failure"):
        provision_compiler_image(
            "nielsr/pwc-latex-compiler-sandbox-staging",
            api=Api(),
        )

    assert calls == ["create", "private", "pause"]


def test_private_compiler_provision_pauses_when_private_visibility_is_unverified() -> (
    None
):
    calls: list[str] = []

    class Api:
        def create_repo(self, **kwargs: object) -> None:
            calls.append("create")

        def update_repo_settings(self, **kwargs: object) -> None:
            calls.append("private")

        def space_info(self, **kwargs: object) -> SimpleNamespace:
            calls.append("info")
            return SimpleNamespace(private=False)

        def pause_space(self, **kwargs: object) -> None:
            calls.append("pause")

    with pytest.raises(RuntimeError, match="visibility"):
        provision_compiler_image(
            "nielsr/pwc-latex-compiler-sandbox-staging",
            api=Api(),
        )

    assert calls == ["create", "private", "info", "pause"]
