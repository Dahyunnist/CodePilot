# CP-2 seaborn-3010 baseline 预检（2026-11-14）

## 结论

单题已取得可复核的**基线缺陷复现证据**，不再只有镜像 pending。修复后验证、CodePilot Agent 运行和模型评测均未执行；这不是修复成功或 Agent 成功。

## 输入核对

| 项目 | 实测/冻结值 | 结果 |
|---|---|---|
| 任务映射 | `mwaskom__seaborn-3010`；PolyFit 对缺失 x/y 数据应等同先 `dropna` 再拟合 | 与 [上游 PR #3010](https://github.com/mwaskom/seaborn/pull/3010) 一致；PR 标题为 “Fix: Make PolyFit stat robust to missing data”，关联 issue #2992 |
| 镜像 | `swebench/sweb.eval.x86_64.mwaskom_1776_seaborn-3010:latest` | Client/Server Docker 29.1.3；image ID 与 RepoDigest 均为 `sha256:22fef36e8b9655fb1642d976de669e3f2426df0186a09d6d788fc6215cfa1bc0`，与冻结值相同 |
| base | 镜像 `HEAD=191ec3379337aea8e27e61f8fd3dd11411a8654f`；`HEAD^=0f5a013e2cf43562deec3b879458e59a73853813` | 父提交与 `case.json` 冻结的 `source_commit` 一致。SWE-bench 镜像 HEAD 是合成提交，按父提交校验 base |
| 许可证 | `BSD-3-Clause`，`LICENSE.md` | 容器 SHA-256 为 `0874bfc01308833385b2f5ca62205525739f6a57b8688afea1b078d0f845d6d4`，与 `source-files.json` 一致 |
| 可见测试 | `tests/_stats/test_regression.py`；冻结命令：`python -m pytest tests/_stats/test_regression.py -p no:cacheprovider -k test_missing_data -q` | case 元数据记载预期 visible hash `c68053590168ce35c79d499e2b33e0e7ca3aff7319b0feb09770065c9bb66ad9`；base 镜像实际文件 SHA 为 `12e12e96be7da9f96e0576e2baeeed5cebe8174a3f544c82b614e640424d6ae2`，且没有 `test_missing_data`。预期测试未物化到 base |

## 容器运行

容器均使用固定 image ID、`--network none`、`--read-only`、临时 `/tmp` tmpfs、`--rm`，没有宿主目录挂载。未运行 Agent、未请求模型，也未写入宿主源仓库。

检查镜像元信息和文件哈希的容器命令：

```powershell
docker run --rm --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=1g --env HOME=/tmp --env MPLCONFIGDIR=/tmp/mpl --env PYTHONDONTWRITEBYTECODE=1 --entrypoint /bin/bash sha256:22fef36e8b9655fb1642d976de669e3f2426df0186a09d6d788fc6215cfa1bc0 -lc 'set -e; cd /testbed; echo IMAGE_HEAD=$(git rev-parse HEAD); echo IMAGE_PARENT=$(git rev-parse HEAD^); echo LICENSE_PATH=LICENSE.md; sha256sum LICENSE.md; echo VISIBLE_FILE=tests/_stats/test_regression.py; sha256sum tests/_stats/test_regression.py; echo TEST_NAMES; grep -n test_missing_data tests/_stats/test_regression.py; echo PYTHON=/opt/miniconda3/envs/testbed/bin/python; /opt/miniconda3/envs/testbed/bin/python --version'
```

上述检查因 `grep` 在 base 文件中找不到新增用例而提前退出，故 Python 版本行未执行；前面的 base 与许可证核对均已输出。冻结测试命令随后单独执行：

```powershell
docker run --rm --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=1g --env HOME=/tmp --env MPLCONFIGDIR=/tmp/mpl --env PYTHONDONTWRITEBYTECODE=1 --entrypoint /bin/bash sha256:22fef36e8b9655fb1642d976de669e3f2426df0186a09d6d788fc6215cfa1bc0 -lc 'cd /testbed; /opt/miniconda3/envs/testbed/bin/python -m pytest tests/_stats/test_regression.py -p no:cacheprovider -k test_missing_data -q; test_rc=$?; echo PYTEST_EXIT=$test_rc; exit 0'
```

结果：`2 deselected in 0.44s`，pytest 退出码 **5**（没有测试被选择）。这说明 base 镜像不含新增可见测试，不能把该命令结果当成 baseline bug 失败。

## 公开可见测试的基线复现

GitHub PR #3010 的公开 diff 新增 `TestPolyFit.test_missing_data`：将 `df.iloc[5:10]` 置为缺失值，比较 `PolyFit()(df[['x', 'y']], ...)` 与 `PolyFit()(df[['x', 'y']].dropna(), ...)` 的结果。为不修改只读 `/testbed`，本次仅把该测试逻辑放进容器 `/tmp` tmpfs，并用固定随机种子生成等价 fixture。此处没有使用 PR fix 或任何隐藏测试。

复现结果：**1 failed**；首个失败为 `numpy.linalg.LinAlgError: SVD did not converge in Linear Least Squares`，pytest 退出码 **1**。这与该题预期的 base failure 相符，完成单题 baseline reproduction。

临时 harness 用固定 seed fixture，并保留 PR 新增测试的断言逻辑：

```python
import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from seaborn._core.groupby import GroupBy
from seaborn._stats.regression import PolyFit

@pytest.fixture
def rng():
    return np.random.default_rng(0)

@pytest.fixture
def df(rng):
    n = 100
    return pd.DataFrame(dict(
        x=rng.normal(0, 1, n),
        y=rng.normal(0, 1, n),
        color=rng.choice(["a", "b", "c"], n),
        group=rng.choice(["x", "y"], n),
    ))

class TestPolyFit:
    def test_missing_data(self, df):
        groupby = GroupBy(["group"])
        df.iloc[5:10] = np.nan
        res1 = PolyFit()(df[["x", "y"]], groupby, "x", {})
        res2 = PolyFit()(df[["x", "y"]].dropna(), groupby, "x", {})
        assert_frame_equal(res1, res2)
```

容器内 pytest 命令：

```bash
/opt/miniconda3/envs/testbed/bin/python -m pytest /tmp/test_visible_seaborn_3010.py -p no:cacheprovider -k test_missing_data -q
```

## 官方 PR 补丁复测（2026-11-14）

从 GitHub 下载原始 [PR #3010 patch](https://github.com/mwaskom/seaborn/pull/3010.patch)，包含提交 `0144d18d09001396443bdcd860c6d08edb3d2c37`（修复与新增测试）和 `f191292f5554eb7908a07b849094c1d78adcf8bb`（release note）。原始 patch 文件 SHA-256：`5d77572ab3082e5cde74d4564a1bb2f507fdfea29b22744fd771d561bce28ddf`。

将 patch 只读挂入以固定 image digest 创建的一次性容器，在容器 `/testbed` 执行 `git apply --check`、`git apply`。Docker 命令使用 `--rm --network none`，不挂载宿主源仓库；容器退出后工作树销毁。Git 提示两个文件镜像模式为 `100755`、PR 补丁预期 `100644`；这是基线镜像合成提交的执行位差异，文本补丁已应用，随后测试均通过。

容器内可见测试结果：

```text
tests/_stats/test_regression.py -p no:cacheprovider -k test_missing_data -q
1 passed, 2 deselected in 0.49s
VISIBLE_EXIT=0

tests/_stats/test_regression.py -p no:cacheprovider -q
3 passed in 0.36s
REGRESSION_EXIT=0
```

应用 patch 后测试文件 SHA-256 为 `f9cb28c201c96931f63e917e0ee7652a77af8d14964e602c7a2a7d41015ec0ca`。冻结 case 的 `visible_test_sha256` 为 `c68053590168ce35c79d499e2b33e0e7ca3aff7319b0feb09770065c9bb66ad9`；字段与完整测试文件哈希的对应规则未确认，因此保留两项实测记录，不改冻结 manifest 的 hash/status 字段。

## 状态边界

- 该任务已有镜像、base、许可证、baseline 缺陷复现和官方 PR fix 的可见测试证据；本单题 `baseline -> 官方修复` 可复现。
- `benchmark-v1.json` 是冻结输入，本轮不改它；后续新版 manifest 应引用本记录并固定可见测试物化规则。
- 未运行 CodePilot Agent 或模型，未运行隐藏测试；不能将任务记为 Agent accepted 或 CP-2 完成。
