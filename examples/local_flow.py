"""Upload, search, download and reuse a source file against a local AmberHouse."""

from pathlib import Path

from amber_house.client import AmberClient

ROOT = Path(__file__).resolve().parent
TARGET = {"backend": "cpu", "architecture": "generic"}
QUERY = {
    "language_version": "0.1-mvp",
    "signature": {
        "inputs": {"A": {"dtype": "fp32", "shape": ["N"]}, "B": {"dtype": "fp32", "shape": ["N"]}},
        "outputs": {"Y": {"dtype": "fp32", "shape": ["N"]}},
    },
    "domain": {"dimensions": {"N": {"min": 1, "max": 1024}}},
    "computation": {
        "nodes": [{"id": "sum", "op": "amber.add.v1", "inputs": ["A", "B"], "attributes": {"rounding": {"exact": "rne"}}}],
        "outputs": {"Y": "sum"},
    },
    "acceptance": {"relation": "semantic_contract", "reference": "example.add.v1"},
}


def main() -> None:
    client = AmberClient("http://127.0.0.1:8000", ROOT / ".amber-cache")
    implementation = {
        **QUERY,
        "computation": {
            "nodes": [{"id": "sum", "op": "amber.add.v1", "inputs": ["A", "B"], "attributes": {"rounding": "rne"}}],
            "outputs": {"Y": "sum"},
        },
    }
    print("spec:", client.compile(QUERY)["spec_digest"])
    source = (ROOT / "operators/add.py").read_text()
    uploaded = client.upload(implementation, TARGET, source)
    print("upload:", uploaded["implementation_digest"])
    for _ in range(2):
        result = client.search(QUERY, TARGET)
        print("search:", result["cache"], result["matches"][0]["decision"])
    path, cached = client.download(uploaded["source_digest"])
    print("download:", path, "local cache hit:", cached)
    _, cached = client.download(uploaded["source_digest"])
    print("second download local cache hit:", cached)


if __name__ == "__main__":
    main()
