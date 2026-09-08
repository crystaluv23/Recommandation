"""Signal Mining, Update, and exploration role-adapter tests."""

from tests.evolution_runtime_test_support import *  # noqa: F403


class SignalRoleAdapterTests(TestCase):
    def test_signal_h1_rejects_empty_portfolio_with_unmet_signal_demand(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {"hypotheses": []},
                {
                    "hypotheses": [
                        {
                            "hypothesis_id": "analyst_estimate_revision_gap",
                            "statement": (
                                "Analyst estimate revisions distinguish the fixed "
                                "Discovery groups."
                            ),
                            "applicability": "all_ready_issuers",
                            "expected_positive_pattern": (
                                "Positive cases show stronger analyst estimate "
                                "revisions than control cases."
                            ),
                            "source_types": ["news"],
                            "query": "analyst estimate revision",
                            "falsifiers": [
                                "Positive and control groups show overlapping or "
                                "reversed estimate revisions."
                            ],
                            "lookback_days": 365,
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["news"],
                "capability_backlog": {
                    "signal_need_items": [
                        {"need": "How have analyst estimate revisions changed?"}
                    ]
                },
            }
        )

        self.assertEqual(result.value[0].hypothesis_id, "analyst_estimate_revision_gap")
        self.assertIn(
            "must return at least one grounded hypothesis",
            validation_error(caller.calls[1]),
        )

    def test_signal_h1_corrects_hypothesis_unrelated_to_bootstrap_need(self) -> None:
        ungrounded = {
            "hypotheses": [
                {
                    "hypothesis_id": "large_order_confirmation",
                    "statement": "Material order confirmation precedes repricing.",
                    "applicability": "Project-driven companies.",
                    "expected_positive_pattern": (
                        "Positive cases confirm more orders than control cases."
                    ),
                    "source_types": ["news"],
                    "query": "material order customer award",
                    "falsifiers": ["Controls confirm orders equally often."],
                    "lookback_days": 365,
                }
            ]
        }
        grounded = {
            "hypotheses": [
                {
                    "hypothesis_id": "production_cost_guidance_gap",
                    "statement": (
                        "Production volume and cost-per-ounce guidance gaps may "
                        "precede repricing."
                    ),
                    "applicability": "all_ready_issuers",
                    "expected_positive_pattern": (
                        "Positive cases beat production and unit-cost guidance more "
                        "often than control cases."
                    ),
                    "source_types": ["news"],
                    "query": "production volume cost ounce guidance",
                    "falsifiers": [
                        "Positive cases and control cases beat the same guidance "
                        "equally often."
                    ],
                    "lookback_days": 365,
                }
            ]
        }
        caller = ScriptedRoleCaller([ungrounded, grounded])
        model = LLMSignalMiningModel(caller)

        result = model.propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["news"],
                "capability_backlog": {
                    "signal_need_items": [
                        {
                            "need": (
                                "What are recent production volumes and cost per "
                                "ounce, and how do they compare to guidance?"
                            )
                        }
                    ]
                },
            }
        )

        self.assertEqual(
            caller.stages,
            ["signal_mining_hypotheses", "signal_mining_hypotheses_correction"],
        )
        self.assertIn("at least two", validation_error(caller.calls[1]))
        self.assertEqual(result.value[0].hypothesis_id, "production_cost_guidance_gap")

    def test_signal_h1_corrects_renamed_existing_stable_signal(self) -> None:
        duplicate = {
            "hypotheses": [
                {
                    "hypothesis_id": "revenue_growth_trajectory_shift",
                    "statement": (
                        "Accelerating year-over-year revenue growth precedes repricing."
                    ),
                    "applicability": "Companies with quarterly revenue history.",
                    "expected_positive_pattern": (
                        "Positive cases show stronger revenue acceleration than "
                        "control cases."
                    ),
                    "source_types": ["10-q"],
                    "query": "revenue growth acceleration",
                    "falsifiers": ["Controls accelerate equally often."],
                    "lookback_days": 365,
                }
            ]
        }
        corrected = {"hypotheses": []}
        caller = ScriptedRoleCaller([duplicate, corrected])

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["10-q"],
                "registered_deterministic_functions": [
                    "financial.revenue_acceleration"
                ],
                "stable_signal_cards": [
                    {
                        "signal_id": "revenue_acceleration",
                        "signal_ref": "revenue_acceleration:v1",
                    }
                ],
            }
        )

        self.assertEqual(result.value, ())
        self.assertIn("restate", validation_error(caller.calls[1]))
        self.assertEqual(
            caller.stages,
            ["signal_mining_hypotheses", "signal_mining_hypotheses_correction"],
        )

    def test_signal_h1_allows_gap_parenthesis_and_downstream_stable_metric(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "hypotheses": [
                        {
                            "hypothesis_id": "production_volume_cost_gap",
                            "statement": (
                                "A production gap (volume versus guidance) is "
                                "associated with revenue acceleration."
                            ),
                            "applicability": "all_ready_issuers",
                            "expected_positive_pattern": (
                                "Positive cases show larger production beats and "
                                "lower unit costs than control cases."
                            ),
                            "source_types": ["10-q"],
                            "query": "production volume cost ounce guidance",
                            "falsifiers": [
                                "Positive cases and control cases show equal or "
                                "reversed production and cost gaps."
                            ],
                            "lookback_days": 365,
                        }
                    ]
                }
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["10-q"],
                "registered_deterministic_functions": [
                    "financial.revenue_acceleration"
                ],
            }
        )

        self.assertEqual(result.value[0].hypothesis_id, "production_volume_cost_gap")
        self.assertEqual(caller.stages, ["signal_mining_hypotheses"])

    def test_signal_h1_preserves_yoy_in_stable_signal_identity(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "hypotheses": [
                        {
                            "hypothesis_id": (
                                "revenue_growth_composition_core_vs_nonoperating"
                            ),
                            "statement": (
                                "Core operating contribution distinguishes the "
                                "composition of recent revenue growth."
                            ),
                            "applicability": "all_ready_issuers",
                            "expected_positive_pattern": (
                                "Positive cases show more core-driven revenue growth "
                                "than control cases."
                            ),
                            "source_types": ["10-q"],
                            "query": (
                                "core vs non-operating revenue growth segment drivers"
                            ),
                            "falsifiers": [
                                "Positive cases and control cases have equal or "
                                "reversed core operating contribution."
                            ],
                            "lookback_days": 365,
                        }
                    ]
                }
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["10-q"],
                "registered_deterministic_functions": [
                    "financial.revenue_growth_yoy"
                ],
            }
        )

        self.assertEqual(
            result.value[0].hypothesis_id,
            "revenue_growth_composition_core_vs_nonoperating",
        )
        self.assertEqual(caller.stages, ["signal_mining_hypotheses"])

    def test_signal_h1_corrects_alternate_outcome_with_stable_feedback(self) -> None:
        invalid = {
            "hypotheses": [
                {
                    "hypothesis_id": "production_guidance_gap",
                    "statement": (
                        "Production above guidance predicts revenue growth in the "
                        "next quarter."
                    ),
                    "applicability": "Commodity producers with guidance.",
                    "expected_positive_pattern": (
                        "Production beats lead to faster growth in the next quarter."
                    ),
                    "source_types": ["10-q"],
                    "query": "production volume cost ounce guidance",
                    "falsifiers": [
                        "The next quarter has the same growth after a miss."
                    ],
                    "lookback_days": 365,
                }
            ]
        }
        corrected = {
            "hypotheses": [
                {
                    **invalid["hypotheses"][0],
                    "statement": (
                        "Prediction-date production and guidance gaps distinguish "
                        "the fixed Discovery groups."
                    ),
                    "applicability": "all_ready_issuers",
                    "expected_positive_pattern": (
                        "Positive cases show larger production beats and lower unit "
                        "costs than control cases."
                    ),
                    "falsifiers": [
                        "Positive cases and control cases show equal or reversed "
                        "production beats."
                    ],
                }
            ]
        }
        caller = ScriptedRoleCaller([invalid, corrected])

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["10-q"],
            }
        )

        self.assertEqual(result.value[0].hypothesis_id, "production_guidance_gap")
        self.assertEqual(
            caller.calls[0]["system_prompt"], caller.calls[1]["system_prompt"]
        )
        self.assertIsNone(caller.calls[0]["payload"]["validation_feedback"])
        error = validation_error(caller.calls[1])
        self.assertIn("alternate horizon", error)
        self.assertIn("both positive and control groups", error)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        must_change_paths = {
            path
            for obligation in feedback["obligations"]
            for path in obligation["must_change_paths"]
        }
        self.assertIn("hypotheses[0].statement", must_change_paths)
        self.assertIn(
            "hypotheses[0].expected_positive_pattern", must_change_paths
        )
        self.assertIn("hypotheses[0].falsifiers[0]", must_change_paths)
        self.assertNotIn(
            "delete every listed quantity", caller.calls[1]["system_prompt"]
        )
        self.assertIn(
            "preserve every hypothesis whose hypothesis_id is not named",
            caller.calls[1]["system_prompt"],
        )

    def test_signal_h1_combines_identity_and_semantic_feedback_without_echo(
        self,
    ) -> None:
        invalid = {
            "hypotheses": [
                {
                    "hypothesis_id": "estimate_gap",
                    "statement": (
                        "Match Group estimate beats cause a price reaction within "
                        "5 days."
                    ),
                    "applicability": "Companies with analyst coverage.",
                    "expected_positive_pattern": (
                        "Positive group case [CASE_POSITIVE_A] beats estimates."
                    ),
                    "source_types": ["news"],
                    "query": "analyst estimate gap",
                    "falsifiers": ["No short-term price increase."],
                    "lookback_days": 365,
                }
            ]
        }
        corrected = {
            "hypotheses": [
                {
                    **invalid["hypotheses"][0],
                    "statement": (
                        "Prediction-date analyst estimate gaps distinguish the "
                        "fixed Discovery groups."
                    ),
                    "applicability": "all_ready_issuers",
                    "expected_positive_pattern": (
                        "The positive group shows larger estimate beats than the "
                        "control cases."
                    ),
                    "falsifiers": [
                        "The positive group and control group show equal or reversed "
                        "estimate beats."
                    ],
                }
            ]
        }
        caller = ScriptedRoleCaller([invalid, corrected])
        model = LLMSignalMiningModel(caller)
        model.set_identity_guard_aliases(("Match Group",))

        result = model.propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["news"],
            }
        )

        self.assertEqual(result.value[0].hypothesis_id, "estimate_gap")
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["invalid_output"], {})
        error = feedback["validation_error"]
        self.assertIn("identity alias leaked", error)
        self.assertIn("alternate horizon", error)
        self.assertIn("must not invent opaque case refs", error)
        self.assertIn("both positive and control groups", error)
        self.assertNotIn("Match Group", json.dumps(feedback))

    def test_signal_h1_rejects_data_readiness_and_raw_absolute_scale(self) -> None:
        invalid = {
            "hypotheses": [
                {
                    "hypothesis_id": "consensus_revenue_surprise",
                    "statement": (
                        "Quarterly revenue and earnings figures are available in "
                        "point-in-time filings."
                    ),
                    "applicability": "Companies with analyst consensus estimates.",
                    "expected_positive_pattern": (
                        "Positive cases (companies with higher absolute revenue) have "
                        "higher absolute revenue and earnings figures than control "
                        "cases."
                    ),
                    "source_types": ["news"],
                    "query": (
                        "Find companies where revenue surprise is more than 5% over "
                        "the last 30 days."
                    ),
                    "falsifiers": [
                        "Control cases have equal case-local consensus surprises."
                    ],
                    "lookback_days": 365,
                }
            ]
        }
        corrected = {
            "hypotheses": [
                {
                    **invalid["hypotheses"][0],
                    "statement": (
                        "Case-local quarterly revenue surprise relative to consensus "
                        "distinguishes the fixed Discovery groups."
                    ),
                    "applicability": "all_ready_issuers",
                    "expected_positive_pattern": (
                        "The positive group has more positive revenue surprise versus "
                        "its own consensus baseline than the control cases."
                    ),
                    "query": "revenue earnings consensus surprise",
                    "falsifiers": [
                        "The positive and control groups show equal or reversed "
                        "case-local consensus surprise."
                    ],
                }
            ]
        }
        caller = ScriptedRoleCaller([invalid, corrected])

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["news"],
            }
        )

        self.assertEqual(result.value[0].hypothesis_id, "consensus_revenue_surprise")
        error = validation_error(caller.calls[1])
        self.assertIn("measurable group feature", error)
        self.assertIn("normalize raw absolute scale", error)
        self.assertIn("one canonical rule", error)
        self.assertIn("positive/control group non-separation", error)
        self.assertIn("must not redefine fixed Discovery groups", error)
        self.assertIn("concise 2-8 term retrieval topic", error)
        prompt = caller.calls[0]["system_prompt"]
        self.assertIn("not merely say data are available", prompt)
        self.assertIn("Never compare raw absolute", prompt)
        self.assertIn("applicability must be exactly one non-conjunctive", prompt)
        self.assertIn("Never redefine either fixed group", prompt)
        self.assertIn("concise 2-8 term retrieval topic", prompt)

    def test_signal_h1_requires_one_rule_from_actual_h2_field_inventory(
        self,
    ) -> None:
        base = {
            "hypothesis_id": "estimate_revision_gap",
            "statement": "Estimate revisions distinguish the fixed Discovery groups.",
            "expected_positive_pattern": (
                "Positive cases show stronger revisions than control cases."
            ),
            "source_types": ["news"],
            "query": "analyst estimate revision",
            "falsifiers": [
                "Positive and control groups show overlapping or reversed revisions."
            ],
            "lookback_days": 365,
        }
        caller = ScriptedRoleCaller(
            [
                {
                    "hypotheses": [
                        {
                            **base,
                            "applicability": (
                                "Issuers on major exchanges with market data coverage."
                            ),
                        }
                    ]
                },
                {
                    "hypotheses": [
                        {**base, "applicability": "exchange_values:NYSE|NASDAQ"}
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["news"],
                "h2_applicability_contract": {
                    "observed_values": {
                        "exchange_values": ["NASDAQ", "NYSE"],
                        "industry_values": [],
                    }
                },
            }
        )

        self.assertEqual(result.value[0].applicability, "exchange_values:NYSE|NASDAQ")
        error = validation_error(caller.calls[1])
        self.assertIn("one canonical rule", error)
        self.assertIn("actual H2 profile contract", error)
        self.assertNotIn("market data coverage", caller.calls[1]["system_prompt"])

    def test_signal_h1_keeps_expected_pattern_on_retrieved_construct(self) -> None:
        invalid = {
            "hypotheses": [
                {
                    "hypothesis_id": "analyst_estimate_revision_outcome",
                    "statement": (
                        "Analyst estimate revisions distinguish the fixed "
                        "Discovery groups."
                    ),
                    "applicability": "all_ready_issuers",
                    "expected_positive_pattern": (
                        "Positive cases show stronger revenue growth than control "
                        "cases."
                    ),
                    "source_types": ["news"],
                    "query": "analyst revenue earnings estimates revised",
                    "falsifiers": [
                        "Positive and control groups show overlapping or reversed "
                        "estimate revisions."
                    ],
                    "lookback_days": 365,
                }
            ]
        }
        corrected = json.loads(json.dumps(invalid))
        corrected["hypotheses"][0]["expected_positive_pattern"] = (
            "Positive cases show more favorable analyst estimate revisions than "
            "control cases."
        )
        caller = ScriptedRoleCaller([invalid, corrected])

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["news"],
            }
        )

        self.assertEqual(
            result.value[0].hypothesis_id,
            invalid["hypotheses"][0]["hypothesis_id"],
        )
        error = validation_error(caller.calls[1])
        self.assertIn("candidate construct", error)
        self.assertIn("same candidate construct", caller.calls[0]["system_prompt"])
        self.assertEqual(
            caller.calls[1]["payload"]["validation_feedback"]["obligations"][0][
                "must_change_paths"
            ],
            ["hypotheses[0].expected_positive_pattern"],
        )

    def test_signal_h1_projects_valid_repair_and_discards_unrelated_drift(self) -> None:
        invalid_hypothesis = {
            "hypothesis_id": "analyst_estimate_revision_outcome",
            "statement": (
                "Analyst estimate revisions distinguish the fixed Discovery groups."
            ),
            "applicability": "all_ready_issuers",
            "expected_positive_pattern": (
                "Positive cases (e.g., case 23) show stronger revenue growth than "
                "control cases."
            ),
            "source_types": ["news"],
            "query": "analyst revenue earnings estimates revised",
            "falsifiers": [
                "Positive and control groups show overlapping or reversed estimate "
                "revisions."
            ],
            "lookback_days": 365,
        }
        valid_hypothesis = {
            "hypothesis_id": "production_cost_gap",
            "statement": (
                "Production costs distinguish the fixed Discovery groups."
            ),
            "applicability": "all_ready_issuers",
            "expected_positive_pattern": (
                "Positive cases show lower production costs than control cases."
            ),
            "source_types": ["10-q"],
            "query": "production cost guidance",
            "falsifiers": [
                "Positive and control groups show overlapping or reversed "
                "production costs."
            ],
            "lookback_days": 365,
        }
        invalid = {"hypotheses": [invalid_hypothesis, valid_hypothesis]}
        drifted = json.loads(json.dumps(invalid))
        drifted["hypotheses"][0]["expected_positive_pattern"] = (
            "Positive cases show more favorable analyst estimate revisions than "
            "control cases."
        )
        drifted["hypotheses"][1]["statement"] = (
            "Production cost guidance distinguishes the fixed Discovery groups."
        )
        caller = ScriptedRoleCaller([invalid, drifted])
        events: list[dict[str, object]] = []
        caller.on_progress = events.append

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["news", "10-q"],
            }
        )

        self.assertEqual(
            caller.stages,
            ["signal_mining_hypotheses", "signal_mining_hypotheses_correction"],
        )
        self.assertEqual(
            result.value[0].expected_positive_pattern,
            drifted["hypotheses"][0]["expected_positive_pattern"],
        )
        self.assertEqual(result.value[1].statement, valid_hypothesis["statement"])
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertIn("e.g.", feedback["validation_error"])
        self.assertNotIn(
            "e.g",
            {
                path
                for obligation in feedback["obligations"]
                for path in obligation["must_change_paths"]
            },
        )
        projection = next(
            item
            for item in events
            if item["event_type"] == "structured_correction_projection_applied"
        )
        self.assertEqual(
            projection["copied_paths"],
            ["hypotheses[0].expected_positive_pattern"],
        )
        self.assertEqual(projection["discarded_paths"], ["hypotheses[1]"])

    def test_signal_h1_projected_correction_still_runs_full_validation(self) -> None:
        invalid_hypothesis = {
            "hypothesis_id": "analyst_estimate_revision_outcome",
            "statement": (
                "Analyst estimate revisions distinguish the fixed Discovery groups."
            ),
            "applicability": "all_ready_issuers",
            "expected_positive_pattern": (
                "Positive cases show stronger revenue growth than control cases."
            ),
            "source_types": ["news"],
            "query": "analyst revenue earnings estimates revised",
            "falsifiers": [
                "Positive and control groups show overlapping or reversed estimate "
                "revisions."
            ],
            "lookback_days": 365,
        }
        valid_hypothesis = {
            "hypothesis_id": "production_cost_gap",
            "statement": (
                "Production costs distinguish the fixed Discovery groups."
            ),
            "applicability": "all_ready_issuers",
            "expected_positive_pattern": (
                "Positive cases show lower production costs than control cases."
            ),
            "source_types": ["10-q"],
            "query": "production cost guidance",
            "falsifiers": [
                "Positive and control groups show overlapping or reversed production "
                "costs."
            ],
            "lookback_days": 365,
        }
        invalid = {"hypotheses": [invalid_hypothesis, valid_hypothesis]}
        still_invalid = json.loads(json.dumps(invalid))
        still_invalid["hypotheses"][0]["expected_positive_pattern"] = (
            "Positive cases show more favorable analyst estimate revisions."
        )
        still_invalid["hypotheses"][1]["statement"] = (
            "Production cost guidance distinguishes the fixed Discovery groups."
        )
        caller = ScriptedRoleCaller([invalid, still_invalid])
        events: list[dict[str, object]] = []
        caller.on_progress = events.append

        with self.assertRaisesRegex(
            CandidateExecutionRejected,
            "must name both positive and control groups",
        ):
            LLMSignalMiningModel(caller).propose_hypotheses(
                {
                    "limits": {"hypothesis_limit": 3},
                    "available_raw_source_types": ["news", "10-q"],
                }
            )

        self.assertFalse(
            any(
                item["event_type"]
                == "structured_correction_projection_applied"
                for item in events
            )
        )

    def test_signal_h1_accepts_bounded_discovery_group_aliases(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "hypotheses": [
                        {
                            "hypothesis_id": "strategic_partnership_gap",
                            "statement": (
                                "Strategic partnership disclosures distinguish the "
                                "fixed Discovery groups."
                            ),
                            "applicability": "all_ready_issuers",
                            "expected_positive_pattern": (
                                "Positive Discovery cases disclose more strategic "
                                "partnerships than control Discovery cases."
                            ),
                            "source_types": ["news"],
                            "query": "strategic partnership disclosure",
                            "falsifiers": [
                                "Positive and control Discovery cases show overlap or "
                                "reversal in strategic partnership disclosures."
                            ],
                            "lookback_days": 365,
                        }
                    ]
                }
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["news"],
            }
        )

        self.assertEqual(result.value[0].hypothesis_id, "strategic_partnership_gap")
        self.assertEqual(caller.stages, ["signal_mining_hypotheses"])

    def test_signal_h1_rejects_membership_style_group_redefinition(self) -> None:
        base = {
            "hypothesis_id": "consensus_revenue_gap",
            "statement": (
                "Case-local quarterly revenue surprise distinguishes the fixed "
                "Discovery groups."
            ),
            "applicability": "all_ready_issuers",
            "source_types": ["news"],
            "query": "quarterly revenue consensus gap",
            "falsifiers": [
                "The positive and control groups show overlapping or reversed "
                "case-local consensus gaps."
            ],
            "lookback_days": 365,
        }
        caller = ScriptedRoleCaller(
            [
                {
                    "hypotheses": [
                        {
                            **base,
                            "expected_positive_pattern": (
                                "Positive cases are issuers classified in the "
                                "Discovery positive group as beating consensus; "
                                "control cases are issuers classified in the "
                                "Discovery control group as missing consensus."
                            ),
                        }
                    ]
                },
                {
                    "hypotheses": [
                        {
                            **base,
                            "expected_positive_pattern": (
                                "The fixed Discovery positive group should show a "
                                "more positive case-local consensus gap than the "
                                "fixed Discovery control group."
                            ),
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["news"],
            }
        )

        self.assertEqual(result.value[0].hypothesis_id, "consensus_revenue_gap")
        error = validation_error(caller.calls[1])
        self.assertIn("must not redefine fixed Discovery groups", error)
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["obligation_count"], 1)
        self.assertEqual(
            feedback["obligations"][0]["must_change_paths"],
            ["hypotheses[0].expected_positive_pattern"],
        )
        self.assertIn("membership clause", caller.calls[0]["system_prompt"])

    def test_signal_h1_allows_parenthetical_same_group_alias(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "hypotheses": [
                        {
                            "hypothesis_id": "revenue_composition_gap",
                            "statement": (
                                "Revenue composition distinguishes the fixed "
                                "Discovery groups."
                            ),
                            "applicability": "all_ready_issuers",
                            "expected_positive_pattern": (
                                "Positive cases (the Discovery positive group) show "
                                "more granular revenue composition than control cases "
                                "(the Discovery control group)."
                            ),
                            "source_types": ["10-k"],
                            "query": "revenue growth composition",
                            "falsifiers": [
                                "The positive and control groups show overlapping or "
                                "reversed revenue composition."
                            ],
                            "lookback_days": 365,
                        }
                    ]
                }
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["10-k"],
            }
        )

        self.assertEqual(result.value[0].hypothesis_id, "revenue_composition_gap")
        self.assertEqual(len(caller.calls), 1)

    def test_signal_h1_allows_fixed_discovery_group_alias(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "hypotheses": [
                        {
                            "hypothesis_id": "estimate_revision_gap",
                            "statement": (
                                "Estimate revisions distinguish the fixed Discovery "
                                "groups."
                            ),
                            "applicability": "all_ready_issuers",
                            "expected_positive_pattern": (
                                "Positive cases (fixed Discovery group) show more "
                                "upward revisions than control cases (fixed Discovery "
                                "group)."
                            ),
                            "source_types": ["news"],
                            "query": "analyst estimate revision",
                            "falsifiers": [
                                "The positive and control groups show overlapping or "
                                "reversed estimate revisions."
                            ],
                            "lookback_days": 365,
                        }
                    ]
                }
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["news"],
            }
        )

        self.assertEqual(result.value[0].hypothesis_id, "estimate_revision_gap")
        self.assertEqual(len(caller.calls), 1)

    def test_signal_h1_rejects_unobserved_canonical_applicability_value(
        self,
    ) -> None:
        base = {
            "hypothesis_id": "production_cost_gap",
            "statement": "Production cost gaps distinguish the fixed Discovery groups.",
            "expected_positive_pattern": (
                "Positive cases show better production cost gaps than control cases."
            ),
            "source_types": ["10-k"],
            "query": "production cost guidance gap",
            "falsifiers": [
                "Positive and control groups show overlapping or reversed gaps."
            ],
            "lookback_days": 365,
        }
        caller = ScriptedRoleCaller(
            [
                {
                    "hypotheses": [
                        {**base, "applicability": "industry_values:Metals & Mining"}
                    ]
                },
                {
                    "hypotheses": [
                        {
                            **base,
                            "applicability": (
                                "business_description_topics:mining|mineral|extraction"
                            ),
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["10-k"],
                "h2_applicability_contract": {
                    "observed_values": {"industry_values": []}
                },
            }
        )

        self.assertEqual(
            result.value[0].applicability,
            "business_description_topics:mining|mineral|extraction",
        )
        self.assertIn("unsupported: Metals & Mining", validation_error(caller.calls[1]))

    def test_signal_h2_enforces_bounded_unpadded_shortlist_and_allows_empty(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "rankings": [
                        {
                            "hypothesis_id": "mining_operations",
                            "cases": [
                                {
                                    "case_ref": case_ref,
                                    "profile_evidence": "irrelevant",
                                    "applicability_reason": "irrelevant",
                                }
                                for case_ref in ("case-001", "case-002", "case-003")
                            ],
                        }
                    ]
                },
                {
                    "rankings": [
                        {
                            "hypothesis_id": "mining_operations",
                            "cases": [],
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).rank_cases(
            {
                "hypotheses": [{"hypothesis_id": "mining_operations"}],
                "case_briefs": [
                    {"case_ref": "case-001"},
                    {"case_ref": "case-002"},
                    {"case_ref": "case-003"},
                ],
                "rules": {"max_case_refs_per_hypothesis": 2},
            }
        )

        self.assertEqual(result.value["mining_operations"], ())
        self.assertIn("exceeds", validation_error(caller.calls[1]))
        self.assertEqual(
            caller.stages,
            [
                "signal_mining_case_ranking",
                "signal_mining_case_ranking_correction",
            ],
        )

    def test_signal_h2_rejects_empty_when_canonical_visible_rule_matches(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "rankings": [
                        {"hypothesis_id": "broad_estimates", "cases": []}
                    ]
                },
                {
                    "rankings": [
                        {
                            "hypothesis_id": "broad_estimates",
                            "cases": [
                                {
                                    "case_ref": "case-001",
                                    "profile_evidence": "aerospace services",
                                    "applicability_reason": (
                                        "The canonical rule covers every ready issuer."
                                    ),
                                }
                            ],
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).rank_cases(
            {
                "hypotheses": [
                    {
                        "hypothesis_id": "broad_estimates",
                        "applicability": "all_ready_issuers",
                    }
                ],
                "case_briefs": [
                    {
                        "case_ref": "case-001",
                        "business_description": "aerospace services",
                    }
                ],
                "rules": {"max_case_refs_per_hypothesis": 1},
            }
        )

        self.assertEqual(result.value["broad_estimates"], ("case-001",))
        self.assertIn(
            "cannot return an empty ranking",
            validation_error(caller.calls[1]),
        )

    def test_signal_h2_rejects_case_outside_canonical_visible_rule(self) -> None:
        def ranking(case_ref: str, evidence: str) -> dict[str, object]:
            return {
                "rankings": [
                    {
                        "hypothesis_id": "exchange_screen",
                        "cases": [
                            {
                                "case_ref": case_ref,
                                "profile_evidence": evidence,
                                "applicability_reason": (
                                    "The visible exchange satisfies the canonical rule."
                                ),
                            }
                        ],
                    }
                ]
            }

        caller = ScriptedRoleCaller(
            [ranking("case-002", "NASDAQ"), ranking("case-001", "NYSE")]
        )
        result = LLMSignalMiningModel(caller).rank_cases(
            {
                "hypotheses": [
                    {
                        "hypothesis_id": "exchange_screen",
                        "applicability": "exchange_values:NYSE",
                    }
                ],
                "case_briefs": [
                    {"case_ref": "case-001", "exchange": "NYSE"},
                    {"case_ref": "case-002", "exchange": "NASDAQ"},
                ],
                "rules": {"max_case_refs_per_hypothesis": 2},
            }
        )

        self.assertEqual(result.value["exchange_screen"], ("case-001",))
        self.assertIn(
            "must satisfy the canonical visible applicability rule",
            validation_error(caller.calls[1]),
        )

    def test_signal_h2_requires_literal_profile_evidence_for_each_case(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "rankings": [
                        {
                            "hypothesis_id": "production_guidance",
                            "cases": [
                                {
                                    "case_ref": "case-001",
                                    "profile_evidence": "operates gold mines",
                                    "applicability_reason": (
                                        "A mine operator can report production guidance."
                                    ),
                                }
                            ],
                        }
                    ]
                },
                {
                    "rankings": [
                        {
                            "hypothesis_id": "production_guidance",
                            "cases": [],
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).rank_cases(
            {
                "hypotheses": [{"hypothesis_id": "production_guidance"}],
                "case_briefs": [
                    {
                        "case_ref": "case-001",
                        "business_description": "Provides aviation repair services.",
                    }
                ],
                "rules": {"max_case_refs_per_hypothesis": 2},
            }
        )

        self.assertEqual(result.value["production_guidance"], ())
        self.assertIn("exact contiguous span", validation_error(caller.calls[1]))

    def test_signal_h2_rejects_self_disqualifying_reason_with_stable_feedback(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "rankings": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "cases": [
                                {
                                    "case_ref": "case-001",
                                    "profile_evidence": "expanded service offerings",
                                    "applicability_reason": (
                                        "The profile mentions growth, but no analyst "
                                        "estimate data are provided and the evidence is "
                                        "too generic to confirm applicability."
                                    ),
                                }
                            ],
                        }
                    ]
                },
                {
                    "rankings": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "cases": [],
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).rank_cases(
            {
                "hypotheses": [{"hypothesis_id": "estimate_gap"}],
                "case_briefs": [
                    {
                        "case_ref": "case-001",
                        "business_description": "expanded service offerings",
                    }
                ],
                "rules": {"max_case_refs_per_hypothesis": 2},
            }
        )

        self.assertEqual(result.value["estimate_gap"], ())
        self.assertEqual(
            caller.calls[0]["system_prompt"], caller.calls[1]["system_prompt"]
        )
        self.assertIsNone(caller.calls[0]["payload"]["validation_feedback"])
        self.assertIn(
            "cannot disclaim applicability", validation_error(caller.calls[1])
        )
        prompt = str(caller.calls[0]["system_prompt"])
        self.assertIn("1-160 characters", prompt)
        self.assertIn("1-240 characters", prompt)
        self.assertNotIn("project-driven engineering services", prompt)

    def test_signal_h2_aggregates_inference_and_span_errors_without_echo(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "rankings": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "cases": [
                                {
                                    "case_ref": "case-001",
                                    "profile_evidence": "AI platform leadership",
                                    "applicability_reason": (
                                        "AI platform leadership suggests likely analyst "
                                        "coverage."
                                    ),
                                },
                                {
                                    "case_ref": "case-002",
                                    "profile_evidence": "analyst estimates",
                                    "applicability_reason": (
                                        "The profile lacks visible estimates and cannot "
                                        "confirm applicability."
                                    ),
                                },
                            ],
                        }
                    ]
                },
                {
                    "rankings": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "cases": [],
                        }
                    ]
                },
            ]
        )
        model = LLMSignalMiningModel(caller)
        model.set_identity_guard_aliases(("AI",))

        result = model.rank_cases(
            {
                "hypotheses": [{"hypothesis_id": "estimate_gap"}],
                "case_briefs": [
                    {
                        "case_ref": "case-001",
                        "business_description": "AI platform leadership",
                    },
                    {
                        "case_ref": "case-002",
                        "business_description": "expanded service offerings",
                    },
                ],
                "rules": {"max_case_refs_per_hypothesis": 2},
            }
        )

        self.assertEqual(result.value["estimate_gap"], ())
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["invalid_output"], {})
        error = feedback["validation_error"]
        self.assertIn("must not infer missing profile facts", error)
        self.assertIn("cannot disclaim applicability", error)
        self.assertIn("exact contiguous span", error)
        self.assertNotIn("identity alias leaked", error)

    def test_identity_guard_requires_context_for_two_character_ticker(self) -> None:
        evolution_runtime_module._scan_payload(
            {"summary": "AI platform leadership"},
            allow_outcomes=True,
            anonymous_aliases=("AI",),
        )

        for value in ("ticker AI", "$AI", "NASDAQ: AI"):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValidationError, "identity alias leaked"
            ):
                evolution_runtime_module._scan_payload(
                    {"summary": value},
                    allow_outcomes=True,
                    anonymous_aliases=("AI",),
                )

    def test_signal_h2_malformed_text_feedback_does_not_echo_raw_output(self) -> None:
        class MalformedThenValidCaller(ScriptedRoleCaller):
            def complete_json(self, **kwargs):
                self.stages.append(str(kwargs["stage"]))
                self.calls.append(dict(kwargs))
                if len(self.calls) == 1:
                    raise StructuredOutputInvalid(
                        "provider returned invalid structured output: Extra data",
                        '{"rankings":[]} Vornado Realty Trust',
                        AgentUsage(llm_calls=1, tokens=5, cost=0.01),
                    )
                return self.outputs.pop(0), AgentUsage(
                    llm_calls=1, tokens=5, cost=0.01
                )

        caller = MalformedThenValidCaller(
            [
                {
                    "rankings": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "cases": [],
                        }
                    ]
                }
            ]
        )
        model = LLMSignalMiningModel(caller)
        model.set_identity_guard_aliases(("Vornado Realty Trust",))

        result = model.rank_cases(
            {
                "hypotheses": [{"hypothesis_id": "estimate_gap"}],
                "case_briefs": [{"case_ref": "case-001"}],
                "rules": {"max_case_refs_per_hypothesis": 2},
            }
        )

        self.assertEqual(result.value["estimate_gap"], ())
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["invalid_output"], {})
        self.assertIn("Extra data", feedback["validation_error"])
        self.assertNotIn("identity alias", feedback["validation_error"])
        self.assertNotIn("Vornado", json.dumps(caller.calls[1]["payload"]))

    def test_signal_h3_repairs_missing_evidence_rejection_to_inconclusive(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "decisions": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "disposition": "rejected",
                            "rationale": [
                                "The packets do not contain analyst estimate data."
                            ],
                            "candidate": None,
                        }
                    ]
                },
                {
                    "decisions": [
                        {
                            "hypothesis_id": "estimate_gap",
                            "disposition": "inconclusive",
                            "rationale": [
                                "The packets do not contain analyst estimate data."
                            ],
                            "candidate": None,
                        }
                    ]
                },
            ]
        )

        result = LLMSignalMiningModel(caller).contrast(
            {
                "comparisons": [
                    {"hypothesis": {"hypothesis_id": "estimate_gap"}}
                ],
                "rules": {
                    "decisions": [
                        "supported",
                        "refine",
                        "rejected",
                        "inconclusive",
                    ]
                },
            }
        )

        self.assertEqual(result.value[0].disposition, "inconclusive")
        self.assertIn(
            "evidence absence must use inconclusive",
            validation_error(caller.calls[1]),
        )

    def test_signal_h1_preserves_real_structured_context_with_brand_collisions(
        self,
    ) -> None:
        output = {
            "hypotheses": [
                {
                    "hypothesis_id": "estimate_revision_dispersion",
                    "statement": "Estimate revisions may precede repricing.",
                    "applicability": "raw_info_source_type_values:news",
                    "expected_positive_pattern": (
                        "Positive cases show stronger upward revisions than controls."
                    ),
                    "source_types": ["news"],
                    "query": "analyst estimate revision",
                    "falsifiers": [
                        "Positive cases and control cases revise upward equally often."
                    ],
                    "lookback_days": 365,
                }
            ]
        }
        caller = ScriptedRoleCaller([output])
        model = LLMSignalMiningModel(caller, creative_temperature=1.0)
        model.set_identity_guard_aliases(
            (
                "OPEN",
                "Match Group",
                "News Corp",
                "Alpha Metallurgical Resources",
            )
        )
        payload = {
            "track": "hypothesis",
            "limits": {"hypothesis_limit": 3},
            "available_raw_source_types": [
                "alpha_vantage_earnings_raw_response",
                "company_facts",
                "market_data",
                "news",
                "price_history",
            ],
            "h2_applicability_contract": {
                "observed_values": {"raw_info_source_type_values": ["news"]}
            },
            "capability_backlog": {
                "status": "open",
                "signal_need_items": [
                    {
                        "status": "open",
                        "stop_reason": "no_signal_match",
                        "need": (
                            "Compare analyst estimate revisions against prior "
                            "expectations."
                        ),
                    }
                ],
            },
            "registered_deterministic_functions": ["news.negative_word_count"],
            "stable_signal_cards": [
                {
                    "signal_id": "negative_word_count",
                    "signal_ref": "negative_word_count:v1",
                    "category": "news",
                    "description": "Count negative terms in company news.",
                }
            ],
        }

        hypotheses = model.propose_hypotheses(payload)

        self.assertEqual(
            caller.calls[0]["payload"], {**payload, "validation_feedback": None}
        )
        self.assertNotIn("MASKED_COMPANY", json.dumps(caller.calls[0]["payload"]))
        self.assertEqual(hypotheses.value[0].source_types, ("news",))

    def test_signal_h1_rejects_identity_output_without_echoing_it(self) -> None:
        leaking = {
            "hypotheses": [
                {
                    "hypothesis_id": "named_issuer",
                    "statement": "Match Group shows a reusable pattern.",
                    "applicability": "Companies with estimate revisions.",
                    "expected_positive_pattern": (
                        "Positive cases show stronger upward revisions than control "
                        "cases."
                    ),
                    "source_types": ["news"],
                    "query": "estimate revision",
                    "falsifiers": ["Controls revise equally often."],
                    "lookback_days": 365,
                }
            ]
        }
        corrected = {
            "hypotheses": [
                {
                    **leaking["hypotheses"][0],
                    "hypothesis_id": "estimate_revision_gap",
                    "statement": "Upward estimate revisions may precede repricing.",
                    "applicability": "all_ready_issuers",
                    "falsifiers": [
                        "Positive cases and control cases revise upward equally often."
                    ],
                }
            ]
        }
        caller = ScriptedRoleCaller([leaking, corrected])
        model = LLMSignalMiningModel(caller)
        model.set_identity_guard_aliases(("Match Group",))

        result = model.propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "available_raw_source_types": ["news"],
            }
        )

        self.assertEqual(
            caller.stages,
            ["signal_mining_hypotheses", "signal_mining_hypotheses_correction"],
        )
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["invalid_output"], {})
        self.assertIn(
            "identity alias leaked into structured role output",
            feedback["validation_error"],
        )
        self.assertNotIn("Match Group", json.dumps(caller.calls[1]["payload"]))
        self.assertEqual(
            result.value[0].statement,
            "Upward estimate revisions may precede repricing.",
        )

    def test_signal_h2_trusts_case_local_masking_without_global_alias_rescan(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "rankings": [
                        {
                            "hypothesis_id": "operating_profile",
                            "cases": [
                                {
                                    "case_ref": "case-001",
                                    "profile_evidence": "leases commercial properties",
                                    "applicability_reason": (
                                        "The profile identifies an externally managed REIT."
                                    ),
                                },
                                {
                                    "case_ref": "case-002",
                                    "profile_evidence": "drug candidate",
                                    "applicability_reason": (
                                        "The profile identifies a clinical-stage drug developer."
                                    ),
                                },
                            ],
                        }
                    ]
                }
            ]
        )
        model = LLMSignalMiningModel(caller)
        model.set_identity_guard_aliases(
            ("Vornado Realty Trust", "VNO", "LX")
        )

        result = model.rank_cases(
            {
                "hypotheses": [{"hypothesis_id": "operating_profile"}],
                "case_briefs": [
                    {
                        "case_ref": "case-001",
                        "business_description": (
                            "The masked target is managed by Vornado Realty Trust "
                            "(NYSE: VNO) and leases commercial properties."
                        ),
                    },
                    {
                        "case_ref": "case-002",
                        "business_description": (
                            "The masked target develops the LX 9211 drug candidate."
                        ),
                    },
                ],
            }
        )

        self.assertEqual(
            result.value["operating_profile"],
            ("case-001", "case-002"),
        )
        self.assertEqual(caller.calls[0]["anonymous_aliases"], ())

    def test_plan_proposer_repairs_malformed_provider_json_once(self) -> None:
        class MalformedThenValidCaller:
            def __init__(self) -> None:
                self.stages: list[str] = []

            def complete_json(self, **kwargs):
                self.stages.append(str(kwargs["stage"]))
                if len(self.stages) == 1:
                    raise StructuredOutputInvalid(
                        "provider returned two JSON objects",
                        '{"B":{}}\n{"extra":true}',
                        AgentUsage(llm_calls=1, tokens=20, cost=0.01),
                    )
                return (
                    {
                        "B": {
                            "requests": [
                                {
                                    "request_id": "recent_news",
                                    "description": "Read recent company news.",
                                    "source_types": ["news"],
                                    "lookback_days": 180,
                                    "max_documents": 5,
                                },
                                {
                                    "request_id": "recent_market_backbone",
                                    "description": "Read recent market data.",
                                    "source_types": ["market_data"],
                                    "lookback_days": 45,
                                    "max_documents": 1,
                                }
                            ]
                        },
                        "H_init": (
                            "Form an initial source-backed hypothesis and list "
                            "unresolved information needs."
                        ),
                        "H_reflect": (
                            "Reflect over all returned Signal evidence, then continue "
                            "for the next need or finalize."
                        ),
                        "H_analyse": (
                            "Organize and weigh supporting and counter evidence while "
                            "preserving uncertainty."
                        ),
                    },
                    AgentUsage(llm_calls=1, tokens=20, cost=0.01),
                )

        caller = MalformedThenValidCaller()
        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=3,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(default_information_plan(),),
            meta_info=(),
            prior="fixed prior",
        )

        self.assertEqual(plan.plan_id, "plan_r0001_c01")
        self.assertEqual(
            caller.stages,
            ["information_plan_propose", "information_plan_propose_correction"],
        )

    def test_plan_proposer_corrects_missing_market_backbone(self) -> None:
        missing = {
            "B": {
                "requests": [
                    {
                        "request_id": "recent_news",
                        "description": "Read recent company news.",
                        "source_types": ["news"],
                        "lookback_days": 180,
                        "max_documents": 5,
                    }
                ]
            },
            "H_init": (
                "Form an initial source-backed hypothesis and list unresolved "
                "information needs."
            ),
            "H_reflect": (
                "Reflect over all returned Signal evidence, then continue for the "
                "next need or finalize."
            ),
            "H_analyse": (
                "Organize and weigh supporting and counter evidence while preserving "
                "uncertainty."
            ),
        }
        corrected = json.loads(json.dumps(missing))
        corrected["B"]["requests"].append(
            {
                "request_id": "recent_market_backbone",
                "description": "Read recent point-in-time price and volume.",
                "source_types": ["market_data"],
                "lookback_days": 45,
                "max_documents": 1,
            }
        )
        caller = ScriptedRoleCaller([missing, corrected])

        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(default_information_plan(),),
            meta_info=(),
            prior="fixed H_P",
        )

        self.assertEqual(
            plan.basic_info_policy.requests[-1].request_id,
            "recent_market_backbone",
        )
        self.assertEqual(
            [call["stage"] for call in caller.calls],
            ["information_plan_propose", "information_plan_propose_correction"],
        )
        self.assertIn("market_data", str(caller.calls[0]["system_prompt"]))

    def test_v91_plan_proposer_confines_query_correction_scope(self) -> None:
        invalid = {
            "B": {
                "requests": [
                    {
                        "request_id": "recent_company_news",
                        "description": "Read recent target-company news.",
                        "source_types": ["news"],
                        "lookback_days": 180,
                        "max_documents": 5,
                    },
                    {
                        "request_id": "recent_market_backbone",
                        "description": "Read recent point-in-time price and volume.",
                        "source_types": ["market_data"],
                        "lookback_days": 45,
                        "max_documents": 1,
                        "query": 7,
                    },
                ]
            },
            "H_init": (
                "Form a source-backed commercialization hypothesis and list "
                "unresolved information needs."
            ),
            "H_reflect": (
                "Update beliefs from all Signal evidence, then continue for the "
                "next need or finalize."
            ),
            "H_analyse": (
                "Organize and weigh supporting and counter evidence while exposing "
                "uncertainty."
            ),
        }
        minimally_corrected = json.loads(json.dumps(invalid))
        minimally_corrected["B"]["requests"][1]["query"] = "price volume"
        drifted = json.loads(json.dumps(minimally_corrected))
        drifted["H_init"] += " Compare management strategy with market signals."

        with self.assertRaisesRegex(
            CandidateProposalRejected,
            "correction changed unrelated valid content",
        ):
            LLMInformationPlanProposer(
                ScriptedRoleCaller([invalid, drifted])
            ).propose(
                round_id=1,
                candidate_index=1,
                candidate_count=1,
                proposal_attempt=1,
                forbidden_plan_ids=(),
                parents=(default_information_plan(),),
                meta_info=(),
                prior="fixed H_P",
            )

        deleted_request = json.loads(json.dumps(invalid))
        deleted_request["B"]["requests"].pop(1)
        with self.assertRaisesRegex(
            CandidateProposalRejected,
            "correction changed unrelated valid content",
        ):
            LLMInformationPlanProposer(
                ScriptedRoleCaller([invalid, deleted_request])
            ).propose(
                round_id=1,
                candidate_index=1,
                candidate_count=1,
                proposal_attempt=1,
                forbidden_plan_ids=(),
                parents=(default_information_plan(),),
                meta_info=(),
                prior="fixed H_P",
            )

        caller = ScriptedRoleCaller([invalid, minimally_corrected])
        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(default_information_plan(),),
            meta_info=(),
            prior="fixed H_P",
        )

        self.assertEqual(plan.basic_info_policy.requests[1].query, "price volume")
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(
            feedback["obligations"][0]["must_change_paths"],
            ["B.requests[1].query"],
        )
        self.assertIn("preserve every unmentioned", caller.calls[0]["system_prompt"])

    def test_v91_plan_proposer_omits_empty_optional_query_without_call(self) -> None:
        output = {
            "B": {
                "requests": [
                    {
                        "request_id": "recent_market_backbone",
                        "description": "Read recent point-in-time price and volume.",
                        "source_types": ["market_data"],
                        "lookback_days": 45,
                        "max_documents": 1,
                        "query": "",
                    }
                ]
            },
            "H_init": (
                "Form a source-backed commercialization hypothesis and list "
                "unresolved information needs."
            ),
            "H_reflect": (
                "Update beliefs from all Signal evidence, then continue for the "
                "next need or finalize."
            ),
            "H_analyse": (
                "Organize and weigh supporting and counter evidence while exposing "
                "uncertainty."
            ),
        }
        caller = ScriptedRoleCaller([output])

        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(default_information_plan(),),
            meta_info=(),
            prior="fixed H_P",
        )

        self.assertIsNone(plan.basic_info_policy.requests[0].query)
        self.assertEqual(caller.stages, ["information_plan_propose"])

    def test_v81_plan_proposer_corrects_cross_issuer_request_scope(self) -> None:
        invalid = {
            "B": {
                "requests": [
                    {
                        "request_id": "recent_company_news",
                        "description": "Read recent company news.",
                        "source_types": ["news"],
                        "lookback_days": 180,
                        "max_documents": 5,
                    },
                    {
                        "request_id": "recent_market_backbone",
                        "description": "Read recent market data.",
                        "source_types": ["market_data"],
                        "lookback_days": 45,
                        "max_documents": 1,
                    },
                    {
                        "request_id": "competitor_actions",
                        "description": (
                            "Competitor actions that could affect the company's "
                            "market position."
                        ),
                        "source_types": ["news"],
                        "lookback_days": 180,
                        "query": "competitor product launch market share",
                        "max_documents": 3,
                    },
                ]
            },
            "H_init": (
                "Form an initial source-backed hypothesis and list unresolved "
                "information needs."
            ),
            "H_reflect": (
                "Reflect over all returned Signal evidence, then continue for the "
                "next need or finalize."
            ),
            "H_analyse": (
                "Organize and weigh supporting and counter evidence while preserving "
                "uncertainty."
            ),
        }
        corrected = json.loads(json.dumps(invalid))
        corrected_request = corrected["B"]["requests"][2]
        corrected_request["description"] = (
            "Read the target issuer's own disclosures about competitive position."
        )
        corrected_request["query"] = "competitive position"
        caller = ScriptedRoleCaller([invalid, corrected])

        plan = LLMInformationPlanProposer(caller).propose(
            round_id=1,
            candidate_index=1,
            candidate_count=1,
            proposal_attempt=1,
            forbidden_plan_ids=(),
            parents=(default_information_plan(),),
            meta_info=(),
            prior="fixed H_P",
        )

        error = caller.calls[1]["payload"]["validation_feedback"][
            "validation_error"
        ]
        self.assertIn("B.requests[2].description", error)
        self.assertIn("B.requests[2].query", error)
        self.assertIn("target-company-scoped Basic Info resolver", error)
        self.assertIn("target company_id", caller.calls[0]["system_prompt"])
        self.assertEqual(
            plan.basic_info_policy.requests[2].description,
            corrected_request["description"],
        )

    def test_plan_skill_validation_rejects_generic_placeholder(self) -> None:
        plan = default_information_plan()
        placeholder = InformationPlan(
            plan_id="placeholder_plan",
            parent_ids=(),
            basic_info_policy=plan.basic_info_policy,
            initial_research_skill="Complete initialization instructions.",
            reflection_skill=plan.reflection_skill,
            analysis_prompt=plan.analysis_prompt,
        )

        with self.assertRaisesRegex(ValidationError, "generic placeholder"):
            evolution_runtime_module._validate_proposed_plan_skills(placeholder)

    def test_default_information_plan_has_compact_market_backbone(self) -> None:
        plan = default_information_plan()
        request = plan.basic_info_policy.requests[-1]

        self.assertEqual(request.source_types, ("market_data",))
        self.assertEqual(request.lookback_days, 45)
        self.assertEqual(request.max_documents, 1)
        model_catalog = set(
            evolution_runtime_module._model_available_source_types(
                ("filing", "financials", "market_data", "news")
            )
        )
        self.assertTrue(
            {
                source_type
                for item in plan.basic_info_policy.requests
                for source_type in item.source_types
            }.issubset(model_catalog)
        )
        self.assertIn("10-k", model_catalog)
        self.assertIn("sec_company_facts", model_catalog)
        self.assertNotIn("earnings_call", model_catalog)

    def test_signal_update_role_returns_one_exact_semantic_decision(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "signal_ref": "revenue_growth_yoy:v1",
                    "disposition": "defer",
                    "problem_type": "routing_applicability_unclear",
                    "rationale": ["The evidence does not isolate a Signal defect."],
                    "candidate": None,
                }
            ]
        )
        model = LLMSignalUpdateModel(caller)

        step = model.update(
            {
                "target": {"signal_ref": "revenue_growth_yoy:v1"},
                "induction_cases": [],
                "candidate_contract": {},
            }
        )

        self.assertEqual(step.value.disposition, "defer")
        system_prompt = str(caller.calls[0]["system_prompt"])
        self.assertIn("routing/applicability mistake", system_prompt)
        self.assertIn('"no_change"', system_prompt)

    def test_signal_mining_roles_parse_hypotheses_and_rank_only_allowed_refs(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "hypotheses": [
                        {
                            "hypothesis_id": "order_confirmation",
                            "statement": "Confirmed orders precede repricing.",
                            "applicability": "all_ready_issuers",
                            "expected_positive_pattern": (
                                "Positive cases confirm more orders than control cases."
                            ),
                            "source_types": ["filings"],
                            "query": "material order",
                            "falsifiers": [
                                "Positive cases and control cases confirm orders "
                                "equally often."
                            ],
                            "lookback_days": 365,
                        }
                    ]
                },
                {
                    "hypotheses": [
                        {
                            "hypothesis_id": "order_confirmation",
                            "statement": "Confirmed orders precede repricing.",
                            "applicability": "all_ready_issuers",
                            "expected_positive_pattern": (
                                "Positive cases confirm more orders than control cases."
                            ),
                            "source_types": ["filing"],
                            "query": "material order",
                            "falsifiers": [
                                "Positive cases and control cases confirm orders "
                                "equally often."
                            ],
                            "lookback_days": 365,
                        }
                    ]
                },
                {
                    "rankings": [
                        {
                            "hypothesis_id": "order_confirmation",
                            "cases": [
                                {
                                    "case_ref": "case-002",
                                    "profile_evidence": "project-driven hardware",
                                    "applicability_reason": (
                                        "The profile directly identifies project-driven "
                                        "operations."
                                    ),
                                },
                                {
                                    "case_ref": "case-001",
                                    "profile_evidence": "project-driven hardware",
                                    "applicability_reason": (
                                        "The profile directly identifies project-driven "
                                        "operations."
                                    ),
                                },
                            ],
                        }
                    ]
                },
            ]
        )
        model = LLMSignalMiningModel(caller, creative_temperature=1.0)

        hypotheses = model.propose_hypotheses(
            {
                "limits": {"hypothesis_limit": 3},
                "meta_info": [],
                "available_raw_source_types": ["news", "filing"],
            }
        )
        rankings = model.rank_cases(
            {
                "hypotheses": [item.to_dict() for item in hypotheses.value],
                "case_briefs": [
                    {"case_ref": "case-001", "industry": "project-driven hardware"},
                    {"case_ref": "case-002", "industry": "project-driven hardware"},
                ],
            }
        )

        self.assertEqual(hypotheses.value[0].hypothesis_id, "order_confirmation")
        self.assertEqual(
            rankings.value["order_confirmation"],
            ("case-002", "case-001"),
        )
        self.assertEqual(
            caller.stages,
            [
                "signal_mining_hypotheses",
                "signal_mining_hypotheses_correction",
                "signal_mining_case_ranking",
            ],
        )
        self.assertEqual(caller.calls[0]["temperature"], 1.0)
        self.assertEqual(caller.calls[1]["temperature"], 1.0)
        self.assertNotIn("large_order_confirmation", caller.calls[0]["system_prompt"])
        self.assertNotIn(
            "material order contract customer award",
            caller.calls[0]["system_prompt"],
        )
        self.assertIn(
            "validation_error", caller.calls[1]["payload"]["validation_feedback"]
        )
        self.assertEqual(caller.calls[2]["temperature"], 0.0)
        self.assertFalse(caller.calls[2]["allow_outcomes"])

    def test_signal_update_role_repairs_wrong_target_once(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "signal_ref": "other_signal:v1",
                    "disposition": "no_change",
                    "problem_type": "routing",
                    "rationale": ["No definition change is justified."],
                    "candidate": None,
                },
                {
                    "signal_ref": "price_momentum_126d:v1",
                    "disposition": "no_change",
                    "problem_type": "routing",
                    "rationale": ["The observed issue belongs to Plan routing."],
                    "candidate": None,
                },
            ]
        )

        step = LLMSignalUpdateModel(caller).update(
            {
                "target": {"signal_ref": "price_momentum_126d:v1"},
                "induction_cases": [],
                "candidate_contract": {},
            }
        )

        self.assertEqual(step.value.signal_ref, "price_momentum_126d:v1")
        self.assertEqual(step.usage.llm_calls, 2)
        self.assertEqual(
            caller.stages,
            ["signal_update_decision", "signal_update_decision_correction"],
        )
        self.assertIn("validation_error", caller.calls[1]["payload"])
        self.assertEqual(
            caller.calls[1]["payload"]["validation_contract"],
            "structured-validation-v1",
        )
        self.assertEqual(
            caller.calls[1]["payload"]["obligations"][0]["must_change_paths"],
            ["signal_ref"],
        )
        self.assertEqual(
            step.value.rationale,
            ("No definition change is justified.",),
        )

    def test_signal_update_corrects_canned_rationale_using_supplied_case_refs(self) -> None:
        canned = {
            "signal_ref": "financing_listing_action:v1",
            "disposition": "defer",
            "problem_type": "routing_applicability_unclear",
            "rationale": ["Induction evidence does not isolate a Signal defect."],
            "candidate": None,
        }
        grounded = {
            **canned,
            "rationale": [
                "update-case-001 lacks a disclosed transaction, whereas "
                "update-case-002 supplies a completed financing. Neither packet "
                "shows extraction of an available transaction failing."
            ],
        }
        caller = ScriptedRoleCaller([canned, grounded])
        payload = {
            "target": {"signal_ref": canned["signal_ref"]},
            "induction_cases": [
                {"case_ref": "update-case-001"},
                {"case_ref": "update-case-002"},
            ],
        }

        step = LLMSignalUpdateModel(caller).update(payload)

        self.assertEqual(step.value.rationale, tuple(grounded["rationale"]))
        self.assertEqual(step.usage.llm_calls, 2)
        self.assertIn("missing case_refs", caller.calls[1]["payload"]["validation_error"])
        self.assertNotIn(canned["rationale"][0], caller.calls[0]["system_prompt"])
        self.assertIn("do not substitute a generic decision", caller.calls[0]["system_prompt"])

    def test_signal_update_case_ref_traceability_applies_to_no_change(self) -> None:
        invalid = {
            "signal_ref": "financing_listing_action:v1",
            "disposition": "no_change",
            "problem_type": "routing",
            "rationale": ["update-case-001-extra is missing evidence."],
            "candidate": None,
        }
        valid = {**invalid, "rationale": ["update-case-001 lacks the required evidence."]}
        caller = ScriptedRoleCaller([invalid, valid])

        step = LLMSignalUpdateModel(caller).update({
            "target": {"signal_ref": invalid["signal_ref"]},
            "induction_cases": [{"case_ref": "update-case-001"}],
        })

        self.assertEqual(step.value.disposition, "no_change")
        self.assertEqual(step.usage.llm_calls, 2)

    def test_routing_rejects_duplicate_refs_and_preserves_valid_siblings(
        self,
    ) -> None:
        guidance = signal_selection("guidance_acceleration:v1")["selections"][0]
        guidance.update(
            {
                "reason_code": "combine_evidence",
                "target_need_indices": [],
                "answer_scope": None,
                "residual_need": None,
            }
        )
        duplicate = json.loads(json.dumps(guidance))
        negative = signal_selection("negative_word_count:v1")["selections"][0]
        negative.update(
            {
                "reason_code": "combine_evidence",
                "target_need_indices": [],
                "answer_scope": None,
                "residual_need": None,
            }
        )
        financing = signal_selection("financing_listing_action:v1")["selections"][0]
        financing.update(
            {
                "reason_code": "combine_evidence",
                "target_need_indices": [],
                "answer_scope": None,
                "residual_need": None,
            }
        )
        drifted_guidance = json.loads(json.dumps(guidance))
        drifted_guidance["selection_reason"] = "Rewritten valid sibling."
        drifted_negative = json.loads(json.dumps(negative))
        drifted_negative["selection_reason"] = "Another rewritten valid sibling."
        caller = ScriptedRoleCaller(
            [
                {"selections": [guidance, duplicate, negative]},
                {"selections": [drifted_guidance, financing, drifted_negative]},
            ]
        )

        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(PROJECT_ROOT / "configs/signals_v1.json")
            result = LLMSignalRetrievalAgent(caller).select(
                ("What source-backed context is available?",),
                registry.freeze(),
                {},
            )

        self.assertEqual(
            tuple(item.signal_ref for item in result.value),
            (
                "guidance_acceleration:v1",
                "financing_listing_action:v1",
                "negative_word_count:v1",
            ),
        )
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["required_change_paths"], ["selections[1]"])
        self.assertEqual(result.value[0].selection_reason, guidance["selection_reason"])
        self.assertEqual(result.value[2].selection_reason, negative["selection_reason"])
        self.assertEqual(feedback["validation_contract"], "structured-validation-v1")
        self.assertIn("duplicates", feedback["validation_error"])

    def test_h3_only_unmatched_comparator_context_forces_inconclusive(self) -> None:
        rejected = {
            "decisions": [
                {
                    "hypothesis_id": "guidance_change",
                    "disposition": "rejected",
                    "rationale": ["The groups directly contradict the hypothesis."],
                    "candidate": None,
                }
            ]
        }
        inconclusive = {
            "decisions": [
                {
                    "hypothesis_id": "guidance_change",
                    "disposition": "inconclusive",
                    "rationale": [
                        "The visible comparator packets are semantically insufficient."
                    ],
                    "candidate": None,
                }
            ]
        }
        caller = ScriptedRoleCaller([rejected, inconclusive])
        model = LLMSignalMiningModel(caller)

        step = model.contrast(
            {
                "evidence_packets": [
                    {
                        "packet_ref": ref,
                        "query_match_status": "unmatched_comparator_context",
                    }
                    for ref in ("packet-a", "packet-b")
                ],
                "comparisons": [
                    {
                        "hypothesis": {"hypothesis_id": "guidance_change"},
                        "evidence_packet_refs": ["packet-a", "packet-b"],
                    }
                ],
            }
        )

        self.assertEqual(step.value[0].disposition, "inconclusive")
        self.assertEqual(step.usage.llm_calls, 2)
        self.assertIn(
            "without query-matched positive and control evidence",
            caller.calls[1]["payload"]["validation_error"],
        )

    def test_h3_one_unmatched_group_forces_inconclusive(self) -> None:
        supported = {
            "decisions": [
                {
                    "hypothesis_id": "guidance_change",
                    "disposition": "supported",
                    "rationale": ["Positive cases contain the queried disclosure."],
                    "candidate": None,
                }
            ]
        }
        inconclusive = {
            "decisions": [
                {
                    "hypothesis_id": "guidance_change",
                    "disposition": "inconclusive",
                    "rationale": ["The control evidence does not directly test the query."],
                    "candidate": None,
                }
            ]
        }
        caller = ScriptedRoleCaller([supported, inconclusive])

        step = LLMSignalMiningModel(caller).contrast(
            {
                "evidence_packets": [
                    {
                        "packet_ref": "packet-positive",
                        "label": "positive",
                        "query_match_status": "matched",
                    },
                    {
                        "packet_ref": "packet-control",
                        "label": "control",
                        "query_match_status": "unmatched_comparator_context",
                    },
                ],
                "comparisons": [
                    {
                        "hypothesis": {"hypothesis_id": "guidance_change"},
                        "evidence_packet_refs": [
                            "packet-positive",
                            "packet-control",
                        ],
                    }
                ],
            }
        )

        self.assertEqual(step.value[0].disposition, "inconclusive")
        self.assertEqual(step.usage.llm_calls, 2)

    def test_exploration_e1_corrects_a_nonliteral_observation(self) -> None:
        invalid = {
            "signatures": [
                {
                    "case_ref": "case-001",
                    "observations": [
                        {
                            "summary": "Revenue guidance increased.",
                            "document_ref": "document-01",
                            "exact_span": "Management raised revenue guidance.",
                        }
                    ],
                    "evidence_gaps": [],
                }
            ]
        }
        valid = json.loads(json.dumps(invalid))
        valid["signatures"][0]["observations"][0]["exact_span"] = (
            "Management reaffirmed revenue guidance."
        )
        caller = ScriptedRoleCaller([invalid, valid])

        step = LLMSignalMiningModel(caller).extract_exploration(
            {
                "cases": [
                    {
                        "case_ref": "case-001",
                        "evidence": [
                            {
                                "document_ref": "document-01",
                                "content_excerpt": (
                                    "Management reaffirmed revenue guidance."
                                ),
                            }
                        ],
                    }
                ]
            }
        )

        self.assertEqual(step.usage.llm_calls, 2)
        self.assertEqual(
            step.value[0].observations[0].exact_span,
            "Management reaffirmed revenue guidance.",
        )
        self.assertIn(
            "not a supplied literal",
            caller.calls[1]["payload"]["validation_feedback"]["validation_error"],
        )

    def test_exploration_e1_empty_packet_records_gap_without_invention(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "signatures": [
                        {
                            "case_ref": "case-001",
                            "observations": [],
                            "evidence_gaps": ["No point-in-time excerpt was supplied."],
                        }
                    ]
                }
            ]
        )

        step = LLMSignalMiningModel(caller).extract_exploration(
            {"cases": [{"case_ref": "case-001", "evidence": []}]}
        )

        self.assertEqual(step.usage.llm_calls, 1)
        self.assertEqual(step.value[0].observations, ())
        self.assertTrue(step.value[0].evidence_gaps)

    def test_exploration_e1_repairs_one_reordered_row_and_preserves_sibling(
        self,
    ) -> None:
        first = {
            "case_ref": "case-001",
            "observations": [
                {
                    "summary": "Management reaffirmed guidance.",
                    "document_ref": "document-01",
                    "exact_span": "Management reaffirmed revenue guidance.",
                }
            ],
            "evidence_gaps": [],
        }
        invalid_second = {
            "case_ref": "case-002",
            "observations": [
                {
                    "summary": "A customer order was disclosed.",
                    "document_ref": "document-01",
                    "exact_span": "A fabricated customer order was disclosed.",
                }
            ],
            "evidence_gaps": [],
        }
        repaired_second = json.loads(json.dumps(invalid_second))
        repaired_second["observations"][0]["exact_span"] = (
            "A binding customer order was disclosed."
        )
        drifted_first = json.loads(json.dumps(first))
        drifted_first["observations"][0]["summary"] = "Unrelated rewritten summary."
        caller = ScriptedRoleCaller(
            [
                {"signatures": [first, invalid_second]},
                {"signatures": [repaired_second, drifted_first]},
            ]
        )

        step = LLMSignalMiningModel(caller).extract_exploration(
            {
                "cases": [
                    {
                        "case_ref": "case-001",
                        "evidence": [
                            {
                                "document_ref": "document-01",
                                "content_excerpt": (
                                    "Management reaffirmed revenue guidance."
                                ),
                            }
                        ],
                    },
                    {
                        "case_ref": "case-002",
                        "evidence": [
                            {
                                "document_ref": "document-01",
                                "content_excerpt": (
                                    "A binding customer order was disclosed."
                                ),
                            }
                        ],
                    },
                ]
            }
        )

        self.assertEqual(
            [item.case_ref for item in step.value], ["case-001", "case-002"]
        )
        self.assertEqual(
            step.value[0].observations[0].summary,
            "Management reaffirmed guidance.",
        )
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(
            feedback["validation_contract"], "structured-validation-v1"
        )
        self.assertEqual(feedback["obligations"][0]["item_id"], "case-002")

    def test_exploration_e2_treats_exact_spans_as_authoritative(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "decisions": [
                        {
                            "hypothesis_id": "exploration-pattern",
                            "disposition": "refine",
                            "rationale": ["The literal pattern needs more cases."],
                            "candidate": None,
                        }
                    ]
                }
            ]
        )

        LLMSignalMiningModel(caller).discover_exploration(
            {
                "signatures": [
                    {
                        "case_ref": "case-001",
                        "observations": [
                            {
                                "summary": "An overstated interpretation.",
                                "document_ref": "document-01",
                                "exact_span": "Management reaffirmed prior guidance.",
                            }
                        ],
                        "evidence_gaps": [],
                        "label": "positive",
                    }
                ]
            }
        )

        self.assertIn(
            "Treat each exact_span as authoritative",
            caller.calls[0]["system_prompt"],
        )
        self.assertIn(
            "ignore any stronger or different claim",
            caller.calls[0]["system_prompt"],
        )

    def test_slow_output_contracts_do_not_supply_populated_answers(self) -> None:
        contracts = (
            evolution_runtime_module._SIGNAL_MINING_DECISIONS_OUTPUT,
            evolution_runtime_module._SIGNAL_MINING_SIGNATURES_OUTPUT,
            evolution_runtime_module._SIGNAL_UPDATE_OUTPUT,
        )
        for contract in contracts:
            with self.subTest(contract=contract):
                self.assertNotIn("example", contract.casefold())
                self.assertNotIn("large_order_confirmation", contract)
                self.assertNotIn("case-001", contract)
                self.assertNotIn("Induction evidence does not isolate", contract)
                self.assertNotIn("An expectation-changing event", contract)
