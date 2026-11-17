import copy
import unittest

from amber_spec import SpecError, digest, match_spec, validate_spec


QUERY = {
    "language_version": "0.1-mvp",
    "signature": {
        "inputs": {"A": {"dtype": "bf16", "shape": ["M", "K"]}, "B": {"dtype": "bf16", "shape": ["K", "N"]}},
        "outputs": {"Y": {"dtype": "bf16", "shape": ["M", "N"]}},
    },
    "domain": {"dimensions": {"M": {"min": 1, "max": 64}, "N": {"min": 4096, "max": 4096}, "K": {"min": 4096, "max": 4096}}},
    "computation": {"nodes": [{"id": "dot", "op": "amber.matmul.v1", "inputs": ["A", "B"], "attributes": {"accumulate": {"exact": "fp32"}, "reduction_order": {"any": True}}}], "outputs": {"Y": "dot"}},
    "acceptance": {"relation": "semantic_contract", "reference": "example.matmul.v1"},
}


def candidate() -> dict:
    value = copy.deepcopy(QUERY)
    value["computation"]["nodes"][0]["attributes"] = {"accumulate": "fp32", "reduction_order": "pairwise"}
    return value


class SpecTests(unittest.TestCase):
    def test_canonical_identity_ignores_mapping_order(self) -> None:
        self.assertEqual(digest(QUERY), digest(dict(reversed(list(QUERY.items())))))
        self.assertIs(validate_spec(QUERY), QUERY)

    def test_precision_and_input_domain_are_independent(self) -> None:
        implementation = candidate()
        self.assertEqual(match_spec(QUERY, implementation)["decision"], "candidate")
        implementation["domain"]["dimensions"]["M"] = {"min": 1, "max": 1}
        self.assertEqual(match_spec(QUERY, implementation)["decision"], "rejected")
        one_shape = copy.deepcopy(QUERY)
        one_shape["domain"]["dimensions"]["M"] = {"min": 1, "max": 1}
        self.assertEqual(match_spec(one_shape, implementation)["decision"], "candidate")
        one_shape["computation"]["nodes"][0]["attributes"]["accumulate"] = {"exact": "fp64"}
        report = match_spec(one_shape, implementation)
        self.assertEqual(report["decision"], "rejected")
        self.assertIn("accumulate", report["reasons"][0])

    def test_undeclared_property_is_unknown(self) -> None:
        implementation = candidate()
        del implementation["computation"]["nodes"][0]["attributes"]["accumulate"]
        self.assertEqual(match_spec(QUERY, implementation)["decision"], "unknown")

    def test_invalid_graph_is_rejected(self) -> None:
        invalid = copy.deepcopy(QUERY)
        invalid["computation"]["nodes"][0]["inputs"] = ["missing"]
        with self.assertRaises(SpecError):
            validate_spec(invalid)


if __name__ == "__main__":
    unittest.main()
