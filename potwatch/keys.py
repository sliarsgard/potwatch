"""Storage keys: twox128(pallet) ++ twox128(item). Derivation verified in tests/test_keys.py when xxhash is installed."""
STORAGE = {
    ("Timestamp", "Now"): "0xf0c365c3cf59d671eb72da0e7a4113c49f1f0515f462cdcf84e0f1d6045dfcbb",
    ("Session", "Validators"): "0xcec5070d609dd3497f72bde07fc96ba088dcde934c658227ee1dfafcd6e16903",
    ("Session", "CurrentIndex"): "0xcec5070d609dd3497f72bde07fc96ba072763800a36a99fdfc7c10f6415f6ee6",
    ("Babe", "Authorities"): "0x1cb6f36e027abb2091cfb5110ab5087f5e0621c4869aa60c02be9adcc98a0d1d",
    ("Babe", "EpochIndex"): "0x1cb6f36e027abb2091cfb5110ab5087f38316cbf8fa0da822a20ac1c55bf1be3",
    ("Babe", "CurrentSlot"): "0x1cb6f36e027abb2091cfb5110ab5087f06155b3cd9a8c9e5e9a23fd5dc13a5ed",
    ("Staking", "ActiveEra"): "0x5f3e4907f716ac89b6347d15ececedca487df464e44a534ba6b0cbb32407b587",
    ("Staking", "ValidatorCount"): "0x5f3e4907f716ac89b6347d15ececedca138e71612491192d68deab7e6f563fe1",
    ("Grandpa", "CurrentSetId"): "0x5f9cc45b7a00c5899361e1c6099678dc8a2d09463effcc78a22d75b9cb87dffc",
}
