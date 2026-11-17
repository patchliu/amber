# Amber

**让高性能算子的搜索成果可以被理解、验证和再次使用。**

算子名称和 tensor 形状通常不足以判断能否复用。中间舍入、量化位置、归约顺序、输入域和目标设备都会影响结果或性能。Amber 用可检查的 **Spec** 表达需求，**AmberHouse** 保存实现、适用条件和证据，让下一次请求可以从已有成果开始。

## 当前可用能力

本地 MVP 支持一个明确的 JSON Spec 子集：计算图与标量属性匹配、维度覆盖检查、规范化摘要和逐项匹配解释。AmberHouse 可上传 UTF-8 源码、按摘要保存和下载，并持久化查询缓存；Python 客户端校验下载内容并维护本地缓存。

匹配结果称为**候选**。源码声明不等于正确性证明；目前不执行算子、不验证数值行为，也不进行设备性能排名。完整规划见[架构设计文档](docs/design/AMBER_DESIGN.zh-CN.md)。

## 运行本地闭环

需要 Python 3.12 或更新版本。运行时不需要第三方依赖。

```bash
python -m amber_house --root .amber-local --port 8000
```

另开终端运行[端到端示例](examples/local_flow.py)，完成 Spec 编译、上传、检索、下载和缓存复用。

```bash
python -m examples.local_flow
python -m unittest discover -s tests -v
```

同一个目录可供重启后的服务进程继续使用；新上传会更新目录版本并使旧查询缓存失效。使用新目录可以启动独立实例。

后续计划扩展公共与团队私有仓库、独立验证证据、目标平台构建和真实负载测量。首批设备方向是 NVIDIA CUDA 与华为 Ascend，之后扩展 AMD ROCm。开发约定见 [AGENTS.md](AGENTS.md)。
