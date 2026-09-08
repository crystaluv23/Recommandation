"""Dataset preparation and inventory runtime tests."""

from tests.evolution_runtime_test_support import *  # noqa: F403


class IdentityBoundaryPerformanceTests(TestCase):
    def test_identity_scan_compiles_aliases_once_per_payload_traversal(self) -> None:
        aliases = tuple(f"Example Holdings {index}" for index in range(80))
        real_compile = re.compile

        def compile_count(value: object) -> int:
            with mock.patch.object(
                evolution_runtime_module.re,
                "compile",
                side_effect=real_compile,
            ) as compile_mock:
                evolution_runtime_module._scan_payload(
                    value,
                    allow_outcomes=True,
                    anonymous_aliases=aliases,
                )
            return compile_mock.call_count

        one_leaf = compile_count({"value": "ordinary reflection"})
        many_leaves = compile_count(
            {f"value_{index}": "ordinary reflection" for index in range(180)}
        )

        self.assertEqual(many_leaves, one_leaf)


class LocalInventoryTests(TestCase):
    def test_expansion_split_keeps_two_validation_issuers_when_capacity_allows(self) -> None:
        candidates = [
            {
                "company_id": f"issuer_{index}",
                "selection_stratum": "surge_10x_plus",
            }
            for index in range(5)
        ]

        splits = evolution_runtime_module._propose_expanded_issuer_splits(
            candidates,
            seed="rare-class-rotation",
        )

        self.assertEqual(len(splits["discovery"]), 2)
        self.assertEqual(len(splits["evolution_validation"]), 2)
        self.assertEqual(len(splits["locked_test"]), 1)

    def test_expansion_keeps_later_eligible_case_when_earlier_date_precedes_ipo(self) -> None:
        listing = {
            "symbol": "LATE",
            "name": "Later Listing Corp",
            "cik": "123456",
            "exchange": "NASDAQ",
            "ipo_date": "2025-02-01",
        }
        bars = [
            {
                "as_of_date": f"2025-02-{day:02d}",
                "adjusted_close": 10.0,
                "volume": 200_000,
            }
            for day in range(10, 29)
        ]
        bars.extend(
            {
                "as_of_date": f"2025-03-{day:02d}",
                "adjusted_close": 12.0,
                "volume": 200_000,
            }
            for day in range(10, 15)
        )
        bars.append(
            {
                "as_of_date": "2025-09-10",
                "adjusted_close": 12.0,
                "volume": 200_000,
            }
        )

        candidate, exclusions = evolution_runtime_module._expansion_candidate(
            listing,
            bars,
            prediction_dates=(date(2025, 1, 10), date(2025, 3, 10)),
        )

        self.assertIsNotNone(candidate)
        self.assertEqual(
            [case["prediction_time"][:10] for case in candidate["cases"]],
            ["2025-03-10"],
        )
        self.assertEqual(
            [item["reason"] for item in exclusions],
            ["prediction_before_listing_ipo_date"],
        )

    def test_legacy_53_case_dataset_fails_v5_anchor_preflight_without_calls(self) -> None:
        manifest = (
            PROJECT_ROOT
            / "runs"
            / "cold_start"
            / "evolution"
            / "deepseek-v4-flash-overnight-v3"
            / "dataset_proposal"
            / "dataset_manifest.approved.json"
        )
        with self.assertRaisesRegex(ValidationError, "missing anchor split"):
            load_approved_development_dataset(manifest)

    def test_inventory_hashes_current_local_shapes_without_reusing_legacy_label(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = root / "cases.json"
            documents = root / "documents.json"
            prices = root / "prices.json"
            write_json(
                cases,
                {
                    "cases": [
                        {
                            "outcome_definition_id": "legacy-terminal-return",
                            "packet": {
                                "as_of": {"as_of_date": "2025-01-01"},
                                "company": {"ticker": {"symbol": "AAA"}},
                            },
                        },
                        {
                            "outcome_definition_id": "legacy-terminal-return",
                            "packet": {
                                "as_of": {"as_of_date": "2025-02-01"},
                                "company": {"ticker": {"symbol": "BBB"}},
                            },
                        },
                    ]
                },
            )
            write_json(
                documents,
                {
                    "documents_by_symbol": {
                        "AAA": [
                            {
                                "available_date": "2024-12-31",
                                "text": "public evidence",
                            }
                        ]
                    }
                },
            )
            write_json(
                prices,
                {
                    "schema_version": "scheme-evolution-adjusted-prices-v1",
                    "source": "fixture",
                    "start_date": "2024-12-01",
                    "end_date": "2025-08-01",
                    "requested_symbol_count": 2,
                    "bars_by_symbol": {
                        "AAA": [{"as_of_date": "2025-01-02", "adjusted_close": 10}],
                    },
                    "failed_symbols": {"BBB": "missing"},
                },
            )
            inventory = inventory_local_evolution_inputs(
                cases_path=cases,
                documents_path=documents,
                adjusted_prices_path=prices,
            )
            self.assertEqual(inventory.compatible_case_count, 1)
            self.assertFalse(inventory.migration_ready)
            self.assertEqual(len(inventory.inventory_hash), 64)
            self.assertIn("terminal-return", inventory.incompatible_label_reason)
            self.assertFalse(inventory.to_dict()["locked_test_accessed"])

    def test_raw_info_migration_excludes_labels_and_future_prices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = root / "cases.json"
            documents = root / "documents.json"
            prices = root / "prices.json"
            raw_info = root / "raw_info"
            write_json(
                cases,
                {
                    "cases": [
                        {
                            "case_id": "AAA:2025-01-10:winner",
                            "label": "winner",
                            "outcome_return": 8.0,
                            "packet": {
                                "as_of": {"as_of_date": "2025-01-10"},
                                "company": {"ticker": {"symbol": "AAA"}},
                            },
                        }
                    ]
                },
            )
            write_json(
                documents,
                {
                    "documents_by_symbol": {
                        "AAA": [
                            {
                                "document_id": "sec:aaa:1",
                                "source_id": "sec:aaa:1",
                                "source_url": "https://example.test/filing",
                                "kind": "filing",
                                "published_date": "2025-01-05",
                                "available_date": "2025-01-05",
                                "title": "Filed report",
                                "text": "Revenue was reported before prediction time.",
                            }
                        ]
                    }
                },
            )
            write_json(
                prices,
                {
                    "schema_version": "scheme-evolution-adjusted-prices-v1",
                    "source": "fixture",
                    "start_date": "2025-01-01",
                    "end_date": "2025-07-10",
                    "requested_symbol_count": 1,
                    "bars_by_symbol": {
                        "AAA": [
                            {"as_of_date": "2025-01-09", "adjusted_close": 10},
                            {"as_of_date": "2025-01-10", "adjusted_close": 20},
                            {"as_of_date": "2025-02-01", "adjusted_close": 80},
                        ]
                    },
                    "failed_symbols": {},
                },
            )
            filtered = filter_case_price_history(
                cases_path=cases,
                full_price_archive_path=prices,
                output_path=root / "filtered_prices.json",
            )
            self.assertEqual(filtered.facts["priced_symbol_count"], 1)
            report = migrate_legacy_raw_info(
                cases_path=cases,
                documents_path=documents,
                adjusted_prices_path=prices,
                raw_info_root=raw_info,
            )
            self.assertEqual(report.migrated_source_documents, 1)
            self.assertEqual(report.migrated_market_snapshots, 1)
            replay = migrate_legacy_raw_info(
                cases_path=cases,
                documents_path=documents,
                adjusted_prices_path=prices,
                raw_info_root=raw_info,
            )
            self.assertEqual(replay.migrated_source_documents, 1)
            self.assertEqual(replay.appended_source_documents, 0)
            store = RawInfoStore(raw_info)
            serialized = json.dumps([item.to_dict() for item in store.documents])
            self.assertNotIn("winner", serialized)
            self.assertNotIn("outcome_return", serialized)
            market = next(
                item for item in store.documents if item.source_type == "market_data"
            )
            self.assertEqual(market.metadata["prices"], [10.0])

    def test_dataset_proposal_recomputes_two_x_label_and_needs_exact_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases_path = root / "cases.json"
            documents_path = root / "documents.json"
            prices_path = root / "prices.json"
            symbols = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
            cases = []
            bars_by_symbol = {}
            for index, symbol in enumerate(symbols):
                cases.append(
                    {
                        "case_id": f"{symbol}:legacy",
                        "label": "legacy-value-must-not-be-reused",
                        "packet": {
                            "as_of": {"as_of_date": "2025-01-10"},
                            "company": {
                                "ticker": {
                                    "symbol": symbol,
                                    "company_name": f"{symbol} Corp",
                                },
                                "industry": "fixture",
                            },
                        },
                    }
                )
                future_price = 25.0 if index < 3 else 12.0
                bars_by_symbol[symbol] = [
                    *[
                        {
                            "as_of_date": f"2025-01-0{day}",
                            "adjusted_close": 10.0,
                        }
                        for day in range(5, 10)
                    ],
                    *[
                        {
                            "as_of_date": f"2025-01-{day:02d}",
                            "adjusted_close": future_price,
                        }
                        for day in range(10, 15)
                    ],
                    {"as_of_date": "2025-07-10", "adjusted_close": future_price},
                ]
            write_json(cases_path, {"cases": cases})
            write_json(
                documents_path,
                {"documents_by_symbol": {symbol: [] for symbol in symbols}},
            )
            write_json(
                prices_path,
                {
                    "schema_version": "scheme-evolution-adjusted-prices-v1",
                    "source": "fixture",
                    "start_date": "2025-01-05",
                    "end_date": "2025-07-10",
                    "requested_symbol_count": 6,
                    "bars_by_symbol": bars_by_symbol,
                    "failed_symbols": {},
                },
            )
            report = prepare_dataset_proposal(
                cases_path=cases_path,
                documents_path=documents_path,
                adjusted_prices_path=prices_path,
                output_root=root / "proposal",
            )
            self.assertEqual(report.eligible_case_count, 6)
            self.assertEqual(report.split_surge_counts, {
                "discovery": 1,
                "evolution_validation": 1,
                "locked_test": 1,
            })
            with self.assertRaisesRegex(ValidationError, "hash"):
                approve_dataset_proposal(
                    proposal_manifest_path=report.manifest_path,
                    expected_proposal_hash="0" * 64,
                    approved_by="reviewer",
                )
            with self.assertRaisesRegex(
                ValidationError,
                "expanded proposal with Anchor",
            ):
                approve_dataset_proposal(
                    proposal_manifest_path=report.manifest_path,
                    expected_proposal_hash=report.manifest_hash,
                    approved_by="reviewer",
                )

    def test_full_market_expansion_is_fixed_date_deduplicated_and_proposal_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            universe_path = root / "universe.json"
            prices_path = root / "prices.json"
            anchors_path = root / "anchors.json"
            multiples = (1.2, 1.7, 2.5, 4.0, 12.0)
            issuer_counts = (10, 10, 9, 7, 4)
            listings = []
            bars_by_symbol = {}
            for stratum_index, multiple in enumerate(multiples):
                for issuer_index in range(issuer_counts[stratum_index]):
                    symbol = f"S{stratum_index}{issuer_index}"
                    cik = str(1000 + stratum_index * 10 + issuer_index)
                    listings.append(
                        {
                            "symbol": symbol,
                            "name": f"{symbol} Corp",
                            "cik": cik,
                            "exchange": "NASDAQ" if issuer_index % 2 else "NYSE",
                            "ipo_date": f"20{10 + issuer_index}-01-01",
                            "asset_type": "Stock",
                            "status": "Active",
                            "source": "fixture",
                            "retrieved_at": "2026-01-01T00:00:00+00:00",
                            "delisting_date": None,
                        }
                    )
                    bars_by_symbol[symbol] = _label_bars(
                        multiple,
                        volume=100_000 * (issuer_index + 1),
                    )
            listings.append(
                {
                    "symbol": "DUP",
                    "name": "Duplicate Share Class",
                    "cik": "1000",
                    "exchange": "NYSE",
                    "ipo_date": "2010-01-01",
                    "asset_type": "Stock",
                    "status": "Active",
                    "source": "fixture",
                    "retrieved_at": "2026-01-01T00:00:00+00:00",
                    "delisting_date": None,
                }
            )
            bars_by_symbol["DUP"] = _label_bars(1.2, volume=10_000_000)
            listings.append(
                {
                    "symbol": "SHRT",
                    "name": "Short History Corp",
                    "cik": "9999",
                    "exchange": "NASDAQ",
                    "ipo_date": "2024-01-01",
                    "asset_type": "Stock",
                    "status": "Active",
                    "source": "fixture",
                    "retrieved_at": "2026-01-01T00:00:00+00:00",
                    "delisting_date": None,
                }
            )
            bars_by_symbol["SHRT"] = _label_bars(1.2, complete_horizon=False)
            listings.append(
                {
                    "symbol": "PIPO",
                    "name": "Future Listing Corp",
                    "cik": "9998",
                    "exchange": "NASDAQ",
                    "ipo_date": "2025-02-01",
                    "asset_type": "Stock",
                    "status": "Active",
                    "source": "fixture",
                    "retrieved_at": "2026-01-01T00:00:00+00:00",
                    "delisting_date": None,
                }
            )
            bars_by_symbol["PIPO"] = _label_bars(1.2)
            abnormal_listings = [
                ("SPACX", "Example Acquisition V Corp", "9100"),
                ("ROMX", "Example Holdings X Inc - Class A", "9104"),
                ("NOCIK", "No CIK Operating Corp", None),
                ("ILLA", "Illiquid Operating Corp", "9102"),
                ("SPLT", "Split Artifact Corp", "9103"),
            ]
            for symbol, name, cik in abnormal_listings:
                listings.append(
                    {
                        "symbol": symbol,
                        "name": name,
                        "cik": cik,
                        "exchange": "NASDAQ",
                        "ipo_date": "2010-01-01",
                        "asset_type": "Stock",
                        "status": "Active",
                        "source": "fixture",
                        "retrieved_at": "2026-01-01T00:00:00+00:00",
                        "delisting_date": None,
                    }
                )
            bars_by_symbol["SPACX"] = _label_bars(1.2)
            bars_by_symbol["NOCIK"] = _label_bars(1.2)
            bars_by_symbol["ILLA"] = _label_bars(1.2, volume=10_000)
            bars_by_symbol["SPLT"] = _label_bars(1.2)
            bars_by_symbol["SPLT"][20]["adjusted_close"] = 50.0
            write_json(universe_path, {"listing_count": len(listings), "listings": listings})
            write_json(
                prices_path,
                {
                    "schema_version": "fixture-prices-v1",
                    "bars_by_symbol": bars_by_symbol,
                    "warning_count": 0,
                },
            )
            write_anchor_spec(
                anchors_path,
                [
                    *((f"S2{index}", "2_3x") for index in range(5)),
                    *((f"S3{index}", "3_10x") for index in range(3)),
                    ("S40", "10x_plus"),
                ],
            )

            report = prepare_expanded_dataset_proposal(
                universe_path=universe_path,
                full_price_archive_path=prices_path,
                output_root=root / "proposal",
                prediction_dates=[date(2025, 1, 10)],
                split_seed="fixture-expansion",
                anchor_cases_path=anchors_path,
            )

            self.assertEqual(report.universe_listing_count, 48)
            self.assertEqual(report.priced_symbol_count, 45)
            self.assertEqual(report.eligible_issuer_count, 40)
            self.assertEqual(report.selection_mode, "all_eligible")
            self.assertEqual(report.selected_issuer_count, 40)
            self.assertEqual(report.case_count, 40)
            self.assertEqual(
                report.selected_stratum_counts,
                report.available_stratum_counts,
            )
            self.assertEqual(report.split_issuer_counts["anchor"], 16)
            self.assertEqual(report.split_surge_counts["anchor"], 9)
            self.assertEqual(report.exclusion_reason_counts["duplicate_issuer_identity"], 1)
            self.assertEqual(report.exclusion_reason_counts["incomplete_six_month_price_horizon"], 1)
            self.assertEqual(report.exclusion_reason_counts["prediction_before_listing_ipo_date"], 1)
            self.assertEqual(
                report.exclusion_reason_counts["non_operating_or_spac_issuer"], 2
            )
            self.assertEqual(report.exclusion_reason_counts["missing_reviewed_cik"], 1)
            self.assertEqual(
                report.exclusion_reason_counts[
                    "below_minimum_pre_prediction_dollar_volume"
                ],
                1,
            )
            self.assertEqual(
                report.exclusion_reason_counts[
                    "extreme_adjusted_price_discontinuity"
                ],
                1,
            )
            self.assertFalse(report.to_dict()["locked_test_accessed"])
            self.assertEqual(report.to_dict()["external_calls"], 0)

            manifest = json.loads(Path(report.manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["case_generation"]["eligibility"],
                "each_case_independently_passes_point_in_time_normality_gate",
            )
            self.assertEqual(
                manifest["case_generation"]["issuer_retention"],
                "at_least_one_eligible_case",
            )
            self.assertEqual(manifest["selection"]["mode"], "all_eligible")
            self.assertIsNone(manifest["selection"]["requested_issuer_cap"])
            self.assertIsNone(manifest["selection"]["weights"])
            self.assertTrue(manifest["approval_blockers"])
            acquisition_path = Path(
                manifest["audit_artifacts"]["acquisition_scope"]["path"]
            )
            acquisition_text = acquisition_path.read_text(encoding="utf-8")
            acquisition = json.loads(acquisition_text)
            self.assertEqual(acquisition["company_count"], 40)
            self.assertFalse(acquisition["outcome_fields_included"])
            self.assertFalse(acquisition["split_ownership_included"])
            self.assertNotIn("ground_truth", acquisition_text)
            self.assertNotIn("selection_stratum", acquisition_text)
            self.assertNotIn("locked_test", acquisition_text)
            issuer_sets = []
            for split_name in ("discovery", "evolution_validation", "locked_test"):
                split = json.loads(
                    Path(manifest["artifacts"][split_name]["path"]).read_text(encoding="utf-8")
                )
                issuer_sets.append({row["company_id"] for row in split["cases"]})
            self.assertFalse(issuer_sets[0] & issuer_sets[1])
            self.assertFalse(issuer_sets[0] & issuer_sets[2])
            self.assertFalse(issuer_sets[1] & issuer_sets[2])

            approved = approve_dataset_proposal(
                proposal_manifest_path=report.manifest_path,
                expected_proposal_hash=report.manifest_hash,
                approved_by="reviewer",
            )
            development = load_approved_development_dataset(approved)
            self.assertEqual(len(development.anchor), 16)
            self.assertEqual(len(development.evolution_validation), 9)

            replay = prepare_expanded_dataset_proposal(
                universe_path=universe_path,
                full_price_archive_path=prices_path,
                output_root=root / "proposal",
                prediction_dates=[date(2025, 1, 10)],
                split_seed="fixture-expansion",
                anchor_cases_path=anchors_path,
            )
            self.assertEqual(replay.to_dict(), report.to_dict())

            decisions_path = root / "identity_decisions.json"
            decisions = {
                "schema_version": "expanded-case-identity-decisions-v1",
                "review_status": "agent_proposed_pending_human_review",
                "decision_count": 2,
                "decisions": [
                    {
                        "decision_id": "fixture-set-cik",
                        "symbol": "S00",
                        "action": "set_cik",
                        "cik": "8000",
                        "applies_from": "2025-01-10",
                        "applies_to": "2025-01-10",
                        "rationale": "official filing identifies the issuer",
                        "evidence": [
                            {
                                "source_url": (
                                    "https://www.sec.gov/Archives/edgar/data/8000/fixture.htm"
                                ),
                                "filing_date": "2025-01-01",
                                "observed_fact": "The filing identifies S00 under CIK 8000.",
                            }
                        ],
                    },
                    {
                        "decision_id": "fixture-exclude-preipo",
                        "symbol": "PIPO",
                        "action": "exclude",
                        "applies_from": "2025-01-10",
                        "applies_to": "2025-01-10",
                        "rationale": "the symbol is not valid at the prediction date",
                        "evidence": [
                            {
                                "source_url": (
                                    "https://www.sec.gov/Archives/edgar/data/9998/fixture.htm"
                                ),
                                "filing_date": "2025-01-01",
                                "observed_fact": "The filing proves a different valid period.",
                            }
                        ],
                    },
                ],
            }
            decisions["decision_hash"] = hashlib.sha256(
                json.dumps(
                    decisions, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()
            write_json(decisions_path, decisions)
            identity_report = prepare_expanded_dataset_proposal(
                universe_path=universe_path,
                full_price_archive_path=prices_path,
                output_root=root / "proposal-identity",
                prediction_dates=[date(2025, 1, 10)],
                target_issuers=15,
                stratum_weights={key: 1.0 for key in report.selected_stratum_counts},
                split_seed="fixture-expansion",
                identity_decisions_path=decisions_path,
                anchor_cases_path=anchors_path,
            )
            self.assertEqual(identity_report.universe_listing_count, 48)
            self.assertEqual(identity_report.eligible_issuer_count, 41)
            self.assertEqual(identity_report.selection_mode, "stratified_cap")
            self.assertEqual(identity_report.selected_issuer_count, 31)
            self.assertEqual(
                identity_report.exclusion_reason_counts["identity_decision_exclude"],
                1,
            )
            identity_manifest = json.loads(
                Path(identity_report.manifest_path).read_text(encoding="utf-8")
            )
            self.assertEqual(identity_manifest["identity_decisions"]["decision_count"], 2)
            self.assertEqual(identity_manifest["identity_decisions"]["cik_update_count"], 1)
            self.assertEqual(identity_manifest["identity_decisions"]["exclusion_count"], 1)
            self.assertEqual(
                identity_manifest["counts"]["identity_eligible_universe_listings"],
                47,
            )
            self.assertIn(
                "human-review the exact applied identity-decision artifact",
                identity_manifest["approval_blockers"],
            )
            inventory = json.loads(
                Path(
                    identity_manifest["audit_artifacts"]["candidate_inventory"]["path"]
                ).read_text(encoding="utf-8")
            )
            inventory_company_ids = {
                row["company_id"] for row in inventory["candidates"]
            } | {row["company_id"] for row in inventory["anchor_cases"]}
            self.assertIn("cik_0000008000", inventory_company_ids)
            identity_replay = prepare_expanded_dataset_proposal(
                universe_path=universe_path,
                full_price_archive_path=prices_path,
                output_root=root / "proposal-identity",
                prediction_dates=[date(2025, 1, 10)],
                target_issuers=15,
                stratum_weights={key: 1.0 for key in report.selected_stratum_counts},
                split_seed="fixture-expansion",
                identity_decisions_path=decisions_path,
                anchor_cases_path=anchors_path,
            )
            self.assertEqual(identity_replay.to_dict(), identity_report.to_dict())

            invalid_evidence = json.loads(json.dumps(decisions))
            invalid_evidence["decisions"][0]["evidence"][0]["source_url"] = (
                "https://example.com/not-sec.htm"
            )
            invalid_evidence.pop("decision_hash")
            invalid_evidence["decision_hash"] = hashlib.sha256(
                json.dumps(
                    invalid_evidence, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()
            write_json(decisions_path, invalid_evidence)
            with self.assertRaisesRegex(ValidationError, "official SEC"):
                prepare_expanded_dataset_proposal(
                    universe_path=universe_path,
                    full_price_archive_path=prices_path,
                    output_root=root / "invalid-evidence-proposal",
                    prediction_dates=[date(2025, 1, 10)],
                    target_issuers=15,
                    identity_decisions_path=decisions_path,
                    anchor_cases_path=anchors_path,
                )

            future_evidence = json.loads(json.dumps(decisions))
            future_evidence["decisions"][0]["evidence"][0]["filing_date"] = (
                "2025-01-11"
            )
            future_evidence.pop("decision_hash")
            future_evidence["decision_hash"] = hashlib.sha256(
                json.dumps(
                    future_evidence, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()
            write_json(decisions_path, future_evidence)
            with self.assertRaisesRegex(ValidationError, "postdates"):
                prepare_expanded_dataset_proposal(
                    universe_path=universe_path,
                    full_price_archive_path=prices_path,
                    output_root=root / "future-evidence-proposal",
                    prediction_dates=[date(2025, 1, 10)],
                    target_issuers=15,
                    identity_decisions_path=decisions_path,
                    anchor_cases_path=anchors_path,
                )

            tampered = dict(decisions)
            tampered["review_status"] = "human_reviewed"
            write_json(decisions_path, tampered)
            with self.assertRaisesRegex(ValidationError, "hash mismatch"):
                prepare_expanded_dataset_proposal(
                    universe_path=universe_path,
                    full_price_archive_path=prices_path,
                    output_root=root / "tampered-proposal",
                    prediction_dates=[date(2025, 1, 10)],
                    target_issuers=15,
                    identity_decisions_path=decisions_path,
                    anchor_cases_path=anchors_path,
                )
