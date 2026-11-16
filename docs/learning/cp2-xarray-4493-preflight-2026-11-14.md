# CP-2 xarray-4493 runtime 预检（2026-11-14）

## 当前状态

`benchmark-v1.json` 冻结 15 题。15 题的 visible test 都只有规格说明，未物化，也未做 baseline；不能称作可见测试通过。14 题已有本地 image config digest 记录。唯一缺失项是 `pydata__xarray-4493`，manifest 状态为 `image_missing`，digest 为 null。

本会话 Docker daemon pipe 不存在，无法独立查询宿主镜像。没有拉取镜像，也没有运行容器或模型。全套 CP-2 继续 fail-closed。

## 宿主只读复核

在 Docker Desktop 已启动的 PowerShell 执行：

```powershell
docker image inspect --format '{{.Id}} {{.Os}}/{{.Architecture}}' swebench/sweb.eval.x86_64.pydata_1776_xarray-4493:latest
```

把完整输出回传。预期平台为 `linux/amd64`；需取得实际 `sha256:...` image ID 后才能更新 runtime pin。若命令显示未找到镜像，保持当前 null 状态，不要批量 pull。

## 可复现契约

运行 `python -m pytest -p no:cacheprovider tests/test_cp2_benchmark.py tests/test_benchmark_manifest_integrity.py -q`。契约断言：15 题仍未把规格草案标成已验证；xarray-4493 是唯一缺少 digest 的题。测试不接触隐藏测试、Docker 或 API。
