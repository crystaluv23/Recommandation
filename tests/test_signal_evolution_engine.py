"""Slow Signal and dual-loop evolution tests."""

from tests.scheme_evolution_test_support import *  # noqa: F403


class SignalEvolutionTests(TestCase):
    def test_item1_excerpt_skips_linked_navigation_and_filing_boilerplate(
        self,
    ) -> None:
        document = RawInfoDocument.create(
            document_id="filing-profile",
            company_id="company-profile",
            source_type="10-k",
            published_at=NOW,
            available_at=NOW,
            content=(
                "<html><body>"
                '<div><a href="#item1">ITEM 1. BUSINESS</a></div>'
                "<div>2</div>"
                '<div><a href="#item1a">ITEM 1A. RISK FACTORS</a></div>'
                '<div id="item1">ITEM 1. BUSINESS</div>'
                "<div>Cautionary Statement Regarding Forward-Looking Statements. "
                "These forward-looking statements involve risks.</div>"
                "<div>Reports are available on our website and filed with the "
                "Securities Exchange Commission. This Annual Report on Form 10-K "
                "is not incorporated by reference.</div>"
                "<div>We design and manufacture precision inspection products and "
                "provide monitoring services to semiconductor customers in global "
                "markets. Our business operates through two technology segments and "
                "offers recurring software solutions for advanced factories.</div>"
                '<div id="item1a">ITEM 1A. RISK FACTORS</div>'
                "<div>Demand volatility may harm future results.</div>"
                "</body></html>"
            ),
        )

        excerpt = _item1_business_excerpt((document,))

        self.assertIsNotNone(excerpt)
        assert excerpt is not None
        self.assertTrue(excerpt.startswith("We design and manufacture"))
        self.assertNotIn("forward-looking", excerpt.casefold())
        self.assertNotIn("Demand volatility", excerpt)

    def test_item1_excerpt_rejects_navigation_page_number(self) -> None:
        document = RawInfoDocument.create(
            document_id="filing-navigation-only",
            company_id="company-navigation",
            source_type="10-k",
            published_at=NOW,
            available_at=NOW,
            content=(
                "<html><body>"
                '<div><a href="#item1">ITEM 1. BUSINESS</a></div>'
                "<div>1</div>"
                '<div><a href="#item1a">ITEM 1A. RISK FACTORS</a></div>'
                "<div>5</div>"
                "</body></html>"
            ),
        )

        self.assertIsNone(_item1_business_excerpt((document,)))

    def test_h2_profile_preflight_pauses_before_h1_without_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                replace(
                    make_case(f"preflight_case_{index}", 4.0 if index < 8 else 1.1),
                    basic_info={
                        "company_name": f"Preflight Company {index}",
                        "ticker": f"PF{index:02d}",
                    },
                )
                for index in range(16)
            )
            model = EmptyMiningModel()
            resolver = EvidenceResolver(
                RawInfoStore(),
                adapters=(
                    UnavailableProviderAdapter(
                        "sec_edgar",
                        ("10-k", "filing", "sec_filing"),
                        ("filing_documents",),
                        "SOA_SEC_USER_AGENT is not configured.",
                        unavailability_reason="sec_user_agent_unconfigured",
                    ),
                ),
                policy=DataAcquisitionPolicy(
                    enabled=True,
                    allowed_providers=("sec_edgar",),
                    allowed_capabilities=("filing_documents",),
                    allowed_source_types=("filing",),
                    max_requests_per_cycle=1,
                    max_requests_per_run=1,
                ),
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                evidence_resolver=resolver,
            )

            with self.assertRaises(SlowLoopDataUnavailable) as context:
                engine._run_signal_mining(cycle_id=1)

            self.assertEqual(context.exception.case_ref, "profile-preflight")
            self.assertEqual(
                context.exception.reason, "sec_user_agent_unconfigured"
            )
            self.assertEqual(model.requests, [])

    def test_h2_profile_provider_failure_raises_retryable_slow_pause(self) -> None:
        class ProviderFailureResolver:
            available_source_types = ("filing",)

            def resolve(self, request, *, company_id, identity, as_of):
                del request, company_id, identity, as_of
                return type(
                    "Resolution",
                    (),
                    {
                        "gap": type(
                            "Gap",
                            (),
                            {
                                "reason": type(
                                    "Reason", (), {"value": "provider_error"}
                                )()
                            },
                        )()
                    },
                )()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            case = replace(
                make_case("profile_provider_failure", 4.0),
                basic_info={
                    "company_name": "Profile Provider Failure Corp",
                    "ticker": "PPFC",
                },
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(case,),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                evidence_resolver=ProviderFailureResolver(),
            )

            with self.assertRaises(SlowLoopDataUnavailable) as context:
                engine._mining_case_brief("case-001", case)

            self.assertEqual(context.exception.case_ref, "case-001")
            self.assertEqual(context.exception.reason, "provider_error")
            self.assertTrue(context.exception.retryable)

    def test_h2_profile_readiness_shortage_skips_h2_and_h3(self) -> None:
        class NoDataResolver:
            available_source_types = ("news", "filing")

            def can_acquire(self, request):
                del request
                return True

            def resolve(self, request, *, company_id, identity, as_of):
                del request, company_id, identity, as_of

                class Gap:
                    reason = type("Reason", (), {"value": "provider_no_data"})()

                    @staticmethod
                    def to_dict():
                        return {"reason": "provider_no_data"}

                return type(
                    "Resolution",
                    (),
                    {"gap": Gap(), "status": "unresolved"},
                )()

            def load_documents(self, resolution, *, as_of):
                del resolution, as_of
                return ()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                replace(
                    make_case(f"profile_case_{index}", 4.0 if index < 8 else 1.1),
                    basic_info={
                        "company_name": f"Profile Company {index}",
                        "ticker": f"P{index:02d}",
                    },
                )
                for index in range(16)
            )
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="profile_gap",
                statement="Business profile separates outcomes.",
                applicability="all_ready_issuers",
                expected_positive_pattern="Positive cases show a distinct profile.",
                source_types=("news",),
                query="guidance",
                falsifiers=("Controls show the same profile.",),
            )
            model = ScriptedMiningModel(hypotheses=(hypothesis,))
            raw_store = RawInfoStore(
                documents=(
                    RawInfoDocument.create(
                        document_id="profile-news",
                        company_id=cases[0].company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content="Routine market update without a business profile.",
                    ),
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=raw_store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                evidence_resolver=NoDataResolver(),
            )

            result = engine._run_signal_mining(cycle_id=1)

            self.assertEqual(len(model.requests), 0)
            self.assertEqual(
                result["audit"]["status"], "insufficient_h2_profile_readiness"
            )
            self.assertEqual(result["audit"]["h2_profile_readiness"]["ready"], 0)
            self.assertEqual(result["candidate_refs"], ())

    def test_h2_profile_scan_stops_when_target_and_class_minima_are_met(self) -> None:
        class RankingModel(ScriptedMiningModel):
            def rank_cases(self, payload):
                self.requests.append(dict(payload))
                case_refs = tuple(
                    item["case_ref"] for item in payload["case_briefs"]
                )
                return AgentStep(
                    {"profile_signal": case_refs},
                    AgentUsage(llm_calls=1),
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = (
                make_case("scan_control_a", 1.1),
                make_case("scan_positive_a", 2.5),
                make_case("scan_positive_b", 5.0),
                make_case("scan_positive_c", 12.0),
                make_case("scan_control_b", 1.2),
                make_case("scan_positive_d", 4.0),
            )
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="profile_signal",
                statement="A public update separates outcomes.",
                applicability="all_ready_issuers",
                expected_positive_pattern="Positive cases show the update.",
                source_types=("news",),
                query="public update",
                falsifiers=("Controls show the same update.",),
            )
            model = RankingModel(hypotheses=(hypothesis,))
            raw_store = RawInfoStore(
                documents=(
                    RawInfoDocument.create(
                        document_id="scan-news",
                        company_id=cases[0].company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content="Scan Control A issued a public update.",
                    ),
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=raw_store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=SignalMiningConfig(
                    case_pool_limit=4,
                    h2_profile_scan_limit=6,
                    h2_min_ready_issuers=4,
                    h2_min_ready_per_class=1,
                    induction_cases_per_class=1,
                    validation_cases_per_class=1,
                ),
            )

            result = engine._run_signal_mining(cycle_id=1)

            self.assertEqual(
                result["audit"]["stages"]["H2"]["profile_readiness"]["scanned"],
                4,
            )
            self.assertEqual(
                len(result["audit"]["stages"]["H2"]["case_briefs"]),
                4,
            )
            self.assertEqual(
                result["audit"]["stages"]["H2"]["mode"],
                "deterministic_canonical_applicability",
            )
            self.assertEqual(
                model.requests[0]["h2_applicability_contract"]["observed_values"][
                    "industry_values"
                ],
                ["fixture"],
            )
            self.assertEqual(
                model.requests[0]["h2_applicability_contract"]["observed_values"][
                    "sector_values"
                ],
                [],
            )

    def test_h2_canonical_shortlist_is_local_and_field_exact(self) -> None:
        brief = {
            "business_description": "Develops seafloor mineral resources.",
            "exchange": "NASDAQ",
            "listing_age_bucket": "over_10y",
            "raw_info_coverage": {"source_types": ["10-k", "news"]},
        }

        self.assertTrue(
            SignalEvolutionEngine._h2_applicability_matches(
                "all_ready_issuers", brief
            )
        )
        self.assertTrue(
            SignalEvolutionEngine._h2_applicability_matches(
                "business_description_topics:mineral resource|extraction", brief
            )
        )
        self.assertTrue(
            SignalEvolutionEngine._h2_applicability_matches(
                "exchange_values:NYSE|NASDAQ", brief
            )
        )
        self.assertTrue(
            SignalEvolutionEngine._h2_applicability_matches(
                "raw_info_source_type_values:news", brief
            )
        )
        self.assertFalse(
            SignalEvolutionEngine._h2_applicability_matches(
                "exchange_values:NYSE", brief
            )
        )
        self.assertFalse(
            SignalEvolutionEngine._h2_applicability_matches(
                "business_description_topics:airline", brief
            )
        )

    def test_h3_news_requires_visible_issuer_and_query_relevance(self) -> None:
        case = replace(
            make_case("news_target", 4.0),
            basic_info={
                "company_name": "Target Systems Corp",
                "ticker": "TGTS",
                "industry": "Hardware",
            },
        )
        relevant = RawInfoDocument.create(
            document_id="relevant-news",
            company_id=case.company_id,
            source_type="news",
            published_at=NOW,
            available_at=NOW,
            content="Target Systems Corp raised full-year guidance.",
        )
        metadata_only = RawInfoDocument.create(
            document_id="metadata-only-news",
            company_id=case.company_id,
            source_type="news",
            published_at=NOW,
            available_at=NOW,
            content="Another issuer announced an unrelated product launch.",
            metadata={"associated_ticker": "TGTS", "title": "Market update"},
        )

        kept, _evidence, audit = _select_h3_model_evidence(
            (relevant, metadata_only), case=case, query="guidance", limit=2
        )

        self.assertEqual(tuple(item.document_id for item in kept), ("relevant-news",))
        self.assertEqual(
            audit["filtered_documents"],
            [
                {
                    "document_id": "metadata-only-news",
                    "reason": "missing_strong_issuer_match",
                }
            ],
        )
        self.assertTrue(audit["query_coverage"]["sufficient"])

    def test_h3_visible_brand_from_uppercase_formal_name_is_case_insensitive(
        self,
    ) -> None:
        case = replace(
            make_case("news_target", 4.0),
            basic_info={
                "company_name": "CIENA Corp / CIENA CORP",
                "ticker": "CIEN",
                "industry": "Networking",
            },
        )
        relevant = RawInfoDocument.create(
            document_id="relevant-news",
            company_id=case.company_id,
            source_type="news",
            published_at=NOW,
            available_at=NOW,
            content="Ciena raised full-year guidance for networking demand.",
        )

        kept, _evidence, audit = _select_h3_model_evidence(
            (relevant,), case=case, query="guidance", limit=1
        )

        self.assertEqual(tuple(item.document_id for item in kept), ("relevant-news",))
        self.assertEqual(audit["filtered_documents"], [])
        self.assertTrue(audit["query_coverage"]["sufficient"])

    def test_h3_filing_requires_query_relevance_and_projects_matching_window(
        self,
    ) -> None:
        case = replace(
            make_case("filing_target", 4.0),
            basic_info={"company_name": "Filing Target Corp", "ticker": "FTGT"},
        )
        relevant = RawInfoDocument.create(
            document_id="relevant-quarterly",
            company_id=case.company_id,
            source_type="10-q",
            published_at=NOW,
            available_at=NOW,
            content=(
                "<html><body><div>XML namespace filing header</div>"
                + "<div>ordinary disclosure text</div>" * 100
                + "<div>Quarterly revenue and earnings exceeded analyst "
                "expectations by a material amount.</div>"
                + "<div>signature page tail</div>" * 100
                + "</body></html>"
            ),
        )
        irrelevant = RawInfoDocument.create(
            document_id="irrelevant-quarterly",
            company_id=case.company_id,
            source_type="10-q",
            published_at=NOW,
            available_at=NOW,
            content="<html><body>Only a routine legal exhibit.</body></html>",
        )

        kept, _evidence, audit = _select_h3_model_evidence(
            (relevant, irrelevant),
            case=case,
            query="quarterly revenue earnings analyst expectations",
            limit=1,
        )
        view = _agent_raw_document_view(
            relevant,
            max_content_chars=240,
            query="quarterly revenue earnings analyst expectations",
        )

        self.assertEqual(tuple(item.document_id for item in kept), ("relevant-quarterly",))
        self.assertEqual(
            audit["filtered_documents"],
            [
                {
                    "document_id": "irrelevant-quarterly",
                    "reason": "document_limit_not_selected",
                }
            ],
        )
        self.assertIn("revenue and earnings exceeded analyst", view["content_excerpt"])
        self.assertNotIn("XML namespace filing header", view["content_excerpt"])
        self.assertEqual(view["content_projection"], "normalized_query_window_v1")
        self.assertTrue(audit["query_coverage"]["sufficient"])
        self.assertGreaterEqual(
            len(audit["query_coverage"]["matched_ordered_pairs"]), 1
        )

    def test_h3_marks_scattered_accounting_boilerplate_as_comparator_context(self) -> None:
        case = replace(
            make_case("filing_target", 4.0),
            basic_info={"company_name": "Filing Target Corp", "ticker": "FTGT"},
        )
        boilerplate = RawInfoDocument.create(
            document_id="accounting-boilerplate",
            company_id=case.company_id,
            source_type="10-q",
            published_at=NOW,
            available_at=NOW,
            content=(
                "This quarterly report contains forward-looking statements. "
                "Management makes estimates and assumptions about liabilities. "
                "Reported amounts of revenues and expenses may differ from actual results."
            ),
        )

        kept, _evidence, audit = _select_h3_model_evidence(
            (boilerplate,), case=case,
            query="quarterly revenue analyst estimates comparison", limit=1,
        )

        self.assertEqual(kept, (boilerplate,))
        self.assertFalse(audit["query_coverage"]["sufficient"])
        self.assertEqual(audit["filtered_documents"], [])
        self.assertEqual(
            audit["query_match_status"], "unmatched_comparator_context"
        )

    def test_h3_excerpt_uses_complete_normalized_terms_not_header_substrings(self) -> None:
        document = RawInfoDocument.create(
            document_id="plural-query-window",
            company_id="fixture",
            source_type="10-k",
            published_at=NOW,
            available_at=NOW,
            content=(
                "Office registry reoffering approved guidelines " * 80
                + "Ordinary disclosure. " * 40
                + "The entity signed off-take agreements covering production. "
                + "Debt financing progressed under those agreements. "
                + "Ordinary disclosure. " * 80
            ),
        )
        view = _agent_raw_document_view(
            document, max_content_chars=240, query="off take agreement financing"
        )

        self.assertIn("off-take agreements", view["content_excerpt"])
        self.assertNotIn("Office registry", view["content_excerpt"])
        self.assertLessEqual(len(view["content_excerpt"]), 240)
        self.assertTrue(_h3_text_query_coverage(
            (view["content_excerpt"],), query="off take agreement financing"
        )["sufficient"])

    def test_h3_excerpt_prefers_visible_ordered_pair_over_scattered_terms(self) -> None:
        document = RawInfoDocument.create(
            document_id="ordered-query-window",
            company_id="fixture",
            source_type="filing",
            published_at=NOW,
            available_at=NOW,
            content=(
                "Revenue " + "ordinary legal terms " * 6 + "growth "
                + "ordinary legal terms " * 6 + "segment. "
                + "ordinary disclosure " * 80
                + "Revenue growth across the segment is discussed here. "
                + "ordinary disclosure " * 80
            ),
        )
        view = _agent_raw_document_view(
            document, max_content_chars=320, query="revenue growth segment"
        )

        self.assertIn("Revenue growth across the segment", view["content_excerpt"])
        self.assertTrue(_h3_text_query_coverage(
            (view["content_excerpt"],), query="revenue growth segment"
        )["sufficient"])

    def test_h3_selection_combines_complementary_documents_before_limit(self) -> None:
        case = replace(
            make_case("filing_target", 4.0),
            basic_info={"company_name": "Filing Target Corp", "ticker": "FTGT"},
        )
        routine = RawInfoDocument.create(
            document_id="routine",
            company_id=case.company_id,
            source_type="10-q",
            published_at=NOW,
            available_at=NOW,
            content="Quarterly revenue was reported without comparative context.",
        )
        estimate = RawInfoDocument.create(
            document_id="estimate",
            company_id=case.company_id,
            source_type="10-q",
            published_at=NOW,
            available_at=NOW,
            content="Analyst estimates were the relevant external baseline.",
        )

        selected, evidence, audit = _select_h3_model_evidence(
            (routine, estimate),
            case=case,
            query="quarterly revenue analyst estimates",
            limit=2,
        )

        self.assertEqual({item.document_id for item in selected}, {"routine", "estimate"})
        self.assertEqual(len(evidence), 2)
        self.assertTrue(audit["query_coverage"]["sufficient"])

        selected, evidence, audit = _select_h3_model_evidence(
            (routine, estimate),
            case=case,
            query="quarterly revenue analyst estimates",
            limit=1,
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(len(evidence), 1)
        self.assertFalse(audit["query_coverage"]["sufficient"])
        self.assertEqual(
            audit["query_match_status"], "unmatched_comparator_context"
        )

    def test_h3_model_view_coverage_rejects_terms_hidden_outside_excerpt(self) -> None:
        case = replace(
            make_case("filing_target", 4.0),
            basic_info={"company_name": "Filing Target Corp", "ticker": "FTGT"},
        )
        document = RawInfoDocument.create(
            document_id="scattered-full-filing",
            company_id=case.company_id,
            source_type="10-k",
            published_at=NOW,
            available_at=NOW,
            content=(
                "Revenue growth was discussed in this section. "
                + "ordinary disclosure text " * 120
                + "Composition volume price and segment terms occur elsewhere."
            ),
        )

        kept, _evidence, audit = _select_h3_model_evidence(
            (document,), case=case,
            query="revenue growth composition volume price segment", limit=1,
        )
        view = _agent_raw_document_view(
            document,
            max_content_chars=1_200,
            query="revenue growth composition volume price segment",
        )
        visible_coverage = _h3_text_query_coverage(
            (view["content_excerpt"],),
            query="revenue growth composition volume price segment",
        )

        self.assertEqual(kept, (document,))
        self.assertTrue(
            audit["query_coverage"]["full_document_coverage"]["sufficient"]
        )
        self.assertFalse(visible_coverage["sufficient"])
        self.assertNotIn("revenue", visible_coverage["matched_terms"])

    def test_h3_query_coverage_uses_strong_supermajority_not_all_terms(self) -> None:
        near_complete = _h3_text_query_coverage(
            ("Quarterly revenue and earnings analyst discussion.",),
            query="quarterly revenue earnings analyst outlook",
        )
        minority = _h3_text_query_coverage(
            ("Revenue growth segment discussion.",),
            query="revenue growth composition volume price segment",
        )

        self.assertEqual(near_complete["required_match_count"], 4)
        self.assertEqual(len(near_complete["matched_terms"]), 4)
        self.assertTrue(near_complete["sufficient"])
        self.assertEqual(minority["required_match_count"], 5)
        self.assertEqual(len(minority["matched_terms"]), 3)
        self.assertFalse(minority["sufficient"])

    def test_h3_packet_combines_complementary_ordered_query_pairs(self) -> None:
        case = replace(
            make_case("filing_target", 4.0),
            basic_info={"company_name": "Filing Target Corp", "ticker": "FTGT"},
        )
        actuals = RawInfoDocument.create(
            document_id="quarterly-actuals",
            company_id=case.company_id,
            source_type="10-q",
            published_at=NOW,
            available_at=NOW,
            content="Quarterly revenue increased to $120 million.",
        )
        estimates = RawInfoDocument.create(
            document_id="analyst-estimates",
            company_id=case.company_id,
            source_type="10-q",
            published_at=NOW,
            available_at=NOW,
            content="Analyst estimates called for $110 million.",
        )

        kept, _evidence, audit = _select_h3_model_evidence(
            (actuals, estimates), case=case,
            query="quarterly revenue analyst estimates", limit=2,
        )

        self.assertEqual(
            tuple(item.document_id for item in kept),
            ("quarterly-actuals", "analyst-estimates"),
        )
        self.assertEqual(audit["filtered_documents"], [])
        coverage = audit["query_coverage"]
        self.assertTrue(coverage["sufficient"])
        self.assertEqual(
            set(coverage["matched_ordered_pairs"]),
            {"analyst estimate", "quarterly revenue"},
        )

    def test_h3_hidden_xbrl_terms_do_not_create_a_query_match(self) -> None:
        case = replace(
            make_case("filing_target", 4.0),
            basic_info={"company_name": "Filing Target Corp", "ticker": "FTGT"},
        )
        hidden_only = RawInfoDocument.create(
            document_id="hidden-xbrl-terms",
            company_id=case.company_id,
            source_type="10-k",
            published_at=NOW,
            available_at=NOW,
            content=(
                "<html><body><ix:header><ix:hidden>production volume cost ounce "
                "guidance</ix:hidden></ix:header><div>Routine legal disclosure.</div>"
                "</body></html>"
            ),
        )

        kept, _evidence, audit = _select_h3_model_evidence(
            (hidden_only,), case=case,
            query="production volume cost ounce guidance", limit=1,
        )
        view = _agent_raw_document_view(
            hidden_only,
            max_content_chars=240,
            query="production volume cost ounce guidance",
        )

        self.assertEqual(kept, (hidden_only,))
        self.assertFalse(audit["query_coverage"]["sufficient"])
        self.assertEqual(
            audit["query_match_status"], "unmatched_comparator_context"
        )
        self.assertNotIn("production", view["content_excerpt"])
        self.assertIn("Routine legal disclosure", view["content_excerpt"])

    def test_mining_ranks_identity_and_label_hidden_briefs_then_overlays_labels(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            positive = replace(
                make_case("workflow_positive", 4.0),
                basic_info={
                    "ticker": "WINR",
                    "company_name": "Winner Corp",
                    "business_description": "Winner Corp builds optical systems.",
                    "industry": "Hardware",
                },
            )
            control = replace(
                make_case("workflow_control", 1.1),
                basic_info={
                    "ticker": "CTRL",
                    "company_name": "Control Corp",
                    "business_description": "Control Corp builds optical systems.",
                    "industry": "Hardware",
                },
            )
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="order_confirmation",
                statement="Material order confirmation precedes repricing.",
                applicability="all_ready_issuers",
                expected_positive_pattern="Positive cases disclose confirmed orders.",
                source_types=("news",),
                query="material order",
                falsifiers=("Controls disclose the same pattern.",),
            )
            second_hypothesis = replace(
                hypothesis,
                hypothesis_id="commercialization_confirmation",
            )
            deferred_hypothesis = replace(
                hypothesis,
                hypothesis_id="guidance_confirmation",
            )
            mining_model = ScriptedMiningModel(
                hypotheses=(
                    hypothesis,
                    second_hypothesis,
                    deferred_hypothesis,
                ),
                rankings={
                    item.hypothesis_id: ("case-001", "case-002")
                    for item in (
                        hypothesis,
                        second_hypothesis,
                        deferred_hypothesis,
                    )
                },
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="order_confirmation",
                        disposition="refine",
                        rationale=("Two cases are not enough to draft a Signal.",),
                    ),
                    SignalMiningDecision(
                        hypothesis_id="commercialization_confirmation",
                        disposition="refine",
                        rationale=("The visible cases do not separate the groups.",),
                    ),
                ),
            )
            counterparty_by_company = {
                positive.company_id: control.basic_info["company_name"],
                control.company_id: positive.basic_info["company_name"],
            }
            raw_store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"workflow_news_{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} reported a material "
                            "order involving "
                            f"{counterparty_by_company[case.company_id]}."
                        ),
                    )
                    for index, case in enumerate((positive, control))
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=raw_store,
                discovery_cases=(positive, control),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(2),
            )
            result = engine._run_signal_mining(cycle_id=1)

            ranking_payload = result["audit"]["stages"]["H2"]
            ranking_json = json.dumps(ranking_payload)
            self.assertNotIn("Winner Corp", ranking_json)
            self.assertNotIn("Control Corp", ranking_json)
            self.assertNotIn("WINR", ranking_json)
            self.assertNotIn("CTRL", ranking_json)
            self.assertNotIn("ground_truth", ranking_json)
            self.assertNotIn('"label"', ranking_json)
            contrast_cases = mining_model.requests[1]["evidence_packets"]
            self.assertEqual(
                {item["label"] for item in contrast_cases},
                {"positive", "control"},
            )
            self.assertTrue(
                mining_model.requests[1]["comparisons"][0][
                    "evidence_packet_refs"
                ]
            )
            self.assertNotIn("Winner Corp", json.dumps(contrast_cases))
            self.assertNotIn("Control Corp", json.dumps(contrast_cases))
            self.assertEqual(result["candidate_refs"], ())
            self.assertIn("order_confirmation", result["refined_hypotheses"])
            self.assertEqual(
                result["refined_hypotheses"]["guidance_confirmation"],
                (
                    "deferred because the per-cycle evidence contrast budget was reached",
                ),
            )

    def test_mining_does_not_learn_refinement_from_unusable_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            positive = make_case("evidence_positive", 4.0)
            control = make_case("evidence_control", 1.1)
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="production_cost_pattern",
                statement="Production and cost changes may precede repricing.",
                applicability="all_ready_issuers",
                expected_positive_pattern="Production rises while cost declines.",
                source_types=("news",),
                query="production cost guidance",
                falsifiers=("Controls show the same pattern.",),
            )
            mining_model = ScriptedMiningModel(
                hypotheses=(hypothesis,),
                rankings={
                    "production_cost_pattern": ("case-001", "case-002")
                },
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="production_cost_pattern",
                        disposition="inconclusive",
                        rationale=(
                            "The comparator packets contain no direct production-cost evidence.",
                        ),
                    ),
                ),
            )
            raw_store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"unrelated_{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} filed a routine legal "
                            "notice."
                        ),
                    )
                    for index, case in enumerate((positive, control))
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=raw_store,
                discovery_cases=(positive, control),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(2),
            )
            result = engine._run_signal_mining(cycle_id=1)

            self.assertEqual(len(mining_model.requests), 2)
            self.assertNotIn(
                "production_cost_pattern", result["refined_hypotheses"]
            )
            self.assertIn(
                "production_cost_pattern", result["audit"]["evidence_unavailable"]
            )
            self.assertEqual(
                result["audit"]["stages"]["H3"]["status"],
                "completed_with_inconclusive",
            )
            packets = mining_model.requests[1]["evidence_packets"]
            self.assertEqual(
                {item["query_match_status"] for item in packets},
                {"unmatched_comparator_context"},
            )

    def test_production_mining_falls_back_to_exploration_after_empty_h1(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                make_case(f"explore_{index}", 4.0 if index < 2 else 1.1)
                for index in range(4)
            )
            exploration = exploration_selection(
                cases, cycle_id=1, induction_per_class=1, validation_per_class=1
            )
            signatures = tuple(
                SignalMiningSignature(
                    case_ref=case_ref,
                    observations=(
                        SignalMiningObservation(
                            summary="A material operational event was disclosed.",
                            document_ref="document-01",
                            exact_span="disclosed an operational event.",
                        ),
                    ),
                )
                for case_ref in exploration["e1_refs"]
            )
            mining_model = ScriptedMiningModel(
                signatures=tuple(reversed(signatures)),
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="exploration_event_pattern",
                        disposition="refine",
                        rationale=("The observable event category needs refinement.",),
                    ),
                ),
            )
            mining_model.supports_exploration_fallback = True
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"explore-news-{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} disclosed an operational event."
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=SignalMiningConfig(
                    case_pool_limit=4,
                    ranking_case_limit=4,
                    h2_profile_scan_limit=4,
                    h2_min_ready_issuers=4,
                    h2_min_ready_per_class=2,
                    induction_cases_per_class=1,
                    validation_cases_per_class=1,
                ),
            )

            result = engine._run_signal_mining(cycle_id=1)

            self.assertEqual(
                result["audit"]["track"],
                "hypothesis_then_exploration_fallback",
            )
            self.assertEqual(result["audit"]["hypothesis"]["candidate_refs"], [])
            self.assertEqual(result["audit"]["exploration"]["track"], "exploration")
            self.assertIn(
                "exploration_event_pattern", result["refined_hypotheses"]
            )
            self.assertEqual(len(mining_model.requests), 3)

    def test_production_mining_falls_back_after_h1_correction_exhaustion(
        self,
    ) -> None:
        class FailedH1MiningModel(ScriptedMiningModel):
            supports_exploration_fallback = True

            def propose_hypotheses(self, payload):
                self.requests.append(dict(payload))
                raise CandidateExecutionRejected(
                    "signal_mining_hypotheses",
                    "signal_mining_hypotheses failed validation after 2 corrections",
                    AgentUsage(llm_calls=3, tokens=29, cost=0.03),
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                make_case(f"recover_{index}", 4.0 if index < 2 else 1.1)
                for index in range(4)
            )
            signatures = tuple(
                SignalMiningSignature(
                    case_ref=f"case-{index:03d}",
                    observations=(
                        SignalMiningObservation(
                            summary="A material operational event was disclosed.",
                            document_ref="document-01",
                            exact_span="disclosed an operational event.",
                        ),
                    ),
                )
                for index in (1, 3)
            )
            mining_model = FailedH1MiningModel(
                signatures=signatures,
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="exploration_event_pattern",
                        disposition="refine",
                        rationale=("The repeated event needs refinement.",),
                    ),
                ),
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"recover-news-{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} disclosed an "
                            "operational event."
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=SignalMiningConfig(
                    case_pool_limit=4,
                    ranking_case_limit=4,
                    h2_profile_scan_limit=4,
                    h2_min_ready_issuers=4,
                    h2_min_ready_per_class=2,
                    induction_cases_per_class=1,
                    validation_cases_per_class=1,
                ),
            )

            result = engine._run_signal_mining(cycle_id=1)

            self.assertEqual(
                result["audit"]["status"],
                "completed_with_hypothesis_failure",
            )
            self.assertEqual(
                result["audit"]["track"],
                "hypothesis_then_exploration_fallback",
            )
            hypothesis_audit = result["audit"]["hypothesis"]
            self.assertEqual(hypothesis_audit["status"], "failed")
            self.assertEqual(
                hypothesis_audit["failure_stage"],
                "signal_mining_hypotheses",
            )
            self.assertEqual(hypothesis_audit["usage"]["llm_calls"], 3)
            self.assertEqual(
                hypothesis_audit["failure_details"]["conclusion"]["conclusion"],
                "technical_failure",
            )
            self.assertTrue(
                hypothesis_audit["failure_details"]["input_fingerprint"]
            )
            self.assertEqual(result["audit"]["exploration"]["track"], "exploration")
            self.assertIn(
                "exploration_event_pattern", result["refined_hypotheses"]
            )
            self.assertEqual(len(mining_model.requests), 3)

            class FailedBothTracksModel(FailedH1MiningModel):
                def extract_exploration(self, payload):
                    self.requests.append(dict(payload))
                    raise CandidateExecutionRejected(
                        "signal_mining_exploration_extract",
                        "exploration extraction remained malformed",
                        AgentUsage(llm_calls=2, tokens=17, cost=0.02),
                    )

            failed_model = FailedBothTracksModel()
            failed_engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "failed-workspace"),
                mining_model=failed_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=engine.mining_config,
            )

            failed = failed_engine._run_signal_mining(cycle_id=1)

            self.assertEqual(failed["candidate_refs"], ())
            self.assertEqual(
                failed["audit"]["status"], "completed_with_hypothesis_failure"
            )
            exploration = failed["audit"]["exploration"]
            self.assertEqual(
                exploration["stages"]["E2"]["status"],
                "not_called_evidence_unavailable",
            )
            self.assertEqual(
                exploration["stages"]["E1"]["usage"]["llm_calls"], 2
            )
            self.assertEqual(len(failed["failures"]), 2)
            self.assertTrue(
                all(
                    "exhausted structured recovery" in " ".join(reasons)
                    for reasons in failed["failures"].values()
                )
            )

    def test_identical_committed_no_hypothesis_suppresses_repeated_h1_work(
        self,
    ) -> None:
        class NoHypothesisModel(EmptyMiningModel):
            def propose_hypotheses(self, payload):
                self.requests.append(dict(payload))
                return AgentStep(
                    (),
                    AgentUsage(llm_calls=1),
                    metadata={
                        "conclusion": "no_testable_hypothesis",
                        "reason_code": "insufficient_retrieval_basis",
                        "rationale": ["No new measurable field is visible."],
                        "need_refs": [],
                    },
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                make_case(f"no_hypothesis_{index}", 4.0 if index < 2 else 1.1)
                for index in range(4)
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"no-hypothesis-news-{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=f"{case.company_id} published a routine update.",
                    )
                    for index, case in enumerate(cases)
                )
            )
            workspace = EvolutionWorkspace(root / "workspace")
            model = NoHypothesisModel()
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_model=model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=SignalMiningConfig(
                    case_pool_limit=4,
                    ranking_case_limit=4,
                    h2_profile_scan_limit=4,
                    h2_min_ready_issuers=4,
                    h2_min_ready_per_class=2,
                    induction_cases_per_class=1,
                    validation_cases_per_class=1,
                ),
            )

            first = engine._run_signal_mining(cycle_id=1)
            cycle_dir = workspace.experiments_root / "cycles" / "cycle-0001"
            cycle_dir.mkdir(parents=True)
            (cycle_dir / "slow_loop_validation.json").write_text(
                json.dumps(
                    {
                        "validation": {
                            "refined_hypotheses": {},
                            "agent_audits": {"mining_pipeline": first["audit"]},
                        }
                    }
                ),
                encoding="utf-8",
            )

            second = engine._run_signal_mining(cycle_id=2)

            self.assertEqual(len(model.requests), 1)
            self.assertEqual(
                second["audit"]["status"], "unchanged_h1_work_suppressed"
            )
            self.assertTrue(
                second["audit"]["stages"]["H1"]["reused_from_prior_cycle"]
            )

    def test_mining_falls_through_to_next_ranked_case_with_usable_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                [make_case(f"fallback_positive_{index}", 4.0) for index in range(3)]
                + [make_case(f"fallback_control_{index}", 1.1) for index in range(3)]
            )
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="production_cost_pattern",
                statement="Production and cost changes may precede repricing.",
                applicability="all_ready_issuers",
                expected_positive_pattern="Production rises while cost declines.",
                source_types=("news",),
                query="production cost guidance",
                falsifiers=("Controls show the same pattern.",),
            )
            mining_model = ScriptedMiningModel(
                hypotheses=(hypothesis,),
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="production_cost_pattern",
                        disposition="refine",
                        rationale=("The visible pattern remains underspecified.",),
                    ),
                ),
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=SignalMiningConfig(
                    case_pool_limit=6,
                    ranking_case_limit=6,
                    h2_profile_scan_limit=6,
                    h2_min_ready_issuers=6,
                    h2_min_ready_per_class=3,
                    induction_cases_per_class=1,
                    validation_cases_per_class=1,
                ),
            )
            pairs = engine._mining_case_universe(limit=6)
            refs_by_class = {
                class_value: [
                    case_ref
                    for case_ref, case in pairs
                    if bool(case.ground_truth.is_surge) is class_value
                ]
                for class_value in (True, False)
            }
            ranking = tuple(
                value
                for index in range(3)
                for value in (
                    refs_by_class[True][index],
                    refs_by_class[False][index],
                )
            )
            mining_model.rankings = {"production_cost_pattern": ranking}
            usable_refs = {
                refs_by_class[True][1],
                refs_by_class[False][1],
            }
            engine.raw_info_store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"usable_{case_ref}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} reported production "
                            "cost guidance."
                        ),
                    )
                    for case_ref, case in pairs
                    if case_ref in usable_refs
                )
            )
            engine.evidence_resolver = EvidenceResolver(engine.raw_info_store)

            result = engine._run_signal_mining(cycle_id=1)

            selected = result["audit"]["local_selection"][0]
            self.assertEqual(set(selected["induction_case_refs"]), usable_refs)
            self.assertEqual(len(mining_model.requests), 2)
            attempted = {
                item["case_ref"]
                for item in result["audit"]["stages"]["H3"]["resolutions"]
            }
            self.assertTrue(
                {
                    refs_by_class[True][0],
                    refs_by_class[False][0],
                }.issubset(attempted)
            )

    def test_mining_keeps_h3_inconclusive_out_of_semantic_refinement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            positive = make_case("inconclusive_positive", 4.0)
            control = make_case("inconclusive_control", 1.1)
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="production_cost_pattern",
                statement="Production and cost changes may precede repricing.",
                applicability="all_ready_issuers",
                expected_positive_pattern="Production rises while cost declines.",
                source_types=("news",),
                query="production cost guidance",
                falsifiers=("Controls show the same pattern.",),
            )
            mining_model = ScriptedMiningModel(
                hypotheses=(hypothesis,),
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="production_cost_pattern",
                        disposition="inconclusive",
                        rationale=(
                            "The visible material remains insufficient to compare guidance.",
                        ),
                    ),
                ),
            )
            documents = tuple(
                RawInfoDocument.create(
                    document_id=f"inconclusive_{case.company_id}",
                    company_id=case.company_id,
                    source_type="news",
                    published_at=NOW,
                    available_at=NOW,
                    content=(
                        f"{case.basic_info['company_name']} reported production cost "
                        "guidance without a comparable historical range."
                    ),
                )
                for case in (positive, control)
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(documents=documents),
                discovery_cases=(positive, control),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(2),
            )
            mining_model.rankings = {
                "production_cost_pattern": tuple(
                    case_ref
                    for case_ref, _case in engine._mining_case_universe(limit=2)
                )
            }

            result = engine._run_signal_mining(cycle_id=1)

            self.assertNotIn(
                "production_cost_pattern", result["refined_hypotheses"]
            )
            self.assertIn(
                "production_cost_pattern", result["audit"]["evidence_unavailable"]
            )
            self.assertEqual(
                result["audit"]["stages"]["H3"]["status"],
                "completed_with_inconclusive",
            )

    def test_signal_update_makes_zero_calls_without_actionable_learning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            update_model = NoChangeUpdateModel()
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("workflow_case", 4.0),),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_model=update_model,
                llm_signal_runner=None,
            )
            result = engine._run_signal_update(cycle_id=1)

            self.assertEqual(result["candidate_refs"], ())
            self.assertEqual(result["audit"]["disposition"], "no_actionable_target")
            self.assertFalse(result["audit"]["model_called"])
            self.assertEqual(update_model.requests, [])

    def test_signal_update_processes_top_three_actionable_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            fixture = candidate_growth_fixture()
            signal_refs: list[str] = []
            for suffix in ("a", "b", "c", "d"):
                spec = SignalSpec(
                    signal_id=f"update_signal_{suffix}",
                    version=1,
                    category="fundamental",
                    description=f"Revenue growth threshold variant {suffix}.",
                    execution_type=SignalExecutionType.DETERMINISTIC,
                    source_types=("financials",),
                    function="financial.revenue_growth_yoy",
                    parameters={"positive_min": 0.2, "negative_max": 0.0},
                )
                registry.register_stable(spec, tests=(fixture,))
                signal_refs.append(spec.ref)
                for index in range(2):
                    registry.record_learning_event(
                        SignalLearningEvent(
                            event_id=f"{suffix}-wrong-event-{index}",
                            observation_key=f"{suffix}-wrong-observation-{index}",
                            signal_ref=spec.ref,
                            round_id=1,
                            plan_id=f"plan-{suffix}-{index}",
                            case_id=f"fast-case-{suffix}-{index}",
                            company_id=f"fast-issuer-{suffix}-{index}",
                            prediction_time=NOW.isoformat(),
                            selection={
                                "signal_ref": spec.ref,
                                "reason_code": "answer_need",
                                "selection_reason": "Test reported revenue growth.",
                                "applicability_hypothesis": (
                                    "Annual periods are comparable."
                                ),
                                "expected_role": "primary",
                                "context_tags": ["comparable_financials"],
                            },
                            result_value=SignalValue.POSITIVE,
                            coverage=SignalCoverage.SUFFICIENT,
                            document_fingerprint=(f"hash-{suffix}-{index}",),
                            is_surge=False,
                            realized_max_multiple=1.2,
                            prediction_correct=False,
                        )
                    )

            cases = tuple(
                [make_case(f"portfolio_positive_{index}", 4.0) for index in range(4)]
                + [make_case(f"portfolio_control_{index}", 1.1) for index in range(4)]
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"portfolio_financial_{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            ("2024-01-01", "2024-12-31", 125.0, "2025-01-10"),
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            update_model = NoChangeUpdateModel()
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_model=update_model,
                llm_signal_runner=None,
            )

            result = engine._run_signal_update(cycle_id=1)

            self.assertEqual(result["candidate_refs"], ())
            self.assertEqual(len(update_model.requests), 3, result["audit"])
            self.assertEqual(
                [request["target"]["signal_ref"] for request in update_model.requests],
                signal_refs[:3],
            )
            audit = result["audit"]
            self.assertEqual(audit["schema_version"], "signal-update-audit-v2")
            self.assertEqual(audit["target_limit"], 3)
            self.assertEqual(audit["target_count"], 3)
            self.assertEqual(audit["model_target_count"], 3)
            self.assertEqual(audit["model_usage"]["llm_calls"], 3)
            self.assertEqual(len(audit["targets"]), 3)
            self.assertTrue(all(item["model_called"] for item in audit["targets"]))

    def test_signal_update_isolates_one_target_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("workflow_case", 4.0),),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )
            targets = tuple(
                {
                    "signal_ref": f"test_signal_{index}:v1",
                    "problem_type": "repeated_directional_wrong",
                    "support": {"directional_wrong": 2},
                    "recurring_contexts": [],
                }
                for index in range(3)
            )
            attempted: list[str] = []
            engine._select_signal_update_targets = lambda: targets

            def run_one(*, cycle_id, target, cases, executor):
                attempted.append(target["signal_ref"])
                if len(attempted) == 1:
                    raise ValidationError("first target failed")
                return engine._signal_update_output(
                    audit={
                        "schema_version": "signal-update-target-audit-v1",
                        "cycle_id": cycle_id,
                        "status": "completed",
                        "model_called": False,
                        "target": dict(target),
                        "issue_fingerprint": "a" * 64,
                        "disposition": "defer",
                    }
                )

            engine._run_one_signal_update = run_one

            result = engine._run_signal_update(cycle_id=1)

            self.assertEqual(attempted, [item["signal_ref"] for item in targets])
            self.assertIn("update:test_signal_0:v1", result["failures"])
            self.assertEqual(
                [item["status"] for item in result["audit"]["targets"]],
                ["failed", "completed", "completed"],
            )

    def test_signal_update_finds_prior_work_audits_in_v1_and_v2(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("workflow_case", 4.0),),
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )
            cycles = workspace.experiments_root / "cycles"
            legacy_dir = cycles / "cycle-0001"
            legacy_dir.mkdir(parents=True)
            (legacy_dir / "slow_loop_validation.json").write_text(
                json.dumps(
                    {
                        "validation": {
                            "agent_audits": {
                                "update_pipeline": {
                                    "schema_version": "signal-update-audit-v1",
                                    "issue_fingerprint": "same-problem",
                                    "work_fingerprint": "legacy-work",
                                    "disposition": "defer",
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            portfolio_dir = cycles / "cycle-0002"
            portfolio_dir.mkdir(parents=True)
            (portfolio_dir / "slow_loop_validation.json").write_text(
                json.dumps(
                    {
                        "validation": {
                            "agent_audits": {
                                "update_pipeline": {
                                    "schema_version": "signal-update-audit-v2",
                                    "targets": [
                                        {
                                            "schema_version": (
                                                "signal-update-target-audit-v1"
                                            ),
                                            "issue_fingerprint": "same-problem",
                                            "work_fingerprint": "portfolio-work",
                                            "disposition": "defer",
                                        }
                                    ],
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                engine._prior_signal_update("legacy-work")["disposition"],
                "defer",
            )
            self.assertEqual(
                engine._prior_signal_update("portfolio-work")["disposition"],
                "defer",
            )
            self.assertIsNone(engine._prior_signal_update("same-problem"))

    def test_signal_update_suppresses_exact_work_but_retries_relevant_new_input(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                [make_case(f"work_positive_{index}", 4.0) for index in range(4)]
                + [make_case(f"work_control_{index}", 1.1) for index in range(4)]
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"work_financial_{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            (
                                "2024-01-01",
                                "2024-12-31",
                                130.0 if case.ground_truth.is_surge else 125.0,
                                "2025-01-10",
                            ),
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            workspace = EvolutionWorkspace(root / "workspace")
            update_model = NoChangeUpdateModel()
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_model=EmptyMiningModel(),
                update_model=update_model,
                llm_signal_runner=None,
            )
            target = {
                "signal_ref": "revenue_growth_yoy:v1",
                "problem_type": "repeated_directional_wrong",
                "support": {
                    "unique_observations": 8,
                    "misleading_attributions": 0,
                    "directional_wrong": 4,
                    "unavailable": 0,
                    "unavailable_with_inputs": 0,
                },
                "recurring_contexts": [],
            }

            def execute_update():
                executor = SignalExecutor(registry.freeze(), store)
                return engine._run_one_signal_update(
                    cycle_id=2,
                    target=target,
                    cases=cases,
                    executor=executor,
                )

            first = execute_update()
            cycle_dir = workspace.experiments_root / "cycles" / "cycle-0001"
            cycle_dir.mkdir(parents=True)
            (cycle_dir / "slow_loop_validation.json").write_text(
                json.dumps(
                    {
                        "validation": {
                            "agent_audits": {
                                "update_pipeline": {
                                    "schema_version": "signal-update-audit-v2",
                                    "targets": [first["audit"]],
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            repeated = execute_update()
            self.assertEqual(repeated["audit"]["disposition"], "unchanged_work_suppressed")
            self.assertEqual(len(update_model.requests), 1)

            store.append(
                RawInfoDocument.create(
                    document_id="unrelated_work_document",
                    company_id="other_issuer",
                    source_type="financials",
                    published_at=NOW,
                    available_at=NOW,
                    content="Unrelated issuer revenue disclosure.",
                )
            )
            still_repeated = execute_update()
            self.assertEqual(
                still_repeated["audit"]["disposition"],
                "unchanged_work_suppressed",
            )
            self.assertEqual(len(update_model.requests), 1)

            store.append(
                RawInfoDocument.create(
                    document_id="relevant_work_document",
                    company_id=cases[0].company_id,
                    source_type="financials",
                    published_at=NOW,
                    available_at=NOW,
                    content=sec_company_facts_content(
                        ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                        ("2024-01-01", "2024-12-31", 140.0, "2025-01-10"),
                    ),
                )
            )
            changed = execute_update()
            self.assertEqual(changed["audit"]["disposition"], "no_change")
            self.assertNotEqual(
                changed["audit"]["work_fingerprint"],
                first["audit"]["work_fingerprint"],
            )
            self.assertEqual(len(update_model.requests), 2)

    def test_mining_context_preserves_refinement_reasons_and_data_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("workflow_case", 4.0),),
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )
            refined = {
                "hypothesis_id": "refined_pattern",
                "statement": "An underspecified pattern.",
            }
            unavailable = {
                "hypothesis_id": "missing_evidence_pattern",
                "statement": "A pattern needing unavailable evidence.",
            }
            cycle_dir = workspace.experiments_root / "cycles" / "cycle-0001"
            cycle_dir.mkdir(parents=True)
            (cycle_dir / "slow_loop_validation.json").write_text(
                json.dumps(
                    {
                        "validation": {
                            "refined_hypotheses": {
                                "refined_pattern": [
                                    "The visible controls show the same pattern."
                                ]
                            },
                            "agent_audits": {
                                "mining_pipeline": {
                                    "evidence_unavailable": {
                                        "missing_evidence_pattern": [
                                            "No query-relevant 10-Q was available."
                                        ]
                                    },
                                    "stages": {
                                        "H1": {
                                            "input_fingerprint": "h1-input-hash",
                                            "conclusion": {
                                                "conclusion": "no_testable_hypothesis",
                                                "reason_code": (
                                                    "insufficient_retrieval_basis"
                                                ),
                                            },
                                            "hypotheses": [refined, unavailable]
                                        }
                                    },
                                }
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            prior = engine._mining_context(cycle_id=2)["prior_slow_work"][0]

            self.assertEqual(
                prior["refined_hypotheses"][0],
                {
                    "hypothesis": refined,
                    "reasons": ["The visible controls show the same pattern."],
                },
            )
            self.assertEqual(
                prior["evidence_unavailable"][0],
                {
                    "hypothesis": unavailable,
                    "reasons": ["No query-relevant 10-Q was available."],
                },
            )
            self.assertEqual(prior["h1_input_fingerprint"], "h1-input-hash")
            self.assertEqual(
                prior["h1_conclusion"]["conclusion"],
                "no_testable_hypothesis",
            )

    def test_signal_update_uses_one_induction_call_and_local_holdout_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            stable = registry.load_spec("revenue_growth_yoy:v1")
            for index in range(2):
                registry.record_learning_event(
                    SignalLearningEvent(
                        event_id=f"wrong-event-{index}",
                        observation_key=f"wrong-observation-{index}",
                        signal_ref=stable.ref,
                        round_id=1,
                        plan_id=f"plan-{index}",
                        case_id=f"fast-case-{index}",
                        company_id=f"fast-issuer-{index}",
                        prediction_time=NOW.isoformat(),
                        selection={
                            "signal_ref": stable.ref,
                            "reason_code": "answer_need",
                            "selection_reason": "Test reported revenue growth.",
                            "applicability_hypothesis": "Annual periods are comparable.",
                            "expected_role": "primary",
                            "context_tags": ["comparable_financials"],
                        },
                        result_value=SignalValue.POSITIVE,
                        coverage=SignalCoverage.SUFFICIENT,
                        document_fingerprint=(f"hash-{index}",),
                        is_surge=False,
                        realized_max_multiple=1.2,
                        prediction_correct=False,
                    )
                )

            cases = tuple(
                [make_case(f"update_positive_{index}", 4.0) for index in range(4)]
                + [make_case(f"update_control_{index}", 1.1) for index in range(4)]
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"update_financial_{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            (
                                "2024-01-01",
                                "2024-12-31",
                                130.0 if case.ground_truth.is_surge else 125.0,
                                "2025-01-10",
                            ),
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            updated = replace(
                stable,
                version=2,
                parameters={"positive_min": 0.28, "negative_max": 0.0},
            )
            fixture = candidate_growth_fixture()
            fixture["documents"][0]["content"] = sec_company_facts_content(
                ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                ("2024-01-01", "2024-12-31", 130.0, "2025-01-10"),
            )
            update_model = ScriptedUpdateModel(
                SignalUpdateDecision(
                    signal_ref=stable.ref,
                    disposition="update",
                    problem_type="threshold_false_positives",
                    rationale=("The current threshold is repeatedly too permissive.",),
                    candidate={
                        "signal_ref": stable.ref,
                        "spec": updated.to_dict(),
                        "skill": None,
                        "tests": [fixture],
                    },
                )
            )
            workspace = EvolutionWorkspace(root / "workspace")
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_model=EmptyMiningModel(),
                update_model=update_model,
                llm_signal_runner=None,
            )
            snapshot = registry.freeze()
            workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=1,
                initial_signal_registry_version=snapshot.version,
                initial_signal_registry_hash=snapshot.registry_hash,
                observed_signal_registry_version=snapshot.version,
                observed_signal_registry_hash=snapshot.registry_hash,
            )
            committed = make_record(
                "update_target_round",
                0.5,
                (1.0, 0.0),
                round_id=1,
            )
            workspace.commit_round(
                round_id=1,
                records=(committed,),
                meta_entry=RoundMetaEntry(
                    round_id=1,
                    evidence_refs=(committed.plan_id,),
                ),
                signal_registry_version=snapshot.version,
                signal_registry_hash=snapshot.registry_hash,
                run_contract_hash="contract-hash",
            )

            result = engine.run_cycle(cycle_id=1, input_snapshot=snapshot)

            self.assertEqual(result.promoted, (updated.ref,))
            self.assertEqual(len(update_model.requests), 1)
            self.assertNotIn("example", update_model.requests[0]["candidate_contract"])
            self.assertNotIn("example", engine._mining_candidate_contract())
            request_json = json.dumps(update_model.requests[0])
            for case in cases:
                self.assertNotIn(case.company_id, request_json)
            update_audit = result.agent_audits["update_pipeline"]
            self.assertEqual(update_audit["target_count"], 1)
            target_audit = update_audit["targets"][0]
            for packet in update_model.requests[0]["induction_cases"]:
                observation = packet["evidence_observation"]
                self.assertIn(
                    "excerpt cannot prove",
                    observation["evidence_scope"],
                )
                self.assertEqual(len(observation["evidence"]), 1)
                self.assertTrue(observation["executed_evidence"])
                cited_refs = {
                    item["document_ref"]
                    for item in observation["executed_evidence"]
                }
                self.assertEqual(
                    observation["evidence"][0]["document_ref"],
                    next(iter(cited_refs)),
                )
                result_evidence = observation["current_signal_result"]["evidence"]
                self.assertTrue(
                    result_evidence["supporting"] or result_evidence["counter"]
                )
            for resolution in target_audit["resolutions"]:
                self.assertTrue(resolution["reused_signal_execution_input"])
                self.assertEqual(resolution["document_count"], 1)
                self.assertEqual(len(resolution["document_ids"]), 1)
                self.assertEqual(len(resolution["document_hashes"]), 1)
                self.assertTrue(
                    resolution["input_request"]["request_id"].startswith("signal:")
                )
                self.assertEqual(
                    resolution["input_request"]["query"], "revenue growth yoy"
                )
            induction_ids = set(
                target_audit["local_selection"]["induction_case_ids"]
            )
            holdout_ids = set(
                target_audit["local_selection"]["holdout_case_ids"]
            )
            self.assertFalse(induction_ids & holdout_ids)
            self.assertTrue(update_audit["model_called"])
            effectiveness = result.candidate_effectiveness[updated.ref]
            self.assertEqual(effectiveness["disposition"], "promoted")
            self.assertLess(
                effectiveness["candidate"]["directional_wrong"],
                effectiveness["current"]["directional_wrong"],
            )

    def test_mining_tool_rejects_existing_stable_signal_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("discovery_case", 4.0),),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )

            with self.assertRaisesRegex(
                ValidationError, "duplicates stable Signal identity"
            ):
                engine._stage_from_tool(
                    spec=registry.load_spec("price_momentum_126d:v1").to_dict(),
                    skill=None,
                    tests=(candidate_growth_fixture(),),
                    origin="mining",
                    collected=[],
                )

    def test_candidate_validation_rejects_leakage_duplicate_and_bad_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            validator = SignalCandidateValidator(registry, llm_runner=None)
            leaking = SignalSpec(
                signal_id="future_outcome_hint",
                version=1,
                category="risks",
                description="Use future price to infer the outcome label.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            finding = validator.validate(leaking, skill=None, tests=())
            self.assertFalse(finding.accepted)
            self.assertTrue(any("leakage" in reason for reason in finding.reasons))
            duplicate = SignalSpec(
                signal_id="duplicate_growth",
                version=1,
                category="financial",
                description=registry.latest_spec("revenue_growth_yoy").description,
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            self.assertFalse(
                validator.validate(duplicate, skill=None, tests=()).accepted
            )
            bad_update = SignalSpec(
                signal_id="revenue_growth_yoy",
                version=3,
                category="financial",
                description="Updated growth measure.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            self.assertFalse(
                validator.validate(bad_update, skill=None, tests=()).accepted
            )

            common_word_validator = SignalCandidateValidator(
                registry,
                llm_runner=None,
                forbidden_identity_terms=("FOR",),
            )
            prose_candidate = SignalSpec(
                signal_id="catalyst_handling_quality",
                version=1,
                category="catalysts",
                description="Check handling for positive catalyst evidence.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            self.assertTrue(
                common_word_validator.validate(
                    prose_candidate,
                    skill=None,
                    tests=(candidate_growth_fixture(),),
                ).accepted
            )

    def test_paired_effectiveness_rejects_an_identical_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                make_case(f"paired_positive_{index}", 4.0)
                for index in range(4)
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"paired_financial_{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            ("2024-01-01", "2024-12-31", 125.0, "2025-01-10"),
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            current = registry.latest_spec("revenue_growth_yoy")
            candidate = SignalSpec(
                **{
                    **current.__dict__,
                    "version": current.version + 1,
                    "description": "Equivalent revenue-growth wording.",
                }
            )

            result = SignalCandidateEffectivenessEvaluator(
                registry,
                raw_info_store=store,
                discovery_cases=cases,
                llm_runner=None,
            ).evaluate(candidate, skill=None)

            self.assertFalse(result.accepted)
            self.assertIn(
                "no strict paired effectiveness gain",
                " ".join(result.reasons),
            )

    def test_effectiveness_excludes_induction_and_marks_sparse_support_provisional(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(SEED_CATALOG)
            induction = (
                make_case("induction_positive", 4.0),
                make_case("induction_control", 1.1),
            )
            validation = (
                make_case("validation_positive", 4.0),
                make_case("validation_control", 1.1),
            )
            cases = (*induction, *validation)
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"independent_financial_{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            (
                                "2024-01-01",
                                "2024-12-31",
                                125.0 if case.ground_truth.is_surge else 90.0,
                                "2025-01-10",
                            ),
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            candidate = SignalSpec(
                signal_id="independent_growth_direction",
                version=1,
                category="financial",
                description="Classify comparable revenue growth direction.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            evaluator = SignalCandidateEffectivenessEvaluator(
                registry,
                raw_info_store=store,
                discovery_cases=cases,
                llm_runner=None,
                case_limit=2,
                minimum_cases=2,
            )

            accepted = evaluator.evaluate(
                candidate,
                skill=None,
                preferred_case_ids=tuple(case.case_id for case in validation),
                excluded_case_ids=tuple(case.case_id for case in induction),
                induction_supported=True,
            )
            provisional = SignalCandidateEffectivenessEvaluator(
                registry,
                raw_info_store=store,
                discovery_cases=induction,
                llm_runner=None,
                case_limit=2,
                minimum_cases=2,
            ).evaluate(
                candidate,
                skill=None,
                excluded_case_ids=tuple(case.case_id for case in induction),
                induction_supported=True,
            )

            self.assertTrue(accepted.accepted)
            self.assertEqual(accepted.disposition, "promoted")
            self.assertEqual(set(accepted.case_ids), {case.case_id for case in validation})
            self.assertEqual(provisional.disposition, "provisional")
            self.assertFalse(provisional.accepted)

    def test_slow_loop_validates_and_auto_promotes_exact_batch_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            new_spec = SignalSpec(
                signal_id="discovery_growth_quality",
                version=1,
                category="financial",
                description="Measure whether growth is broad-based across disclosed segments.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
                parameters={"positive_min": 0.10, "negative_max": 0.0},
            )
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="broad_growth",
                statement="Point-in-time revenue acceleration separates winners.",
                applicability="all_ready_issuers",
                expected_positive_pattern="Positive cases show stronger growth.",
                source_types=("financials",),
                query="revenue",
                falsifiers=("Controls show the same growth.",),
            )
            mining_model = ScriptedMiningModel(
                hypotheses=(hypothesis,),
                rankings={
                    "broad_growth": tuple(
                        f"case-{index:03d}" for index in range(1, 9)
                    )
                },
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="broad_growth",
                        disposition="supported",
                        rationale=("Positive and control cases separate consistently.",),
                        candidate={
                            "spec": new_spec.to_dict(),
                            "skill": None,
                            "tests": [candidate_growth_fixture()],
                        },
                    ),
                ),
            )
            discovery_cases = tuple(
                [
                    make_case(f"discovery_positive_{index}", 4.0)
                    for index in range(4)
                ]
                + [
                    make_case(f"discovery_control_{index}", 1.1)
                    for index in range(4)
                ]
            )
            raw_store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"effectiveness_financial_{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            (
                                "2024-01-01",
                                "2024-12-31",
                                115.0 if case.ground_truth.is_surge else 90.0,
                                "2025-01-10",
                            ),
                        ),
                    )
                    for index, case in enumerate(discovery_cases)
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=raw_store,
                discovery_cases=discovery_cases,
                meta_memory=PlanMetaMemory(),
                workspace=workspace,
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(len(discovery_cases)),
            )
            snapshot = registry.freeze()
            workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=1,
                initial_signal_registry_version=snapshot.version,
                initial_signal_registry_hash=snapshot.registry_hash,
                observed_signal_registry_version=snapshot.version,
                observed_signal_registry_hash=snapshot.registry_hash,
            )
            committed = make_record(
                "plan_before_signal_promotion",
                0.8,
                (1.0, 0.0),
                round_id=1,
            )
            workspace.commit_round(
                round_id=1,
                records=(committed,),
                meta_entry=RoundMetaEntry(
                    round_id=1,
                    evidence_refs=(committed.plan_id,),
                ),
                signal_registry_version=snapshot.version,
                signal_registry_hash=snapshot.registry_hash,
                run_contract_hash="contract-hash",
            )
            original_bump_version = registry.bump_version

            def interrupt_before_version_commit():
                registry.bump_version = original_bump_version
                raise RuntimeError("simulated interruption before Registry version commit")

            registry.bump_version = interrupt_before_version_commit
            with self.assertRaisesRegex(RuntimeError, "simulated interruption"):
                engine.run_cycle(cycle_id=1, input_snapshot=snapshot)
            self.assertEqual(registry.version, 1)
            mining_request_count = len(mining_model.requests)

            result = engine.run_cycle(cycle_id=1)
            self.assertEqual(
                set(result.validated_candidates),
                {"discovery_growth_quality:v1"},
            )
            self.assertEqual(set(result.promoted), set(result.validated_candidates))
            self.assertEqual(
                result.agent_audits["mining_pipeline"]["track"],
                "hypothesis",
            )
            self.assertEqual(result.input_registry_version, 1)
            self.assertEqual(result.output_registry_version, 2)
            self.assertEqual(registry.latest_spec("revenue_growth_yoy").version, 1)
            self.assertFalse(
                (
                    root
                    / "signals_candidates"
                    / "financial"
                    / "discovery_growth_quality"
                    / "v1"
                    / "approval.json"
                ).exists()
            )
            promoted = engine.run_cycle(cycle_id=1)
            self.assertEqual(
                set(promoted.promoted),
                {"discovery_growth_quality:v1"},
            )
            self.assertEqual(promoted.registry_version, 2)
            self.assertEqual(len(mining_model.requests), mining_request_count)
            self.assertEqual(registry.latest_spec("revenue_growth_yoy").version, 1)
            self.assertEqual(registry.latest_spec("discovery_growth_quality").version, 1)

    def test_mining_controller_rejects_malformed_candidate_spec_locally(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            invalid_spec = registry.load_spec("guidance_acceleration:v1").to_dict()
            invalid_spec["execution"].pop("type")
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="guidance_change",
                statement="Explicit guidance changes separate winners.",
                applicability="all_ready_issuers",
                expected_positive_pattern="Positive cases raise guidance.",
                source_types=("news",),
                query="guidance",
                falsifiers=("Controls raise guidance equally often.",),
            )
            mining_model = ScriptedMiningModel(
                hypotheses=(hypothesis,),
                rankings={"guidance_change": ("case-001", "case-002")},
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="guidance_change",
                        disposition="supported",
                        rationale=("The small sample separates.",),
                        candidate={
                            "spec": invalid_spec,
                            "skill": None,
                            "tests": [],
                        },
                    ),
                ),
            )
            positive = make_case("discovery_positive", 4.0)
            control = make_case("discovery_control", 1.1)
            raw_store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"guidance_news_{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} management changed "
                            "guidance."
                        ),
                    )
                    for index, case in enumerate((positive, control))
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=raw_store,
                discovery_cases=(positive, control),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(2),
            )

            result = engine._validate_cycle(registry.freeze())

            self.assertEqual(result.validated_candidates, {})
            self.assertIn(
                "candidate SignalSpec JSON is invalid",
                str(result.rejected["slow_loop:mining_stage:guidance_change"]),
            )

    def test_exploration_freezes_label_hidden_signatures_before_reveal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                [make_case(f"explore_positive_{index}", 4.0) for index in range(4)]
                + [make_case(f"explore_control_{index}", 1.1) for index in range(4)]
            )
            selection = exploration_selection(
                cases, cycle_id=3, induction_per_class=2, validation_per_class=2
            )
            induction_refs = selection["e1_refs"]
            mining_model = ScriptedMiningModel(
                signatures=tuple(
                    SignalMiningSignature(
                        case_ref=case_ref,
                        observations=(
                            SignalMiningObservation(
                                summary="A bounded observable event is present.",
                                document_ref="document-01",
                                exact_span="A bounded observable event was reported.",
                            ),
                        ),
                    )
                    for case_ref in induction_refs
                ),
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="exploration_pattern",
                        disposition="refine",
                        rationale=("The extracted pattern needs more cases.",),
                    ),
                ),
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"exploration_news_{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} reported: "
                            "A bounded observable event was reported."
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(len(cases)),
            )

            result = engine._run_signal_mining(cycle_id=3)

            e1_payload, e2_payload = mining_model.requests
            self.assertNotIn('"label"', json.dumps(e1_payload))
            self.assertEqual(
                {item["label"] for item in e2_payload["signatures"]},
                {"positive", "control"},
            )
            self.assertEqual(
                result["refined_hypotheses"]["exploration_pattern"],
                ("The extracted pattern needs more cases.",),
            )

    def test_exploration_does_not_call_e2_when_one_group_lacks_grounding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                [make_case(f"explore_positive_{index}", 4.0) for index in range(4)]
                + [make_case(f"explore_control_{index}", 1.1) for index in range(4)]
            )
            selection = exploration_selection(
                cases, cycle_id=3, induction_per_class=2, validation_per_class=2
            )
            induction_refs = selection["e1_refs"]
            failed_ref = selection["e1_by_class"][True][0]
            signatures = []
            for case_ref in induction_refs:
                if case_ref == failed_ref:
                    signatures.append(
                        SignalMiningSignature(
                            case_ref=case_ref,
                            observations=(),
                            evidence_gaps=("No supportable observation was visible.",),
                        )
                    )
                else:
                    signatures.append(
                        SignalMiningSignature(
                            case_ref=case_ref,
                            observations=(
                                SignalMiningObservation(
                                    summary="A bounded event was reported.",
                                    document_ref="document-01",
                                    exact_span="A bounded observable event was reported.",
                                ),
                            ),
                        )
                    )
            mining_model = ScriptedMiningModel(signatures=tuple(signatures))
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"exploration_news_{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} reported: "
                            "A bounded observable event was reported."
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(len(cases)),
            )

            result = engine._run_signal_mining(cycle_id=3)

            self.assertEqual(len(mining_model.requests), 1)
            self.assertEqual(
                result["audit"]["stages"]["E2"]["status"],
                "not_called_evidence_unavailable",
            )
            self.assertIn("exploration_evidence", result["refined_hypotheses"])

    def test_exploration_microbatch_failure_preserves_valid_siblings(self) -> None:
        class OneFailedMicrobatchModel(ScriptedMiningModel):
            def __init__(self, *, failed_ref, **kwargs):
                super().__init__(**kwargs)
                self.failed_ref = failed_ref

            def extract_exploration(self, payload):
                refs = [item["case_ref"] for item in payload["cases"]]
                if self.failed_ref in refs:
                    self.requests.append(dict(payload))
                    raise CandidateExecutionRejected(
                        "signal_mining_exploration_extract",
                        "one isolated response remained malformed",
                        AgentUsage(llm_calls=2),
                    )
                return super().extract_exploration(payload)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                [make_case(f"micro_positive_{index}", 4.0) for index in range(4)]
                + [make_case(f"micro_control_{index}", 1.1) for index in range(4)]
            )
            selection = exploration_selection(
                cases, cycle_id=3, induction_per_class=1, validation_per_class=1
            )
            failed_ref = selection["e1_by_class"][True][0]
            signatures = tuple(
                SignalMiningSignature(
                    case_ref=case_ref,
                    observations=(
                        SignalMiningObservation(
                            summary="A bounded event was reported.",
                            document_ref="document-01",
                            exact_span="A bounded observable event was reported.",
                        ),
                    ),
                )
                for case_ref in selection["e1_refs"]
            )
            mining_model = OneFailedMicrobatchModel(
                failed_ref=failed_ref,
                signatures=signatures,
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="microbatch_pattern",
                        disposition="refine",
                        rationale=("More evidence is required.",),
                    ),
                ),
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"micro-news-{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} reported: "
                            "A bounded observable event was reported."
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            config = SignalMiningConfig(
                case_pool_limit=8,
                ranking_case_limit=8,
                h2_profile_scan_limit=8,
                h2_min_ready_issuers=8,
                h2_min_ready_per_class=4,
                induction_cases_per_class=1,
                validation_cases_per_class=1,
                exploration_microbatch_size=1,
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=config,
            )

            result = engine._run_signal_mining(cycle_id=3)

            e1 = result["audit"]["stages"]["E1"]
            self.assertEqual(len(e1["microbatches"]), 4)
            self.assertEqual(e1["failures"].keys(), {failed_ref})
            self.assertEqual(len(e1["signatures"]), 3)
            self.assertIn("microbatch_pattern", result["refined_hypotheses"])
            self.assertEqual(
                result["audit"]["local_selection"]["validation_case_refs"],
                list(selection["validation_refs"]),
            )
            self.assertIn(
                f"slow_loop:exploration_e1:{failed_ref}", result["failures"]
            )

    def test_exploration_uses_bounded_same_group_evidence_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(
                [make_case(f"explore_positive_{index}", 4.0) for index in range(6)]
                + [make_case(f"explore_control_{index}", 1.1) for index in range(6)]
            )
            selection = exploration_selection(
                cases, cycle_id=3, induction_per_class=2, validation_per_class=2
            )
            e1_refs = selection["e1_refs"]
            failed_ref = selection["e1_by_class"][True][0]
            signatures = tuple(
                SignalMiningSignature(
                    case_ref=case_ref,
                    observations=(
                        ()
                        if case_ref == failed_ref
                        else (
                            SignalMiningObservation(
                                summary="A bounded event was reported.",
                                document_ref="document-01",
                                exact_span=(
                                    "A bounded observable event was reported."
                                ),
                            ),
                        )
                    ),
                    evidence_gaps=(
                        ("No supportable observation was visible.",)
                        if case_ref == failed_ref
                        else ()
                    ),
                )
                for case_ref in e1_refs
            )
            mining_model = ScriptedMiningModel(
                signatures=tuple(reversed(signatures)),
                decisions=(
                    SignalMiningDecision(
                        hypothesis_id="exploration_pattern",
                        disposition="refine",
                        rationale=("The extracted pattern needs more cases.",),
                    ),
                ),
            )
            store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"exploration_news_{index}",
                        company_id=case.company_id,
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content=(
                            f"{case.basic_info['company_name']} reported: "
                            "A bounded observable event was reported."
                        ),
                    )
                    for index, case in enumerate(cases)
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=store,
                discovery_cases=cases,
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(len(cases)),
            )

            result = engine._run_signal_mining(cycle_id=3)

            self.assertEqual(len(mining_model.requests), 2)
            grounded_by_class = {
                label: tuple(
                    ref
                    for ref in refs
                    if ref != failed_ref
                )[:2]
                for label, refs in selection["e1_by_class"].items()
            }
            expected_grounded = [
                ref
                for ref in selection["all_refs"]
                if ref in {*grounded_by_class[True], *grounded_by_class[False]}
            ]
            self.assertEqual(
                [item["case_ref"] for item in mining_model.requests[1]["signatures"]],
                expected_grounded,
            )
            self.assertEqual(
                result["audit"]["local_selection"]["validation_case_refs"],
                list(selection["validation_refs"]),
            )

    def test_exploration_reference_order_is_independent_of_outcomes(self) -> None:
        cases = tuple(
            [make_case(f"shuffle_positive_{index}", 4.0) for index in range(4)]
            + [make_case(f"shuffle_control_{index}", 1.1) for index in range(4)]
        )
        swapped = tuple(
            replace(
                case,
                ground_truth=GroundTruth(
                    1.1 if case.ground_truth.is_surge else 4.0
                ),
            )
            for case in cases
        )

        original_pairs = _exploration_case_pairs(cases, cycle_id=7)
        swapped_pairs = _exploration_case_pairs(swapped, cycle_id=7)

        self.assertEqual(
            [(ref, case.case_id) for ref, case in original_pairs],
            [(ref, case.case_id) for ref, case in swapped_pairs],
        )

    def test_exploration_rejects_a_fabricated_document_ref(self) -> None:
        signatures = (
            SignalMiningSignature(
                case_ref="case-001",
                observations=(
                    SignalMiningObservation(
                        summary="A bounded event was reported.",
                        document_ref="fabricated-document",
                        exact_span="A bounded observable event was reported.",
                    ),
                ),
            ),
        )

        with self.assertRaisesRegex(ValidationError, "unknown document_ref"):
            validate_signal_mining_signatures(
                signatures,
                (
                    {
                        "case_ref": "case-001",
                        "evidence": [
                            {
                                "document_ref": "document-01",
                                "content_excerpt": (
                                    "A bounded observable event was reported."
                                ),
                            }
                        ],
                    },
                ),
            )

    def test_exploration_rejects_a_malformed_evidence_collection(self) -> None:
        signatures = (
            SignalMiningSignature(
                case_ref="case-001",
                observations=(),
                evidence_gaps=("No supportable observation was visible.",),
            ),
        )

        with self.assertRaisesRegex(ValidationError, "evidence must be an array"):
            validate_signal_mining_signatures(
                signatures,
                ({"case_ref": "case-001", "evidence": "not-an-array"},),
            )

    def test_exploration_rejects_a_malformed_evidence_item(self) -> None:
        signatures = (
            SignalMiningSignature(
                case_ref="case-001",
                observations=(),
                evidence_gaps=("No supportable observation was visible.",),
            ),
        )

        with self.assertRaisesRegex(ValidationError, "requires content_excerpt"):
            validate_signal_mining_signatures(
                signatures,
                (
                    {
                        "case_ref": "case-001",
                        "evidence": [{"document_ref": "document-01"}],
                    },
                ),
            )

    def test_signal_learning_keeps_plan_reasons_but_dedupes_effectiveness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            for index, reason in enumerate(("test growth", "confirm growth"), start=1):
                registry.record_learning_event(
                    SignalLearningEvent(
                        event_id=f"event-{index}",
                        observation_key="same-case-input",
                        signal_ref="revenue_growth_yoy:v1",
                        round_id=1,
                        plan_id=f"plan-{index}",
                        case_id="case-1",
                        company_id="issuer-1",
                        prediction_time=NOW.isoformat(),
                        selection={
                            "signal_ref": "revenue_growth_yoy:v1",
                            "reason_code": "answer_need",
                            "selection_reason": reason,
                            "applicability_hypothesis": "Comparable periods exist.",
                            "expected_role": "primary",
                            "context_tags": ["comparable_financials"],
                        },
                        result_value=SignalValue.POSITIVE,
                        coverage=SignalCoverage.SUFFICIENT,
                        document_fingerprint=("doc-hash",),
                        is_surge=True,
                        realized_max_multiple=3.0,
                        prediction_correct=True,
                    )
                )

            events = registry.load_learning_events("revenue_growth_yoy:v1")
            profile = registry.load_learning_profile("revenue_growth_yoy:v1")
            self.assertEqual(len(events), 2)
            self.assertEqual(
                {event.selection["selection_reason"] for event in events},
                {"test growth", "confirm growth"},
            )
            self.assertEqual(profile["selection_events"], 2)
            self.assertEqual(profile["unique_observations"], 1)
            self.assertNotIn("test growth", json.dumps(profile))
            self.assertNotIn("plan-1", json.dumps(profile))
            self.assertNotIn("case-1", json.dumps(profile))
            self.assertEqual(
                profile["state_outcome_matrix"]["positive"]["surge"], 1
            )
            cycle_start = registry.freeze(learning_round_cutoff=0)
            resumed_same_cycle = registry.freeze(learning_round_cutoff=0)
            next_cycle = registry.freeze(learning_round_cutoff=1)
            self.assertEqual(cycle_start.learning_hash, resumed_same_cycle.learning_hash)
            self.assertNotEqual(cycle_start.learning_hash, next_cycle.learning_hash)
            self.assertEqual(
                cycle_start.learned_profiles["revenue_growth_yoy:v1"][
                    "unique_observations"
                ],
                0,
            )

    def test_slow_loop_context_cannot_access_locked_test(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            mining_model = EmptyMiningModel()
            update_model = NoChangeUpdateModel()
            raw_store = RawInfoStore(
                documents=(
                    RawInfoDocument.create(
                        document_id="discovery_doc",
                        company_id="discovery_only",
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content="start " + ("evidence " * 2_000) + "end",
                    ),
                    RawInfoDocument.create(
                        document_id="locked_doc",
                        company_id="locked_company",
                        source_type="news",
                        published_at=NOW,
                        available_at=NOW,
                        content="Locked evidence.",
                    ),
                )
            )
            engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=raw_store,
                discovery_cases=(make_case("discovery_only", 3.0),),
                meta_memory=PlanMetaMemory(),
                workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=mining_model,
                update_model=update_model,
                llm_signal_runner=None,
            )
            validation = engine._validate_cycle(registry.freeze())
            mining_workspace = engine._mining_context(cycle_id=1)
            serialized = json.dumps(mining_workspace)
            self.assertNotIn("locked_company", serialized)
            self.assertFalse(mining_workspace["locked_test_available"])
            self.assertIn("capability_backlog", mining_workspace)
            self.assertTrue(
                all(
                    "learned_profile" not in card
                    for card in mining_workspace["stable_signal_cards"]
                )
            )
            self.assertTrue(
                all(
                    "learned_profile" in card.to_dict()
                    for category in registry.list_categories()
                    for card in registry.list_signal_cards(category)
                )
            )
            self.assertEqual(update_model.requests, [])
            self.assertEqual(
                validation.agent_audits["update_pipeline"]["disposition"],
                "no_actionable_target",
            )

    def test_h1_card_projection_retains_nonempty_learned_profile(self) -> None:
        card = {
            "signal_ref": "revenue_growth_yoy:v1",
            "learned_profile": {
                "selection_events": 1,
                "unique_observations": 0,
                "directional": {"correct": 0, "wrong": 0},
            },
        }

        view = SignalEvolutionEngine._mining_signal_card_view(card)

        self.assertEqual(view, card)
        self.assertIn("learned_profile", view)


