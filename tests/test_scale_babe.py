import unittest

from potwatch.babe import babe_predigest
from potwatch.scale import compact, hex_bytes, ss58, vec_babe_authorities


class ScaleTests(unittest.TestCase):
    def test_compact_modes(self):
        self.assertEqual(compact(bytes([0x04])), (1, 1))            # single byte
        self.assertEqual(compact(bytes([0x15, 0x01])), (69, 2))     # two byte
        self.assertEqual(compact(bytes([0xfe, 0xff, 0x03, 0x00])), (65535, 4))  # four byte

    def test_ss58_known_dev_key(self):
        # Alice sr25519 public key -> well-known generic-substrate (prefix 42) address
        alice = hex_bytes("0xd43593c715fdd31c61141abd04a99fd6822c8558854ccde39a5684e7a56da27d")
        self.assertEqual(ss58(alice), "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY")

    def test_vec_babe_authorities(self):
        pk = bytes(range(32))
        raw = bytes([0x08]) + pk + (1).to_bytes(8, "little") + pk[::-1] + (1).to_bytes(8, "little")
        out = vec_babe_authorities(raw)
        self.assertEqual([p for p, _ in out], [pk, pk[::-1]])
        self.assertEqual([w for _, w in out], [1, 1])


class BabeTests(unittest.TestCase):
    def test_real_portaldot_testnet_header_log(self):
        # Pre-runtime digest copied from a Portaldot V3 testnet header (secondary_plain slot).
        log = "0x06424142453402000000006b52d01100000000"
        d = babe_predigest([log])
        self.assertEqual(d["kind"], "secondary_plain")
        self.assertEqual(d["authority_index"], 0)
        self.assertEqual(d["slot"], int.from_bytes(bytes.fromhex("6b52d01100000000"), "little"))

    def test_no_babe_log(self):
        self.assertIsNone(babe_predigest(["0x0541555241" + "00" * 8]))


if __name__ == "__main__":
    unittest.main()
