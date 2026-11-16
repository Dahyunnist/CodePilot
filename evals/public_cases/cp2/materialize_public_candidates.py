"""Build exact-base CP-2 public fixtures from cached Docker images only."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from evals.cp2_benchmark import _case_materialization_blockers
from evals.public_cases.prepare_swebench_lite import _safe_extract_tar


ROOT = Path(__file__).resolve().parents[3]
CP2 = ROOT / "evals/public_cases/cp2"
CASE_ROOT = CP2 / "cases"
PATCH_ROOT = CP2 / "public-test-patches"
DOCKER_PYTHON = "/opt/miniconda3/envs/testbed/bin/python"
TASK_IDS = (
    "django__django-10924", "django__django-11001", "django__django-11099", "django__django-11133",
    "pytest-dev__pytest-5103", "pytest-dev__pytest-5221", "pytest-dev__pytest-5413", "pytest-dev__pytest-5495",
    "pydata__xarray-3364", "pydata__xarray-4094", "pydata__xarray-4248", "pydata__xarray-4493",
    "mwaskom__seaborn-2848", "mwaskom__seaborn-3010", "scikit-learn__scikit-learn-10508",
)
TASK_REPOS = {
    "django__django": ("django/django", "BSD-3-Clause", "LICENSE"),
    "pytest-dev__pytest": ("pytest-dev/pytest", "MIT", "LICENSE"),
    "pydata__xarray": ("pydata/xarray", "Apache-2.0", "LICENSE"),
    "mwaskom__seaborn": ("mwaskom/seaborn", "BSD-3-Clause", "LICENSE.md"),
    "scikit-learn__scikit-learn": ("scikit-learn/scikit-learn", "BSD-3-Clause", "COPYING"),
}
XARRAY_4493_TEST = '''import dask.array as da
import xarray as xr


def test_dataset_update_keeps_chunked_data_lazy():
    values = da.random.random((3, 3), chunks=(2, 2))
    ds = xr.Dataset({"foo": xr.DataArray(values, dims=("x", "y")), "bar": ("x", [1, 2, 3])})
    update = {
        "foo": (("x", "y"), ds.foo[1:, :]),
        "bar": ("x", ds.bar[1:]),
    }

    ds.update(update)

    assert isinstance(ds.foo.data, da.Array)
'''

TASK_SPECS: dict[str, dict[str, Any]] = {
    "django__django-10924": {
        "visible_path": "tests/model_fields/test_filepathfield.py",
        "patch": "django-10924.patch",
        "django_methods": ["test_callable_path"],
    },
    "django__django-11001": {
        "visible_path": "tests/expressions/tests.py",
        "patch": "django-11001.patch",
        "django_methods": ["test_order_by_multiline_sql"],
    },
    "django__django-11099": {
        "visible_path": "tests/auth_tests/test_validators.py",
        "patch": "django-11099.patch",
        "django_methods": ["test_unicode_validator", "test_ascii_validator"],
    },
    "django__django-11133": {
        "visible_path": "tests/httpwrappers/tests.py",
        "patch": "django-11133.patch",
        "django_methods": ["test_memoryview_content"],
    },
    "pytest-dev__pytest-5221": {
        "visible_path": "testing/python/fixtures.py",
        "patch": "pytest-5221.patch",
        "pytest_filter": "test_show_fixtures",
    },
    "pytest-dev__pytest-5103": {
        "visible_path": "testing/test_assertrewrite.py",
        "patch": "pytest-5103.patch",
        "pytest_filter": "unroll",
    },
    "pytest-dev__pytest-5413": {
        "visible_path": "testing/code/test_excinfo.py",
        "patch": "pytest-5413.patch",
        "pytest_filter": "test_excinfo_repr_str",
    },
    "pytest-dev__pytest-5495": {
        "visible_path": "testing/test_assertion.py",
        "patch": "pytest-5495.patch",
        "pytest_filter": "bytes_diff",
    },
    "pydata__xarray-4094": {
        "visible_path": "xarray/tests/test_dataset.py",
        "patch": "xarray-4094.patch",
        "pytest_filter": "test_to_stacked_array_to_unstacked_dataset",
    },
    "pydata__xarray-3364": {
        "visible_path": "xarray/tests/test_concat.py",
        "patch": "xarray-3364.patch",
        "pytest_filter": "test_concat_merge_variables_present_in_some_datasets",
    },
    "pydata__xarray-4248": {
        "visible_path": "xarray/tests/test_formatting.py",
        "patch": "xarray-4248.patch",
        "pytest_filter": "test_inline_variable_array_repr_custom_repr",
    },
    "pydata__xarray-4493": {
        "visible_path": "xarray/tests/test_cp2_dataset_update_lazy.py",
        "test_source": XARRAY_4493_TEST,
        "pytest_filter": "test_dataset_update_keeps_chunked_data_lazy",
        "image_digest_override": "sha256:5c94544db403737d9f88cfb75afeb9444226072860af86e830ebbc7478287c20",
    },
    "scikit-learn__scikit-learn-10508": {
        "visible_path": "sklearn/preprocessing/tests/test_label.py",
        "patch": "sklearn-10508.patch",
        "pytest_filter": "test_label_encoder_empty_array",
    },
    "mwaskom__seaborn-2848": {
        "visible_path": "tests/test_relational.py",
        "patch": "seaborn-2848.patch",
        "pytest_filter": "test_hue_order",
    },
    "mwaskom__seaborn-3010": {
        "visible_path": "tests/_stats/test_regression.py",
        "patch": "seaborn-3010.patch",
        "pytest_filter": "test_missing_data",
    },
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_hash(path: Path) -> str:
    return _sha256(path.read_bytes())


def _docker(command: list[str], *, timeout: int = 240) -> bytes:
    result = subprocess.run(command, capture_output=True, check=False, timeout=timeout)
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace")[-1200:]
        raise RuntimeError(f"Docker command failed ({result.returncode}): {detail}")
    return result.stdout


def _source_archive(image: str, commit: str) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("base commit must be a full Git SHA")
    return _docker([
        "docker", "run", "--pull=never", "--rm", "--network", "none",
        "--entrypoint", "bash", image, "-lc",
        f"git -C /testbed archive --format=tar {commit}",
    ])


def _git_value(image: str, expression: str) -> str:
    value = _docker([
        "docker", "run", "--pull=never", "--rm", "--network", "none",
        "--entrypoint", "bash", image, "-lc",
        f"git -C /testbed rev-parse {expression}",
    ]).decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("image returned an invalid Git object ID")
    return value


def _image_id(image: str) -> str:
    value = _docker([
        "docker", "image", "inspect", image, "--format", "{{.Id}}",
    ]).decode("ascii").strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ValueError("Docker returned an invalid image config digest")
    return value


def _generated_runtime_files(image: str, repo: Path, repo_name: str) -> dict[str, str]:
    generated: dict[str, str] = {}
    if repo_name == "pytest-dev/pytest":
        version = _docker([
            "docker", "run", "--pull=never", "--rm", "--network", "none",
            "--entrypoint", "cat", image, "/testbed/src/_pytest/_version.py",
        ])
        path = repo / "src/_pytest/_version.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(version)
        generated[path.relative_to(repo).as_posix()] = _file_hash(path)
    elif repo_name == "scikit-learn/scikit-learn":
        archive = _docker([
            "docker", "run", "--pull=never", "--rm", "--network", "none",
            "--entrypoint", "bash", image, "-lc",
            "cd /testbed && find sklearn -type f -name '*.so' -print0 | tar --null -T - -cf -",
        ], timeout=300)
        _safe_extract_tar(archive, repo)
        generated = {
            path.relative_to(repo).as_posix(): _file_hash(path)
            for path in sorted(repo.rglob("*.so"))
        }
        if not generated:
            raise RuntimeError("pinned image contains no compiled scikit-learn extensions")
    return generated


def _file_inventory(repo: Path) -> dict[str, str]:
    return {
        path.relative_to(repo).as_posix(): _file_hash(path)
        for path in sorted(repo.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def _apply_public_test(task_id: str, spec: dict[str, Any], repo: Path) -> None:
    if patch_name := spec.get("patch"):
        patch_path = PATCH_ROOT / patch_name
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
        result = subprocess.run(
            ["git", "apply", "--ignore-space-change", "--whitespace=nowarn", str(patch_path.resolve())],
            cwd=repo, check=False, capture_output=True,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace")[-1200:])
        shutil.rmtree(repo / ".git")
    elif source := spec.get("test_source"):
        target = repo / spec["visible_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    else:
        raise ValueError(f"{task_id}: missing public test source")


def _django_command(repo: Path, path: str, methods: list[str]) -> list[str]:
    module = path.removeprefix("tests/").removesuffix(".py").replace("/", ".")
    tree = ast.parse((repo / path).read_text(encoding="utf-8"))
    labels: dict[str, str] = {}

    def visit(nodes: list[ast.stmt], parents: list[str]) -> None:
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                visit(node.body, parents + [node.name])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                labels[node.name] = ".".join([module, *parents, node.name])

    visit(tree.body, [])
    missing = set(methods) - labels.keys()
    if missing:
        raise ValueError(f"Django visible test methods missing: {sorted(missing)}")
    return ["python", "tests/runtests.py", *(labels[name] for name in methods)]


def _pytest_command(path: str, filter_expression: str) -> list[str]:
    return ["python", "-m", "pytest", path, "-p", "no:cacheprovider", "-k", filter_expression, "-q"]


def materialize(task_ids: set[str] | None = None) -> list[dict[str, Any]]:
    selected_ids = [task_id for task_id in TASK_IDS if task_ids is None or task_id in task_ids]
    if task_ids and set(selected_ids) != task_ids:
        raise ValueError("requested task IDs are not in the public candidate list")
    prepared: list[dict[str, Any]] = []
    for task_id in selected_ids:
        case_dir = CASE_ROOT / task_id
        case_path = case_dir / "case.json"
        inventory_path = case_dir / "source-files.json"
        repo_final = case_dir / "repo"
        if not case_path.is_file():
            raise ValueError(f"{task_id}: public case metadata missing")
        case = json.loads(case_path.read_text(encoding="utf-8"))
        spec = TASK_SPECS.get(task_id)
        if not spec:
            raise ValueError(f"{task_id}: no reviewed public test patch configuration")
        visible_paths = case.get("visible_test_files") or [case.get("visible_test_file")]
        visible_paths = [path for path in visible_paths if path]
        if len(visible_paths) != 1 or visible_paths[0] != spec["visible_path"]:
            raise ValueError(f"{task_id}: public test path differs from reviewed patch")
        visible_path = visible_paths[0]
        repo_name, spdx, default_license_file = TASK_REPOS[task_id.rsplit("-", 1)[0]]
        image = case["docker_image"]
        commit = case["source_commit"]
        actual_image_digest = _image_id(image)
        pinned_digest = spec.get("image_digest_override") or case.get("docker_image_config_digest")
        if pinned_digest and actual_image_digest != pinned_digest:
            raise ValueError(f"{task_id}: local Docker image digest differs from case metadata")
        image_digest = pinned_digest or actual_image_digest
        if repo_final.exists():
            blockers = _case_materialization_blockers(case_dir, case)
            if not blockers:
                inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
                license_path = case.get("license_file") or default_license_file
                license_digest = inventory.get("files", {}).get(license_path)
                if not license_digest:
                    raise ValueError(f"{task_id}: base license file missing: {license_path}")
                if case.get("license_file_sha256") and case["license_file_sha256"] != license_digest:
                    raise ValueError(f"{task_id}: exact-base license file hash mismatch")
                case["docker_image_config_digest"] = image_digest
                case["license"] = case.get("license") or spdx
                case["license_file"] = license_path
                case["license_file_sha256"] = license_digest
                case_path.write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                prepared.append({"task_id": task_id, "repo_fixture": "already_present_and_verified", "image_digest": image_digest})
                continue
            raise ValueError(f"{task_id}: existing repo fixture fails validation: {blockers}")

        with tempfile.TemporaryDirectory(prefix="cp2-materialize-") as temp_name:
            temp_repo = Path(temp_name) / "repo"
            archive = _source_archive(image, commit)
            _safe_extract_tar(archive, temp_repo)
            tree_sha = _git_value(image, commit + "^{tree}")
            base_files = _file_inventory(temp_repo)
            license_path = case.get("license_file") or default_license_file
            license_digest = base_files.get(license_path)
            if not license_digest:
                raise ValueError(f"{task_id}: base license file missing: {license_path}")
            if case.get("license_file_sha256") and case["license_file_sha256"] != license_digest:
                raise ValueError(f"{task_id}: exact-base license file hash mismatch")
            generated_files = _generated_runtime_files(image, temp_repo, repo_name)
            _apply_public_test(task_id, spec, temp_repo)

            test_path = temp_repo / visible_path
            if not test_path.is_file():
                raise ValueError(f"{task_id}: visible test was not materialized")
            visible_sha = _file_hash(test_path)
            visible_root = case_dir / "visible_tests"
            visible_copy = visible_root / visible_path
            visible_copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(test_path, visible_copy)

            source_inventory = {
                "case_id": task_id,
                "files": base_files,
                "generated_files": generated_files,
                "schema_version": 1,
                "source_archive_sha256": _sha256(archive),
                "source_commit": commit,
                "source_tree_sha": tree_sha,
            }
            inventory_bytes = (json.dumps(source_inventory, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            if inventory_path.is_file():
                old_raw = inventory_path.read_text(encoding="utf-8")
                old = json.loads(old_raw)
                for key in ("case_id", "files", "source_commit"):
                    if old.get(key) != source_inventory[key]:
                        raise ValueError(f"{task_id}: existing source inventory differs at {key}")
                if old.get("source_tree_sha") != tree_sha:
                    old_tree = old.get("source_tree_sha")
                    if not isinstance(old_tree, str) or old_raw.count(old_tree) != 1:
                        raise ValueError(f"{task_id}: cannot safely update stale source tree metadata")
                    inventory_path.write_text(old_raw.replace(old_tree, tree_sha), encoding="utf-8", newline="\n")
            else:
                inventory_path.write_bytes(inventory_bytes)

            if "django_methods" in spec:
                command = _django_command(temp_repo, visible_path, spec["django_methods"])
            else:
                command = _pytest_command(visible_path, spec["pytest_filter"])
            case["test_command"] = command
            case["visible_test_sha256"] = visible_sha
            case["source_tree_sha"] = tree_sha
            case["docker_image_config_digest"] = image_digest
            case["license"] = case.get("license") or spdx
            case["license_file"] = license_path
            case["license_file_sha256"] = license_digest
            case["source_file_manifest_sha256"] = _sha256(inventory_path.read_bytes())
            if "src/_pytest/_version.py" in generated_files:
                case["generated_version_sha256"] = generated_files["src/_pytest/_version.py"]
            runtime_only = {path: digest for path, digest in generated_files.items() if path != "src/_pytest/_version.py"}
            if runtime_only:
                case["generated_runtime_files"] = runtime_only
            case_path.write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            shutil.copytree(temp_repo, repo_final)
            prepared.append({
                "task_id": task_id,
                "base_commit": commit,
                "image_digest": image_digest,
                "source_archive_sha256": _sha256(archive),
                "source_tree_sha": tree_sha,
                "visible_test_sha256": visible_sha,
                "repo_fixture": "materialized",
            })
    return prepared


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-ids", nargs="*")
    arguments = parser.parse_args()
    task_ids = set(arguments.task_ids) if arguments.task_ids else None
    print(json.dumps(materialize(task_ids), ensure_ascii=False, indent=2))