class DualLoopTests(TestCase):
    def test_slow_bootstrap_runs_no_fast_round_and_preserves_round_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            snapshot = registry.freeze()
            workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=0,
                cycle_mode="slow_bootstrap",
                initial_signal_registry_version=snapshot.version,
                initial_signal_registry_hash=snapshot.registry_hash,
                observed_signal_registry_version=snapshot.version,
                observed_signal_registry_hash=snapshot.registry_hash,
            )
            meta = PlanMetaMemory()
            proposer = CountingProposer()
            evaluator = SyntheticPlanEvaluator(include_signal=False)
            plan_engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=meta,
                signal_registry=registry,
                evaluator=evaluator,
                proposer=proposer,
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
            )
            mining_model = EmptyMiningModel()
            signal_engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("discovery_case", 4.0),),
                meta_memory=meta,
                workspace=workspace,
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )
            dataset = EvolutionDataset(
                discovery=(make_case("discovery_case", 4.0),),
                anchor=make_anchor_pool(),
                evolution_validation=make_evaluation_pool(),
                locked_test=(make_case("locked_company", 12.0),),
            )
            progress_events = []

            result = DualLoopEvolutionEngine(
                plan_engine=plan_engine,
                signal_engine=signal_engine,
                signal_registry=registry,
                dataset=dataset,
                plan_rounds_per_signal_cycle=0,
                cycle_mode="slow_bootstrap",
                on_progress=progress_events.append,
            ).run_cycle(cycle_id=1)

            self.assertEqual(result.plan_rounds, ())
            self.assertEqual(proposer.calls, [])
            self.assertEqual(evaluator.seen_company_ids, [])
            self.assertEqual(workspace.last_completed_round, 0)
            self.assertEqual(len(mining_model.requests), 0)
            event_types = [item["event_type"] for item in progress_events]
            self.assertNotIn("fast_loop_started", event_types)
            self.assertIn("slow_loop_started", event_types)

    def test_offline_dual_loop_freezes_signals_then_runs_one_slow_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            snapshot = registry.freeze()
            workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=1,
                initial_signal_registry_version=snapshot.version,
                initial_signal_registry_hash=snapshot.registry_hash,
                observed_signal_registry_version=snapshot.version,
                observed_signal_registry_hash=snapshot.registry_hash,
            )
            meta = PlanMetaMemory()
            proposer = CountingProposer()
            evaluator = SyntheticPlanEvaluator(include_signal=False)
            plan_engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=meta,
                signal_registry=registry,
                evaluator=evaluator,
                proposer=proposer,
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
            )
            mining_model = EmptyMiningModel()
            signal_engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("discovery_case", 4.0),),
                meta_memory=meta,
                workspace=workspace,
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )
            dataset = EvolutionDataset(
                discovery=(make_case("discovery_case", 4.0),),
                anchor=make_anchor_pool(),
                evolution_validation=make_evaluation_pool(),
                locked_test=(make_case("locked_company", 12.0),),
            )
            result = DualLoopEvolutionEngine(
                plan_engine=plan_engine,
                signal_engine=signal_engine,
                signal_registry=registry,
                dataset=dataset,
                plan_rounds_per_signal_cycle=1,
            ).run_cycle(cycle_id=1)
            self.assertEqual(len(result.plan_rounds), 1)
            self.assertEqual(result.signal_evolution.promoted, ())
            self.assertEqual(workspace.last_completed_round, 1)
            self.assertEqual(len(evaluator.seen_company_ids), 24)
            self.assertEqual(len(set(evaluator.seen_company_ids)), 24)
            self.assertEqual(mining_model.requests, [])

    def test_next_cycle_uses_promoted_registry_without_reevaluating_old_plans(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            initial = registry.freeze()
            workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=1,
                initial_signal_registry_version=initial.version,
                initial_signal_registry_hash=initial.registry_hash,
                observed_signal_registry_version=initial.version,
                observed_signal_registry_hash=initial.registry_hash,
            )
            meta = PlanMetaMemory()
            proposer = CountingProposer()
            evaluator = SyntheticPlanEvaluator(include_signal=False)
            plan_engine = PlanEvolutionEngine(
                archive=PlanArchive(),
                meta_memory=meta,
                signal_registry=registry,
                evaluator=evaluator,
                proposer=proposer,
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
                run_contract_hash="contract-hash",
            )
            new_spec = SignalSpec(
                signal_id="cross_cycle_growth_quality",
                version=1,
                category="financial",
                description="Measure whether revenue growth spans disclosed segments.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            discovery_cases = tuple(
                [
                    make_case(f"discovery_positive_{index}", 4.0)
                    for index in range(4)
                ]
                + [
                    make_case(f"discovery_control_{index}", 1.1)
                    for index in range(4)
                ]
            )
            signal_store = RawInfoStore(
                documents=tuple(
                    RawInfoDocument.create(
                        document_id=f"cross_cycle_financial_{index}",
                        company_id=case.company_id,
                        source_type="financials",
                        published_at=NOW,
                        available_at=NOW,
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            (
                                "2024-01-01",
                                "2024-12-31",
                                125.0 if case.ground_truth.is_surge else 90.0,
                                "2025-01-10",
                            ),
                        ),
                    )
                    for index, case in enumerate(discovery_cases)
                )
            )
            hypothesis = SignalMiningHypothesis(
                hypothesis_id="cross_cycle_growth",
                statement="Revenue growth direction separates winners.",
                applicability="all_ready_issuers",
                expected_positive_pattern="Positive cases have stronger growth.",
                source_types=("financials",),
                query="revenue",
                falsifiers=("Controls have indistinguishable growth.",),
            )
            first_signal_engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=signal_store,
                discovery_cases=discovery_cases,
                meta_memory=meta,
                workspace=workspace,
                mining_model=ScriptedMiningModel(
                    hypotheses=(hypothesis,),
                    rankings={
                        "cross_cycle_growth": tuple(
                            f"case-{index:03d}" for index in range(1, 9)
                        )
                    },
                    decisions=(
                        SignalMiningDecision(
                            hypothesis_id="cross_cycle_growth",
                            disposition="supported",
                            rationale=("Positive and control cases separate.",),
                            candidate={
                                "spec": new_spec.to_dict(),
                                "skill": None,
                                "tests": [candidate_growth_fixture()],
                            },
                        ),
                    ),
                ),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
                mining_config=fixture_mining_config(len(discovery_cases)),
            )
            dataset = EvolutionDataset(
                discovery=discovery_cases,
                anchor=make_anchor_pool(),
                evolution_validation=make_evaluation_pool(),
                locked_test=(make_case("locked_company", 12.0),),
            )
            first = DualLoopEvolutionEngine(
                plan_engine=plan_engine,
                signal_engine=first_signal_engine,
                signal_registry=registry,
                dataset=dataset,
                plan_rounds_per_signal_cycle=1,
            ).run_cycle(cycle_id=1)
            self.assertEqual(first.signal_evolution.promoted, (new_spec.ref,))
            workspace.stage_slow_result(
                cycle_id=1,
                result=first.signal_evolution.to_dict(),
            )
            promoted_snapshot = registry.freeze()
            workspace.complete_cycle(
                cycle_id=1,
                observed_signal_registry_version=promoted_snapshot.version,
                observed_signal_registry_hash=promoted_snapshot.registry_hash,
            )
            old_record = plan_engine.archive.records[0]
            old_f1 = old_record.metrics.binary_f1

            second_cycle = workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=1,
                initial_signal_registry_version=initial.version,
                initial_signal_registry_hash=initial.registry_hash,
                observed_signal_registry_version=promoted_snapshot.version,
                observed_signal_registry_hash=promoted_snapshot.registry_hash,
            )
            second_signal_engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("discovery_case", 4.0),),
                meta_memory=meta,
                workspace=workspace,
                mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )
            second = DualLoopEvolutionEngine(
                plan_engine=plan_engine,
                signal_engine=second_signal_engine,
                signal_registry=registry,
                dataset=dataset,
                plan_rounds_per_signal_cycle=1,
            ).run_cycle(cycle_id=int(second_cycle["cycle_id"]))

            self.assertNotIn(new_spec.ref, evaluator.seen_registry_refs[0])
            self.assertIn(new_spec.ref, evaluator.seen_registry_refs[1])
            self.assertEqual(len(evaluator.seen_registry_refs), 2)
            self.assertEqual(len(evaluator.seen_company_ids), 48)
            self.assertEqual(len(plan_engine.archive.records), 2)
            self.assertEqual(old_record.metrics.binary_f1, old_f1)
            self.assertIn(old_record.plan_id, proposer.calls[1]["parents"])
            round_one_checkpoint = json.loads(
                (
                    workspace.experiments_root
                    / "round-0001"
                    / "checkpoint.json"
                ).read_text(encoding="utf-8")
            )
            round_two_checkpoint = json.loads(
                (
                    workspace.experiments_root
                    / "round-0002"
                    / "checkpoint.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(round_one_checkpoint["signal_registry_version"], 1)
            self.assertEqual(round_two_checkpoint["signal_registry_version"], 2)
            self.assertEqual(second.signal_evolution.output_registry_version, 2)

    def test_dual_loop_resume_runs_only_remaining_fast_rounds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            snapshot = registry.freeze()
            workspace.start_or_resume_cycle(
                run_contract_hash="contract-hash",
                target_plan_rounds=2,
                initial_signal_registry_version=snapshot.version,
                initial_signal_registry_hash=snapshot.registry_hash,
                observed_signal_registry_version=snapshot.version,
                observed_signal_registry_hash=snapshot.registry_hash,
            )
            committed = make_record(
                "plan_committed",
                0.75,
                HashingPlanEmbedder().embed(default_information_plan()),
                round_id=1,
            )
            workspace.commit_round(
                round_id=1,
                records=(committed,),
                meta_entry=RoundMetaEntry(
                    round_id=1,
                    evidence_refs=(committed.plan_id,),
                ),
                signal_registry_version=registry.version,
                signal_registry_hash=snapshot.registry_hash,
                run_contract_hash="contract-hash",
            )
            meta = workspace.restore_meta()
            proposer = CountingProposer()
            evaluator = SyntheticPlanEvaluator(include_signal=False)
            plan_engine = PlanEvolutionEngine(
                archive=workspace.restore_archive(),
                meta_memory=meta,
                signal_registry=registry,
                evaluator=evaluator,
                proposer=proposer,
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=1,
            )
            mining_model = EmptyMiningModel()
            signal_engine = SignalEvolutionEngine(
                registry=registry,
                raw_info_store=RawInfoStore(),
                discovery_cases=(make_case("discovery_case", 4.0),),
                meta_memory=meta,
                workspace=workspace,
                mining_model=mining_model,
                update_model=NoChangeUpdateModel(),
                llm_signal_runner=None,
            )
            dataset = EvolutionDataset(
                discovery=(make_case("discovery_case", 4.0),),
                anchor=make_anchor_pool(),
                evolution_validation=make_evaluation_pool(),
                locked_test=(make_case("locked_company", 12.0),),
            )

            result = DualLoopEvolutionEngine(
                plan_engine=plan_engine,
                signal_engine=signal_engine,
                signal_registry=registry,
                dataset=dataset,
                plan_rounds_per_signal_cycle=2,
            ).run_cycle(cycle_id=1, completed_plan_rounds=1)

            self.assertEqual([item.round_id for item in result.plan_rounds], [2])
            self.assertEqual(workspace.last_completed_round, 2)
            self.assertEqual(len(proposer.calls), 1)
            self.assertEqual(len(result.plan_rounds[0].records), 1)
            self.assertFalse(
                (workspace.evaluation_root / "round_002" / "champion.json").exists()
            )
            self.assertEqual(len(evaluator.seen_company_ids), 24)
