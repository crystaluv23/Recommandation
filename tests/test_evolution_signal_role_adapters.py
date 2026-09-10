"""Signal Mining, Update, and exploration role-adapter tests."""

from tests.evolution_runtime_test_support import *  # noqa: F403
from stock_opportunity_agent.research import (
    evolution_core as core_module,
    evolution_signal_roles as signal_roles_module,
)


class SignalRoleAdapterTests(TestCase):
    def test_strict_aggregate_aliases_preserve_words_and_reuse_matchers(self) -> None:
        aliases = ("Future Holdings", "Business Systems", "Z", "Q2")
        text = "Future business plans target Gen Z in Q2. Future Holdings disclosed them."
        masked = core_module._mask_identity_values(text, aliases, expand_aliases=False)
        self.assertEqual(
            masked,
            "Future business plans target Gen Z in Q2. [MASKED_COMPANY] disclosed them.",
        )
        core_module._assert_identity_values_masked(masked, aliases, expand_aliases=False)
        evolution_runtime_module._scan_payload(
            masked, allow_outcomes=True, anonymous_aliases=aliases,
        )
        first = core_module._compiled_identity_aliases(aliases, expand_aliases=False)
        self.assertIs(
            first, core_module._compiled_identity_aliases(aliases, expand_aliases=False),
        )
        local = core_module._mask_identity_values("Future announced results.", aliases)
        self.assertIn("[MASKED_COMPANY]", local)

    def test_signal_h1_v2_accepts_structured_no_hypothesis_with_open_demand(
        self,
    ) -> None:
        response = {
            "conclusion": "no_testable_hypothesis",
            "hypotheses": [],
            "no_hypothesis": {
                "reason_code": "insufficient_retrieval_basis",
                "rationale": [
                    "Available source types do not expose the requested measurement."
                ],
                "need_refs": ["need-001"],
            },
        }
        caller = ScriptedRoleCaller([response])

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "h1_contract_version": "signal-mining-hypothesis-v2",
                "hypothesis_slots": ["h1-c0001-s01"],
                "limits": {
                    "hypothesis_limit": 1,
                    "evidence_lookback_days": 365,
                },
                "available_raw_source_types": ["news"],
                "capability_backlog": {
                    "signal_need_items": [
                        {"need_ref": "need-001", "need": "Estimate changes"}
                    ]
                },
            }
        )

        self.assertEqual(result.value, ())
        self.assertEqual(result.metadata["conclusion"], "no_testable_hypothesis")
        self.assertEqual(result.metadata["reason_code"], "insufficient_retrieval_basis")
        self.assertEqual(caller.stages, ["signal_mining_hypotheses"])

    def test_signal_h1_v2_uses_runtime_identity_and_structured_measurement(
        self,
    ) -> None:
        caller = ScriptedRoleCaller(
            [
                {
                    "conclusion": "hypotheses",
                    "hypotheses": [
                        {
                            "proposal_ref": "h1-c0007-s01",
                            "measurement": {
                                "observable": "Customer commitments converted to revenue",
                                "value_kind": "numeric",
                                "normalization": "ratio to opening backlog",
                            },
                            "applicability": {
                                "rule": "all_ready_issuers",
                                "values": [],
                            },
                            "expected_direction": "higher_in_positive",
                            "retrieval_intent": {
                                "source_types": ["10-q"],
                                "query": "contract awards backlog conversion",
                            },
                            "falsifiers": [
                                {
                                    "condition": "The measurement is extracted.",
                                    "expected_observation": (
                                        "The fixed groups overlap or reverse direction."
                                    ),
                                }
                            ],
                            "need_refs": [],
                        }
                    ],
                    "no_hypothesis": None,
                }
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "h1_contract_version": "signal-mining-hypothesis-v2",
                "hypothesis_slots": ["h1-c0007-s01"],
                "limits": {
                    "hypothesis_limit": 1,
                    "evidence_lookback_days": 540,
                },
                "available_raw_source_types": ["10-q"],
            }
        )

        hypothesis = result.value[0]
        self.assertEqual(hypothesis.hypothesis_id, "h1-c0007-s01")
        self.assertEqual(hypothesis.lookback_days, 540)
        self.assertEqual(hypothesis.expected_direction, "higher_in_positive")
        self.assertEqual(hypothesis.measurement["value_kind"], "numeric")
        self.assertNotIn("h1-c0007-s01", hypothesis.query)

    def test_signal_h1_v2_correction_preserves_valid_sibling_by_runtime_id(
        self,
    ) -> None:
        invalid_item = {
            "proposal_ref": "h1-c0008-s01",
            "measurement": {
                "observable": "New customer commitments",
                "value_kind": "numeric",
                "normalization": "ratio to opening backlog",
            },
            "applicability": {"rule": "all_ready_issuers", "values": []},
            "expected_direction": "higher_in_positive",
            "retrieval_intent": {
                "source_types": ["unavailable-source"],
                "query": "new customer commitments",
            },
            "falsifiers": [
                {
                    "condition": "The measurement is extracted.",
                    "expected_observation": "The fixed groups overlap.",
                }
            ],
            "need_refs": [],
        }
        valid_item = {
            "proposal_ref": "h1-c0008-s02",
            "measurement": {
                "observable": "Backlog converted to recognized revenue",
                "value_kind": "numeric",
                "normalization": "ratio to opening backlog",
            },
            "applicability": {"rule": "all_ready_issuers", "values": []},
            "expected_direction": "higher_in_positive",
            "retrieval_intent": {
                "source_types": ["10-q"],
                "query": "backlog revenue conversion",
            },
            "falsifiers": [
                {
                    "condition": "The measurement is extracted.",
                    "expected_observation": "The fixed groups overlap.",
                }
            ],
            "need_refs": [],
        }
        corrected_item = {
            **invalid_item,
            "retrieval_intent": {
                "source_types": ["10-q"],
                "query": "new customer commitments",
            },
        }
        drifted_valid_item = {
            **valid_item,
            "expected_direction": "lower_in_positive",
        }
        caller = ScriptedRoleCaller(
            [
                {
                    "conclusion": "hypotheses",
                    "hypotheses": [invalid_item, valid_item],
                    "no_hypothesis": None,
                },
                {
                    "conclusion": "hypotheses",
                    "hypotheses": [drifted_valid_item, corrected_item],
                    "no_hypothesis": None,
                },
            ]
        )

        result = LLMSignalMiningModel(caller).propose_hypotheses(
            {
                "h1_contract_version": "signal-mining-hypothesis-v2",
                "hypothesis_slots": ["h1-c0008-s01", "h1-c0008-s02"],
                "limits": {"hypothesis_limit": 2, "evidence_lookback_days": 365},
                "available_raw_source_types": ["10-q"],
            }
        )

        by_ref = {item.hypothesis_id: item for item in result.value}
        self.assertEqual(result.usage.llm_calls, 2)
        self.assertEqual(
            by_ref["h1-c0008-s01"].source_types,
            ("10-q",),
        )
        self.assertEqual(
            by_ref["h1-c0008-s02"].expected_direction,
            valid_item["expected_direction"],
        )
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertEqual(feedback["obligations"][0]["item_id"], "h1-c0008-s01")

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

    def test_short_ticker_masking_and_guard_preserve_ordinary_research_text(self) -> None:
        aliases = ("Z", "Q2", "AI", "Q2 Holdings")
        ordinary = {"summary": "Gen Z engagement and Q2 revenue from AI services."}
        masked = core_module._mask_identity_values(ordinary, aliases)
        self.assertEqual(masked, ordinary)
        evolution_runtime_module._scan_payload(
            masked, allow_outcomes=True, anonymous_aliases=aliases,
        )
        url = "https://example.com/quote/Z"
        with self.assertRaises(ValidationError):
            core_module._assert_identity_values_masked(url, aliases)
        masked_url = core_module._mask_identity_values(url, aliases)
        self.assertIn("[MASKED_COMPANY]", masked_url)
        core_module._assert_identity_values_masked(masked_url, aliases)
        for text in ("$Z", "ticker Z", "NYSE: Z", "$Q2", "symbol AI", "Q2 Holdings"):
            with self.subTest(text=text):
                with self.assertRaises(ValidationError):
                    evolution_runtime_module._scan_payload(
                        text, allow_outcomes=True, anonymous_aliases=aliases,
                    )
                masked = core_module._mask_identity_values(text, aliases)
                self.assertIn("[MASKED_COMPANY]", masked)
                evolution_runtime_module._scan_payload(
                    masked, allow_outcomes=True, anonymous_aliases=aliases,
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
                "evidence_packets": [
                    {
                        "packet_ref": "packet-positive",
                        "label": "positive",
                        "query_match_status": "matched",
                    },
                    {
                        "packet_ref": "packet-control",
                        "label": "control",
                        "query_match_status": "matched",
                    },
                ],
                "comparisons": [
                    {
                        "hypothesis": {"hypothesis_id": "estimate_gap"},
                        "evidence_packet_refs": [
                            "packet-positive",
                            "packet-control",
                        ],
                    }
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
        self.assertEqual(
            result.value[0].sample_basis,
            {
                "positive_refs": ("packet-positive",),
                "control_refs": ("packet-control",),
            },
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
            "Read target-company-scoped news about competitive position."
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

    def test_signal_update_v2_rejects_label_as_fact_and_keeps_source_verdict_first(
        self,
    ) -> None:
        base = {
            "signal_ref": "financing_listing_action:v1",
            "disposition": "defer",
            "problem_type": "routing_applicability_unclear",
            "rationale": ["The source verdict is insufficient for update-case-001."],
            "candidate": None,
        }
        invalid = {
            **base,
            "case_diagnostics": [
                {
                    "case_ref": "update-case-001",
                    "evidence_verdict": "supported",
                    "facts": [
                        {
                            "claim": "The positive label proves financing occurred.",
                            "document_ref": "document-01",
                            "exact_span": "positive label",
                        }
                    ],
                    "evidence_gaps": [],
                    "outcome_relation": "aligned",
                    "outcome_explanation": "The supplied label is positive.",
                }
            ],
        }
        corrected = {
            **base,
            "case_diagnostics": [
                {
                    "case_ref": "update-case-001",
                    "evidence_verdict": "insufficient",
                    "facts": [],
                    "evidence_gaps": ["No transaction terms are visible."],
                    "outcome_relation": "not_assessable",
                    "outcome_explanation": (
                        "The outcome cannot establish a missing source fact."
                    ),
                }
            ],
        }
        caller = ScriptedRoleCaller([invalid, corrected])
        payload = {
            "update_contract_version": "signal-update-decision-v2",
            "target": {"signal_ref": base["signal_ref"]},
            "induction_cases": [
                {
                    "case_ref": "update-case-001",
                    "evidence_observation": {
                        "evidence": [
                            {
                                "document_ref": "document-01",
                                "content_excerpt": (
                                    "The issuer discussed general corporate liquidity."
                                ),
                            }
                        ]
                    },
                    "outcome_relation": {
                        "label": "positive",
                        "current_signal_relation": "not_assessable",
                    },
                }
            ],
        }

        result = LLMSignalUpdateModel(caller).update(payload)

        self.assertEqual(result.value.case_diagnostics, tuple(corrected["case_diagnostics"]))
        self.assertEqual(result.usage.llm_calls, 2)
        self.assertIn("source-cited literal facts", validation_error(caller.calls[1]))
        self.assertIn("label cannot establish", caller.calls[0]["system_prompt"])

    def test_signal_update_preserves_long_source_literals_without_correction(self) -> None:
        literal = "Management reaffirmed the disclosed annual outlook. " * 20
        output = {
            "signal_ref": "guidance_acceleration:v1",
            "disposition": "defer",
            "problem_type": "insufficient_evidence",
            "rationale": ["A reaffirmation alone does not show acceleration."],
            "candidate": None,
            "case_diagnostics": [{
                "case_ref": "update-case-001",
                "evidence_verdict": "insufficient",
                "facts": [{"document_ref": "document-01", "exact_span": literal}],
                "evidence_gaps": ["No comparable prior outlook is supplied."],
                "outcome_relation": "not_assessable",
                "outcome_explanation": "No directional result is available.",
            }],
        }
        caller = ScriptedRoleCaller([output])
        payload = {
            "target": {"signal_ref": output["signal_ref"]},
            "induction_cases": [{
                "case_ref": "update-case-001",
                "evidence_observation": {"executed_evidence": [{
                    "document_ref": "document-01", "exact_span": literal,
                }]},
                "outcome_relation": {"current_signal_relation": "not_assessable"},
            }],
        }

        result = LLMSignalUpdateModel(caller).update(payload)

        self.assertEqual(result.value.case_diagnostics, tuple(output["case_diagnostics"]))
        self.assertEqual(result.usage.llm_calls, 1)

    def test_signal_update_v2_adds_missing_case_without_rewriting_valid_sibling(
        self,
    ) -> None:
        base = {
            "signal_ref": "guidance_acceleration:v1",
            "disposition": "defer",
            "problem_type": "insufficient_case_evidence",
            "rationale": ["Both cases require source-grounded observations."],
            "candidate": None,
        }
        valid_first = {
            "case_ref": "update-case-001",
            "evidence_verdict": "insufficient",
            "facts": [],
            "evidence_gaps": ["No guidance statement is visible."],
            "outcome_relation": "not_assessable",
            "outcome_explanation": "No source fact can be associated with the label.",
        }
        missing_second = {
            "case_ref": "update-case-002",
            "evidence_verdict": "insufficient",
            "facts": [],
            "evidence_gaps": ["No guidance statement is visible."],
            "outcome_relation": "not_assessable",
            "outcome_explanation": "No source fact can be associated with the label.",
        }
        caller = ScriptedRoleCaller(
            [
                {**base, "case_diagnostics": [valid_first]},
                {
                    **base,
                    "case_diagnostics": [
                        {
                            **valid_first,
                            "outcome_explanation": "Unrelated rewrite.",
                        },
                        missing_second,
                    ],
                },
            ]
        )
        payload = {
            "update_contract_version": "signal-update-decision-v2",
            "target": {"signal_ref": base["signal_ref"]},
            "induction_cases": [
                {
                    "case_ref": case_ref,
                    "evidence_observation": {"evidence": []},
                    "outcome_relation": {
                        "label": label,
                        "current_signal_relation": "not_assessable",
                    },
                }
                for case_ref, label in (
                    ("update-case-001", "positive"),
                    ("update-case-002", "control"),
                )
            ],
        }

        result = LLMSignalUpdateModel(caller).update(payload)

        diagnostics = {
            item["case_ref"]: item for item in result.value.case_diagnostics
        }
        self.assertEqual(result.usage.llm_calls, 2)
        self.assertEqual(
            diagnostics["update-case-001"]["outcome_explanation"],
            valid_first["outcome_explanation"],
        )
        self.assertEqual(diagnostics["update-case-002"], missing_second)

    def test_signal_update_v2_semantic_blind_review_set(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests"
                / "fixtures"
                / "signal_update_semantic_blind_v1.json"
            ).read_text(encoding="utf-8")
        )
        source_one = "Management raised full-year revenue guidance by 8 percent."
        source_two = "Management maintained prior full-year revenue guidance."
        payload = {
            "update_contract_version": "signal-update-decision-v2",
            "target": {"signal_ref": "guidance_acceleration:v1"},
            "induction_cases": [
                {
                    "case_ref": "blind-case-001",
                    "evidence_observation": {
                        "evidence": [
                            {
                                "document_ref": "blind-document-001",
                                "content_excerpt": source_one,
                            }
                        ]
                    },
                    "outcome_relation": {
                        "label": "positive",
                        "current_signal_relation": "aligned",
                    },
                },
                {
                    "case_ref": "blind-case-002",
                    "evidence_observation": {
                        "evidence": [
                            {
                                "document_ref": "blind-document-002",
                                "content_excerpt": source_two,
                            }
                        ]
                    },
                    "outcome_relation": {
                        "label": "control",
                        "current_signal_relation": "misaligned",
                    },
                },
            ],
        }
        valid_first = {
            "case_ref": "blind-case-001",
            "evidence_verdict": "supported",
            "facts": [
                {
                    "document_ref": "blind-document-001",
                    "exact_span": source_one,
                }
            ],
            "evidence_gaps": [],
            "outcome_relation": "aligned",
            "outcome_explanation": "The source verdict precedes association.",
        }
        valid_second = {
            "case_ref": "blind-case-002",
            "evidence_verdict": "supported",
            "facts": [
                {
                    "document_ref": "blind-document-002",
                    "exact_span": source_two,
                }
            ],
            "evidence_gaps": [],
            "outcome_relation": "misaligned",
            "outcome_explanation": "The source verdict precedes association.",
        }
        base = {
            "signal_ref": "guidance_acceleration:v1",
            "disposition": "defer",
            "problem_type": "semantic_review",
            "rationale": ["Review source facts before outcome association."],
            "candidate": None,
        }

        for review in fixture["cases"]:
            with self.subTest(review_id=review["review_id"]):
                invalid = {
                    **base,
                    "case_diagnostics": [review["diagnostic"], valid_second],
                }
                corrected = {
                    **base,
                    "case_diagnostics": [valid_first, valid_second],
                }
                caller = ScriptedRoleCaller([invalid, corrected])

                result = LLMSignalUpdateModel(caller).update(payload)

                self.assertEqual(result.usage.llm_calls, 2)
                self.assertEqual(result.value.case_diagnostics[0], valid_first)
                self.assertEqual(result.value.case_diagnostics[1], valid_second)
                issue_codes = {
                    item["issue_code"]
                    for item in caller.calls[1]["payload"]["validation_feedback"][
                        "obligations"
                    ]
                }
                self.assertIn(review["expected_issue_code"], issue_codes)

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
                        "label": (
                            "positive" if ref == "packet-a" else "control"
                        ),
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
                    },
                    {
                        "case_ref": "case-002",
                        "observations": [
                            {
                                "summary": "Management maintained its prior position.",
                                "document_ref": "document-02",
                                "exact_span": "Management maintained its prior position.",
                            }
                        ],
                        "evidence_gaps": [],
                        "label": "control",
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
            signal_roles_module._SIGNAL_MINING_HYPOTHESES_V2_OUTPUT,
            signal_roles_module._SIGNAL_MINING_DECISIONS_OUTPUT,
            signal_roles_module._SIGNAL_MINING_SIGNATURES_OUTPUT,
            signal_roles_module._SIGNAL_UPDATE_V2_OUTPUT,
        )
        for contract in contracts:
            with self.subTest(contract=contract):
                self.assertNotIn("example", contract.casefold())
                self.assertNotIn("large_order_confirmation", contract)
                self.assertNotIn("case-001", contract)
                self.assertNotIn("Induction evidence does not isolate", contract)
                self.assertNotIn("An expectation-changing event", contract)
