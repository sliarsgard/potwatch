import importlib.util
import pathlib
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("deployment", ROOT / "scripts" / "deployment.py")
dep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dep)

CFG, ART = dep.load("portaldot-v3-testnet")
DEPLOYER = "0x" + "a1" * 20
CONTRACT = "0x" + "c0" * 20
DEPLOY_TX, ATTEST_TX = "0x" + "11" * 32, "0x" + "22" * 32
NET = "0x" + "portaldot-v3-testnet".encode().hex().ljust(64, "0")
DIGEST = "ab" * 32


def fake_chain(code=ART["deployedBytecode"], owner=DEPLOYER):
    receipts = {
        DEPLOY_TX: {"status": "0x1", "contractAddress": CONTRACT, "from": DEPLOYER, "to": None,
                    "blockNumber": hex(236000), "transactionIndex": "0x1", "logs": []},
        ATTEST_TX: {"status": "0x1", "contractAddress": None, "from": DEPLOYER, "to": CONTRACT,
                    "blockNumber": hex(236010), "transactionIndex": "0x2",
                    "logs": [{"address": CONTRACT, "topics": ["0x" + "ee" * 32, "0x" + "0" * 64, NET]}]},
    }

    def call(self, method, params=None):
        self._check(method, params)
        if method == "eth_getTransactionReceipt":
            return receipts.get(params[0]), 1.0
        if method == "eth_getCode":
            return code, 1.0
        data = params[0]["data"]
        if data == dep.selector(ART, "owner()"):
            return "0x" + owner[2:].rjust(64, "0"), 1.0
        if data == dep.selector(ART, "count()"):
            return "0x" + "1".rjust(64, "0"), 1.0
        if data.startswith(dep.selector(ART, "latest(bytes32)")):
            return "0x" + DIGEST + "0" * 64 * 7, 1.0
        raise AssertionError(data)

    def get(url, params=None, timeout=None):
        height = int(url.rsplit("/", 2)[1])
        items = [{"indexer": {"blockHeight": height, "extrinsicIndex": 0}, "call": {"section": "timestamp"}},
                 {"indexer": {"blockHeight": height, "extrinsicIndex": 3}, "call": {"section": "revive"}}]
        return mock.Mock(json=lambda: {"items": items}, raise_for_status=lambda: None)

    return mock.patch.object(dep.Rpc, "call", call), mock.patch.object(dep.requests, "get", get)


class VerifyDeployment(unittest.TestCase):
    def run_verify(self, **kw):
        p1, p2 = fake_chain(**kw)
        with p1, p2:
            return dep.verify("portaldot-v3-testnet", CFG, ART, DEPLOY_TX, ATTEST_TX)

    def test_records_address_hashes_and_explorer_links_from_chain(self):
        d = self.run_verify()
        self.assertEqual(d["contract"], CONTRACT)
        self.assertEqual(d["deploy"]["tx"], DEPLOY_TX)
        self.assertEqual(d["deploy"]["links"]["extrinsic"], "https://scanner-testnet-v3.portaldot.dev/extrinsics/236000-3")
        self.assertEqual(d["attest"]["network"], "portaldot-v3-testnet")
        self.assertEqual(d["attest"]["latest_digest"], "0x" + DIGEST)
        md = dep.markdown(d)
        self.assertIn(CONTRACT, md)
        self.assertIn(ATTEST_TX, md)

    def test_rejects_code_that_differs_from_build(self):
        with self.assertRaises(SystemExit):
            self.run_verify(code="0x6000")

    def test_accepts_same_code_with_other_metadata_hash(self):
        built = ART["deployedBytecode"]
        n = int(built[-4:], 16)
        other = built[: -(n + 2) * 2] + "ff" * n + built[-4:]
        self.assertEqual(self.run_verify(code=other)["code_match"], "same-except-metadata")

    def test_rejects_foreign_owner(self):
        with self.assertRaises(SystemExit):
            self.run_verify(owner="0x" + "99" * 20)

    def test_revive_extrinsic_falls_back_to_tx_index_when_ambiguous(self):
        items = [{"indexer": {"extrinsicIndex": i}, "call": {"section": "revive"}} for i in (2, 5)]
        self.assertEqual(dep.revive_extrinsic(items, 5)["indexer"]["extrinsicIndex"], 5)
        self.assertIsNone(dep.revive_extrinsic(items, 7))


class LocalNetwork(unittest.TestCase):
    def test_local_network_without_explorer_records_rpc_instead_of_links(self):
        cfg, _ = dep.load("local-anvil", ROOT / "networks.local.json")
        self.assertEqual(cfg["expected_evm_chain_id"], CFG["expected_evm_chain_id"])
        p1, p2 = fake_chain()
        with p1, p2:
            d = dep.verify("local-anvil", cfg, ART, DEPLOY_TX, ATTEST_TX)
        self.assertEqual(d["deploy"]["links"], {})
        md = dep.markdown(d)
        self.assertIn("not the public V3 testnet", md)
        self.assertIn("| Explorer | none (local chain, RPC `http://127.0.0.1:8545`) |", md)


class ReplaceBlock(unittest.TestCase):
    def test_replaces_only_marked_block(self):
        text = f"a\n{dep.START}\nTODO\n{dep.END}\nb"
        self.assertEqual(dep.replace_block(text, "X"), f"a\n{dep.START}\nX\n{dep.END}\nb")

    def test_readme_has_markers(self):
        dep.replace_block((ROOT / "README.md").read_text(), "X")


if __name__ == "__main__":
    unittest.main()
