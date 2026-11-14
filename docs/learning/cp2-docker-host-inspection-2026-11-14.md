# CP-2 Docker 宿主预检（2026-11-14）

> 勘误：本记录最初把合成 `HEAD` SHA 当作 base SHA，故“15/15 不一致”的结论错误。正确核验见[父提交审计与更正](cp2-docker-parent-audit-2026-11-14.md)。

## 结果

Docker Desktop 可用：Client 29.1.3，Server 29.1.3，linux/amd64。15 个冻结镜像 tag 均可读取；14 个已有 config digest 与冻结值一致。xarray-4493 的冻结 digest 原先为空，本次读到 `sha256:5c94544db403737d9f88cfb75afeb9444226072860af86e830ebbc7478287c20`。

所有镜像容器均可运行，但 `/testbed` 的 `git rev-parse HEAD` 与清单预期 base commit **15/15 不一致**。许可证 SHA-256 均与清单值一致；seaborn-3010 容器中路径为 `LICENSE.md`，清单记录为 `LICENSE`。路径差异与 base 不匹配都需查明，不能据此标记 exact-base 已验证。

| task | 预期 base | 容器 HEAD |
| --- | --- | --- |
| `django__django-10924` | `bceadd2788dc2dad53eba0caae172bd8522fd483` | `a84760f61639d2d3954344001aa58401083f0177` |
| `django__django-11001` | `ef082ebb84f00e38af4e8880d04e8365c2766d34` | `31c695dce67e3c7ddd60ac898bd4e62ff0c23daa` |
| `django__django-11099` | `d26b2424437dabeeca94d7900b37d2df4410da0c` | `04df050ee958b843111c32aaaa362eda26b25bda` |
| `django__django-11133` | `879cc3da6249e920b8d54518a0ae06de835d7373` | `95d0ab8311f8180cdd9c02006be1dc16cc706548` |
| `pytest-dev__pytest-5103` | `10ca84ffc56c2dd2d9dc4bd71b7b898e083500cd` | `5df4d131d551b79b9fcf258482eaa4f59bf238b8` |
| `pytest-dev__pytest-5221` | `4a2fdce62b73944030cff9b3e52862868ca9584d` | `c0698ad6368fb4dfda4e3d2b8dab498874793848` |
| `pytest-dev__pytest-5413` | `450d2646233c670654744d3d24330b69895bb9d2` | `c08daa5908fdcedc912b07801adc12c428f352d7` |
| `pytest-dev__pytest-5495` | `1aefb24b37c30fba8fd79a744829ca16e252f340` | `f2f74c379db180f695e2cc06ed8e86f906e2dcef` |
| `pydata__xarray-3364` | `863e49066ca4d61c9adfe62aca3bf21b90e1af8c` | `3c2a10d9bbf2bf86b74762c5e62b2f7ef33127b6` |
| `pydata__xarray-4094` | `a64cf2d5476e7bbda099b34c40b7be1880dbd39a` | `58761b01d75edf12556fbc9d0056af31e38c86b2` |
| `pydata__xarray-4248` | `98dc1f4ea18738492e074e9e51ddfed5cd30ab94` | `56c06a44f43b5aa56b426e82b6159f7217e97e8a` |
| `pydata__xarray-4493` | `a5f53e203c52a7605d5db799864046471115d04f` | `e8815311e4681461882133e650391caf0d1ae868` |
| `mwaskom__seaborn-2848` | `94621cef29f80282436d73e8d2c0aa76dab81273` | `a110ef5b2bca99904daf60a6e10e7e5bda8d98d6` |
| `mwaskom__seaborn-3010` | `0f5a013e2cf43562deec3b879458e59a73853813` | `191ec3379337aea8e27e61f8fd3dd11411a8654f` |
| `scikit-learn__scikit-learn-10508` | `c753b77ac49e72ebc0fe5e3c2369fe628f975017` | `fd90cef8a6ab1b1eb5b96e092ba7984e8461e124` |

## 原始证据

逐题镜像 inspect、容器 stdout、预期摘要与预期 base 均保存在 [cp2-docker-host-inspection-2026-11-14.json](cp2-docker-host-inspection-2026-11-14.json)，SHA-256：`7368cd63f486067d01fc3556eafb536ad5e82641d4fb98d3fb22402d92a47ceb`。

## 决策

- 不改写冻结 manifest，不把错误 base 标成 verified。
- 不物化或运行 visible tests；当前镜像不能证明它们运行在指定 base 上。
- 下一步需查清 task/base 映射与镜像内 Git HEAD 的差异，并取得每题精确 base 的可运行源码。CP-2 的 visible tests、baseline、预算账本仍未就绪。
- 本轮没有拉取镜像、调用模型、读取隐藏测试或改动未跟踪的 `django_10924/`。
