# Amber

**Make high-performance operator search results understandable, verifiable, and reusable.**

An operator name and tensor shape rarely tell the whole story. Intermediate rounding, quantization placement, reduction order, input domains, and the target device can all change correctness or performance. Amber uses a checkable **Spec** to describe those requirements. **AmberHouse** stores implementations, applicability constraints, and evidence so the next request can start from existing work.

```text
Request → Spec → Search and match report → Implementation → Download or continue optimizing
```

## What works today

The local MVP accepts a deliberately small JSON Spec language. It canonicalizes a spec, matches a computation graph and its scalar attributes, checks whether an implementation covers the requested dimension ranges, and explains rejected or unknown properties. AmberHouse accepts UTF-8 source uploads, stores them by digest, persists a query cache, and serves downloads. A small Python client verifies downloaded content and caches it locally.

A matching source is reported as a **candidate**. Source declarations are not correctness proofs; this MVP does not execute kernels, verify numerical behavior, or rank device performance. The full system design is in the [architecture proposal](docs/design/AMBER_DESIGN.zh-CN.md).

## Try the local flow

Requires Python 3.12 or newer. No third-party runtime packages are needed.

```bash
python -m amber_house --root .amber-local --port 8000
```

In another terminal, run the [end-to-end example](examples/local_flow.py). It starts from a Spec, uploads a source file, searches, downloads, and shows local cache reuse.

```bash
python -m examples.local_flow
python -m unittest discover -s tests -v
```

The same registry directory can be used by a newly started service process; query cache entries remain available until a new upload changes the catalog revision. Use a fresh directory for an isolated instance.

## Direction

Amber is intended to grow toward public and self-hosted private registries, independent evidence checks, target-specific builds, and real workload measurements. NVIDIA CUDA and Huawei Ascend are the first planned device backends, with AMD ROCm later. The current implementation is a local search-and-reuse foundation.

See [中文说明](README.zh-CN.md) and [development guidelines](AGENTS.md). Issues and pull requests that include a concrete operator contract, numeric edge case, or real workload are especially useful.
