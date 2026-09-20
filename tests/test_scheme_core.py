"""Core Raw Info, generic-agent, and Signal Library tests."""

from tests.scheme_evolution_test_support import *  # noqa: F403


class RawInfoStoreTests(TestCase):
    def test_refresh_reuses_unchanged_files_but_detects_same_size_rewrite(self) -> None:
        import os
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            store = RawInfoStore(directory)
            document = RawInfoDocument.create(
                document_id="cached_doc", company_id="issuer_1",
                source_type="filing", published_at=NOW, available_at=NOW,
                content="Original filing.", metadata={"accession": "0001"},
            )
            store.append(document)
            store.refresh()
            with patch.object(Path, "read_text", side_effect=AssertionError("reparsed")):
                self.assertEqual(store.refresh(), 0)
                self.assertFalse(store.append(document))
            path = Path(directory) / "filing" / "issuer_1" / "cached_doc.json"
            stat = path.stat()
            path.write_text(path.read_text().replace('"0001"', '"0002"'))
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            with self.assertRaisesRegex(ValidationError, "different content or provenance"):
                store.refresh()

    def test_append_only_store_filters_by_available_at_and_reloads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RawInfoStore(directory)
            visible = RawInfoDocument.create(
                document_id="doc_visible",
                company_id="issuer_1",
                source_type="financials",
                published_at=NOW - timedelta(days=2),
                available_at=NOW - timedelta(days=1),
                content="Revenue grew 25 percent year over year.",
                metadata={"revenue_growth_yoy": 0.25},
            )
            future = RawInfoDocument.create(
                document_id="doc_future",
                company_id="issuer_1",
                source_type="financials",
                published_at=NOW + timedelta(days=1),
                available_at=NOW + timedelta(days=1),
                content="Future quarter revenue grew 80 percent.",
                metadata={"revenue_growth_yoy": 0.8},
            )
            self.assertTrue(store.append(visible))
            self.assertFalse(store.append(visible))
            store.append(future)
            self.assertEqual(
                [item.document_id for item in store.search("issuer_1", as_of=NOW)],
                ["doc_visible"],
            )
            with self.assertRaisesRegex(ValidationError, "not available"):
                store.load("doc_future", as_of=NOW)
            reloaded = RawInfoStore(directory)
            self.assertEqual(len(reloaded.documents), 2)
            self.assertEqual(reloaded.load("doc_visible"), visible)

    def test_file_backed_instances_refresh_and_concurrent_replay_is_idempotent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = RawInfoStore(directory)
            stale = RawInfoStore(directory)
            document = RawInfoDocument.create(
                document_id="shared_doc",
                company_id="issuer_1",
                source_type="filing",
                published_at=NOW,
                available_at=NOW,
                content="The same canonical filing body.",
                metadata={"accession": "0001"},
            )

            self.assertTrue(first.append(document))
            self.assertEqual(stale.documents, ())
            self.assertFalse(stale.append(document))
            self.assertEqual(stale.load(document.document_id), document)

            later = RawInfoDocument.create(
                document_id="later_doc",
                company_id="issuer_1",
                source_type="news",
                published_at=NOW,
                available_at=NOW,
                content="A later source became available.",
            )
            first.append(later)
            self.assertEqual(stale.refresh(), 1)
            self.assertEqual(stale.load(later.document_id), later)

    def test_file_backed_document_id_is_unique_across_canonical_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = RawInfoStore(directory)
            second = RawInfoStore(directory)
            first.append(
                RawInfoDocument.create(
                    document_id="global_id",
                    company_id="issuer_1",
                    source_type="filing",
                    published_at=NOW,
                    available_at=NOW,
                    content="Original filing.",
                )
            )
            conflicting = RawInfoDocument.create(
                document_id="global_id",
                company_id="issuer_2",
                source_type="news",
                published_at=NOW,
                available_at=NOW,
                content="Conflicting source and issuer.",
            )

            with self.assertRaisesRegex(ValidationError, "different content or provenance"):
                second.append(conflicting)
            self.assertFalse(
                (Path(directory) / "news" / "issuer_2" / "global_id.json").exists()
            )

    def test_raw_info_snapshot_does_not_change_after_backing_store_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RawInfoStore(directory)
            first = RawInfoDocument.create(
                document_id="snapshot_first",
                company_id="issuer_1",
                source_type="filing",
                published_at=NOW,
                available_at=NOW,
                content="First document.",
            )
            store.append(first)
            snapshot = store.snapshot()
            store.append(
                RawInfoDocument.create(
                    document_id="snapshot_second",
                    company_id="issuer_1",
                    source_type="filing",
                    published_at=NOW,
                    available_at=NOW,
                    content="Second document.",
                )
            )

            self.assertEqual(snapshot.documents, (first,))

    def test_store_rejects_conflicting_id_hash_and_path_traversal(self) -> None:
        valid = RawInfoDocument.create(
            document_id="doc_1",
            company_id="issuer_1",
            source_type="news",
            published_at=NOW,
            available_at=NOW,
            content="A sourced event occurred.",
        )
        store = RawInfoStore(documents=(valid,))
        conflicting = RawInfoDocument.create(
            document_id="doc_1",
            company_id="issuer_1",
            source_type="news",
            published_at=NOW,
            available_at=NOW,
            content="Different content.",
        )
        with self.assertRaisesRegex(ValidationError, "different content"):
            store.append(conflicting)
        with self.assertRaisesRegex(ValidationError, "content_hash"):
            RawInfoDocument(
                document_id="doc_2",
                company_id="issuer_1",
                source_type="news",
                published_at=NOW,
                available_at=NOW,
                content="content",
                content_hash=content_sha256("other"),
            )
        with self.assertRaisesRegex(ValidationError, "safe identifier"):
            RawInfoDocument.create(
                document_id="../escape",
                company_id="issuer_1",
                source_type="news",
                published_at=NOW,
                available_at=NOW,
                content="content",
            )

    def test_hidden_outcome_metadata_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "forbidden outcome"):
            RawInfoDocument.create(
                document_id="leaking_doc",
                company_id="issuer_1",
                source_type="financials",
                published_at=NOW,
                available_at=NOW,
                content="Contemporaneous financial statement.",
                metadata={"analysis": {"realized_max_multiple": 4.0}},
            )


class GenericAgentTests(TestCase):
    def test_external_approval_pause_propagates_through_tool_boundary(self) -> None:
        model = ScriptedAgentModel(
            [AgentTurn(tool_call=ToolCall("lookup", {}))]
        )

        def pause() -> None:
            raise ExternalRequestPending("a" * 64, Path("request.json"))

        with self.assertRaises(ExternalRequestPending):
            GenericAgent(model).run(
                prompt="fixture",
                tools=(DomainTool("lookup", "fixture lookup", pause),),
                workspace={},
                output_schema=lambda value: value,
                max_steps=1,
            )

    def test_agent_uses_only_granted_domain_tools_and_validates_output(self) -> None:
        model = ScriptedAgentModel(
            [
                AgentTurn(tool_call=ToolCall("lookup", {"key": "x"})),
                AgentTurn(final_output={"answer": 4}),
            ]
        )
        result = GenericAgent(model).run(
            prompt="Use the domain tool and return an integer answer.",
            tools=(DomainTool("lookup", "Look up one fixture value.", lambda key: 4),),
            workspace={"scope": "fixture"},
            output_schema=lambda value: int(value["answer"]),
            max_steps=2,
        )
        self.assertEqual(result.value, 4)
        self.assertEqual(result.observations[0].result, 4)
        self.assertEqual(result.usage.llm_calls, 2)
        self.assertNotIn("cat", {card["name"] for card in model.requests[0].tool_cards})

    def test_agent_exposes_tool_signature_and_returns_argument_error_for_repair(self) -> None:
        model = ScriptedAgentModel(
            [
                AgentTurn(tool_call=ToolCall("lookup", {})),
                AgentTurn(final_output={"answer": 4}),
            ]
        )

        result = GenericAgent(model).run(
            prompt="Use the domain tool and repair invalid arguments.",
            tools=(DomainTool("lookup", "Look up a value.", lambda key: 4),),
            workspace={"scope": "fixture"},
            output_schema=lambda value: int(value["answer"]),
            max_steps=2,
        )

        self.assertIn("key", model.requests[0].tool_cards[0]["arguments"])
        self.assertEqual(
            model.requests[0].tool_cards[0]["arguments_schema"]["required"],
            ["key"],
        )
        self.assertEqual(
            result.observations[0].result,
            {"error": "invalid_arguments", "expected": "(key)"},
        )
        self.assertEqual(model.requests[1].observations, result.observations)

    def test_agent_returns_domain_validation_error_for_bounded_repair(self) -> None:
        def validate_as_of(as_of: str) -> int:
            raise ValidationError("as_of must be timezone-aware")

        model = ScriptedAgentModel(
            [
                AgentTurn(
                    tool_call=ToolCall("lookup", {"as_of": "2025-01-15"})
                ),
                AgentTurn(final_output={"answer": 4}),
            ]
        )

        result = GenericAgent(model).run(
            prompt="Use the domain tool and repair invalid values.",
            tools=(DomainTool("lookup", "Look up a value.", validate_as_of),),
            workspace={"scope": "fixture"},
            output_schema=lambda value: int(value["answer"]),
            max_steps=2,
        )

        self.assertEqual(
            result.observations[0].result,
            {
                "error": "tool_validation",
                "message": "as_of must be timezone-aware",
            },
        )
        self.assertEqual(model.requests[1].observations, result.observations)

    def test_agent_returns_output_validation_error_for_bounded_repair(self) -> None:
        def parse_answer(value):
            if not isinstance(value, dict):
                raise ValidationError("final output must be an object")
            return int(value["answer"])

        model = ScriptedAgentModel(
            [
                AgentTurn(final_output='{"answer": 4}'),
                AgentTurn(final_output={"answer": 4}),
            ]
        )

        result = GenericAgent(model).run(
            prompt="Return a validated object.",
            tools=(),
            workspace={"scope": "fixture"},
            output_schema=parse_answer,
            max_steps=2,
        )

        self.assertEqual(result.value, 4)
        self.assertEqual(
            result.observations[0].result,
            {
                "error": "output_validation",
                "message": "final output must be an object",
            },
        )
        self.assertEqual(model.requests[1].observations, result.observations)

    def test_agent_returns_completion_validation_error_for_workflow_repair(self) -> None:
        model = ScriptedAgentModel(
            [
                AgentTurn(final_output={"answer": 4}),
                AgentTurn(tool_call=ToolCall("lookup", {"key": "x"})),
                AgentTurn(final_output={"answer": 4}),
            ]
        )

        def require_lookup(value, observations):
            if not any(item.name == "lookup" for item in observations):
                raise ValidationError("lookup must run before final output")

        result = GenericAgent(model).run(
            prompt="Use the required workflow.",
            tools=(DomainTool("lookup", "Look up a value.", lambda key: 4),),
            workspace={},
            output_schema=lambda value: int(value["answer"]),
            completion_validator=require_lookup,
            max_steps=3,
        )

        self.assertEqual(result.value, 4)
        self.assertEqual(
            result.observations[0].result,
            {
                "error": "output_validation",
                "message": "lookup must run before final output",
            },
        )
        self.assertEqual(result.observations[1].name, "lookup")

    def test_agent_rejects_ungranted_or_raw_tools_and_step_exhaustion(self) -> None:
        with self.assertRaisesRegex(ValidationError, "not allowed"):
            DomainTool("rm", "Remove anything.", lambda: None)
        model = ScriptedAgentModel(
            [AgentTurn(tool_call=ToolCall("not_granted", {}))]
        )
        with self.assertRaisesRegex(ValidationError, "ungranted"):
            GenericAgent(model).run(
                prompt="test",
                tools=(),
                workspace={},
                output_schema=lambda value: value,
                max_steps=1,
            )
        looping = ScriptedAgentModel(
            [AgentTurn(tool_call=ToolCall("lookup", {}))]
        )
        with self.assertRaisesRegex(ValidationError, "exhausted"):
            GenericAgent(looping).run(
                prompt="test",
                tools=(DomainTool("lookup", "fixture lookup", lambda: 1),),
                workspace={},
                output_schema=lambda value: value,
                max_steps=1,
            )


class SignalLibraryTests(TestCase):
    def _registry(self, directory: str) -> SignalRegistry:
        registry = SignalRegistry(Path(directory) / "signals")
        self.assertEqual(registry.install_catalog(SEED_CATALOG), 14)
        return registry

    def test_unavailable_signal_result_rejects_placeholder_evidence(self) -> None:
        with self.assertRaisesRegex(ValidationError, "cannot carry evidence"):
            SignalResult(
                signal_id="customer_concentration",
                version=1,
                value=SignalValue.UNAVAILABLE,
                confidence=0.5,
                interpretation="No relevant concentration disclosure was visible.",
                supporting_evidence=(
                    SignalEvidence(
                        document_id="filing-1",
                        exact_span="Routine filing cover-page text.",
                        timestamp=NOW,
                    ),
                ),
                coverage=SignalCoverage.UNAVAILABLE,
            )

    def test_seed_catalog_progressive_disclosure_and_frozen_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            self.assertEqual(len(registry.list_signal_cards()), 14)
            self.assertIn("financial", registry.list_categories())
            cards = registry.search_signal_cards("customer")
            self.assertTrue(cards)
            self.assertEqual(cards[0].to_dict()["signal_ref"], cards[0].ref)
            self.assertFalse(registry.search_signal_cards("market cap"))
            with self.assertRaises(ValidationError):
                registry.load_spec("pilot_to_volume:v1")
            spec = registry.load_spec("guidance_acceleration:v1")
            self.assertEqual(spec.execution_type, SignalExecutionType.LLM)
            self.assertIn("guidance", registry.load_skill(spec.ref))
            self.assertIn(
                "guidance",
                spec.parameters["result_required_evidence_phrases"],
            )
            self.assertIn(
                "guidance updates",
                spec.parameters["routing_need_phrases"],
            )
            with self.assertRaisesRegex(ValidationError, "multiword"):
                replace(
                    spec,
                    parameters={
                        **spec.parameters,
                        "routing_need_phrases": ["guidance"],
                    },
                )
            snapshot = registry.freeze()
            v2 = SignalSpec(
                signal_id="revenue_growth_yoy",
                version=2,
                category="financial",
                description="Measure audited year-over-year revenue growth.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            registry.register_stable(v2)
            self.assertEqual(registry.latest_spec("revenue_growth_yoy").version, 2)
            self.assertEqual(snapshot.load_spec("revenue_growth_yoy:v1").version, 1)
            with self.assertRaisesRegex(ValidationError, "unknown frozen"):
                snapshot.load_spec("revenue_growth_yoy:v2")

    def test_v20_commercialization_signal_excludes_mature_operations(self) -> None:
        fixture = json.loads(
            (
                PROJECT_ROOT
                / "tests"
                / "fixtures"
                / "scheme_evolution"
                / "v20_commercialization_mature_operations.json"
            ).read_text()
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            card = next(
                item
                for item in registry.list_signal_cards()
                if item.ref == fixture["signal_ref"]
            )
            skill = registry.load_skill(fixture["signal_ref"])
            spec = registry.load_spec(fixture["signal_ref"])

        self.assertIn("mature operations", card.description)
        self.assertIn("already mature mine", skill)
        self.assertIn("return unavailable with empty evidence", skill)
        self.assertEqual(
            spec.parameters["routing_excluded_context_tags"],
            ["mature_operations"],
        )
        self.assertEqual(fixture["actual_bad_output"]["state"]["value"], "positive")
        self.assertEqual(fixture["expected_value"], "unavailable")

    def test_signal_routing_exclusions_require_unique_frozen_tags(self) -> None:
        with self.assertRaisesRegex(
            ValidationError, "routing_excluded_context_tags"
        ):
            SignalSpec(
                signal_id="bad_routing_exclusion",
                version=1,
                category="product",
                description="Reject invalid routing exclusions.",
                execution_type=SignalExecutionType.LLM,
                skill_file="skill.md",
                source_types=("filing",),
                parameters={
                    "routing_excluded_context_tags": ["mature_operations", "unknown"]
                },
            )

    def test_order_quality_requires_version_owned_research_phrases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            spec = registry.load_spec("order_quality:v1")

        self.assertEqual(
            spec.parameters["routing_required_research_phrases"],
            [
                "purchase order",
                "purchase orders",
                "customer order",
                "customer orders",
                "order backlog",
                "funded backlog",
                "contract award",
                "customer commitment",
            ],
        )
        with self.assertRaisesRegex(
            ValidationError, "routing_required_research_phrases"
        ):
            SignalSpec(
                signal_id="bad_required_research_phrase",
                version=1,
                category="orders",
                description="Reject empty routing context requirements.",
                execution_type=SignalExecutionType.LLM,
                skill_file="skill.md",
                source_types=("filing",),
                parameters={"routing_required_research_phrases": []},
            )

    def test_commercialization_requires_version_owned_product_phrases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            spec = registry.load_spec("commercialization_status:v1")

        self.assertEqual(
            spec.parameters["routing_required_research_phrases"],
            [
                "product",
                "technology",
                "prototype",
                "commercialization",
                "commercial launch",
                "commercially available",
                "sellable",
                "repeatable",
            ],
        )

    def test_customer_concentration_owns_direct_need_and_result_phrases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            spec = registry.load_spec("customer_concentration:v1")

        self.assertIn(
            "one customer",
            spec.parameters["routing_answer_need_phrases"],
        )
        self.assertIn(
            "customer",
            spec.parameters["result_required_evidence_phrases"],
        )
        with self.assertRaisesRegex(
            ValidationError, "routing_answer_need_phrases"
        ):
            SignalSpec(
                signal_id="bad_answer_need_phrase",
                version=1,
                category="risks",
                description="Reject empty direct-need phrase requirements.",
                execution_type=SignalExecutionType.LLM,
                skill_file="skill.md",
                source_types=("filing",),
                parameters={"routing_answer_need_phrases": []},
            )

    def test_empty_registry_cannot_be_frozen_for_an_evolution_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")

            with self.assertRaisesRegex(ValidationError, "empty stable Signal"):
                registry.freeze()

    def test_frozen_registry_deeply_isolates_specs_and_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            snapshot = registry.freeze()
            original_hash = snapshot.registry_hash
            original_learning_hash = snapshot.learning_hash
            spec = snapshot.load_spec("guidance_acceleration:v1")

            with self.assertRaisesRegex(TypeError, "cannot be mutated"):
                spec.parameters["routing_need_phrases"].append("mutated phrase")
            with self.assertRaisesRegex(TypeError, "cannot be mutated"):
                snapshot.learned_profiles[spec.ref]["new_key"] = "mutated"

            detached = spec.to_dict()
            detached["parameters"]["routing_need_phrases"].append(
                "detached mutation"
            )
            self.assertNotIn(
                "detached mutation",
                snapshot.load_spec(spec.ref).parameters["routing_need_phrases"],
            )
            self.assertEqual(snapshot.registry_hash, original_hash)
            self.assertEqual(snapshot.learning_hash, original_learning_hash)

    def test_rejected_next_version_can_be_repaired_without_erasing_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = self._registry(directory)
            rejected = SignalSpec(
                signal_id="revenue_growth_yoy",
                version=2,
                category="financial",
                description="Rejected revenue-growth draft.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            registry.stage_candidate(
                rejected,
                tests=(candidate_growth_fixture(),),
                origin="cycle-1-update",
            )
            rejected_hash = registry.candidate_hash(rejected.ref)
            registry.record_candidate_validation(
                rejected.ref,
                candidate_hash=rejected_hash,
                evaluation_identity={
                    "baseline_hash": "0" * 64,
                    "cohort_hash": "1" * 64,
                    "source_manifest_hash": "2" * 64,
                    "projection_hash": "3" * 64,
                    "validator_hash": "4" * 64,
                    "model_hash": "5" * 64,
                    "sampling_hash": "6" * 64,
                },
                accepted=False,
                reasons=("fixture failed",),
                effectiveness={
                    "accepted": False,
                    "disposition": "rejected",
                },
            )
            repaired = SignalSpec(
                signal_id="revenue_growth_yoy",
                version=2,
                category="financial",
                description="Repaired point-in-time revenue growth.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )

            registry.stage_candidate(
                repaired,
                tests=(candidate_growth_fixture(),),
                origin="cycle-2-update",
            )

            active, _skill = registry.load_candidate(repaired.ref)
            self.assertEqual(active, repaired)
            archived = list(
                (root / "signals_candidates" / ".rejected").glob(
                    "financial/revenue_growth_yoy/v2/*/evaluations/*.json"
                )
            )
            self.assertEqual(len(archived), 1)
            self.assertEqual(
                json.loads(archived[0].read_text(encoding="utf-8"))["candidate_hash"],
                rejected_hash,
            )

    def test_stage_candidate_rejects_same_id_under_second_category(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            first = SignalSpec(
                signal_id="order_confirmation_disclosed",
                version=1,
                category="narrative_event",
                description="Narrative order-confirmation disclosure.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.cash_reserves",
                source_types=("filing",),
            )
            registry.stage_candidate(first, tests=(candidate_growth_fixture(),), origin="seed-a")
            replay = registry.stage_candidate(
                first, tests=(candidate_growth_fixture(),), origin="seed-a"
            )
            self.assertEqual(replay, first.ref)

            colliding = SignalSpec(
                **{
                    **first.__dict__,
                    "category": "commercial_activity",
                    "description": "Same observable re-filed under a new category.",
                }
            )
            with self.assertRaisesRegex(
                ValidationError,
                "already staged under category narrative_event",
            ):
                registry.stage_candidate(
                    colliding,
                    tests=(candidate_growth_fixture(),),
                    origin="seed-b",
                )
            self.assertEqual(
                len(
                    list(
                        registry.candidate_root.glob(
                            "*/order_confirmation_disclosed"
                        )
                    )
                ),
                1,
            )

    def test_candidate_keeps_multiple_immutable_evaluations_and_latest_pointer(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            candidate = SignalSpec(
                signal_id="revenue_growth_yoy",
                version=2,
                category="financial",
                description="Re-evaluate revenue growth when evidence expands.",
                execution_type=SignalExecutionType.DETERMINISTIC,
                function="financial.revenue_growth_yoy",
                source_types=("financials",),
            )
            registry.stage_candidate(
                candidate,
                tests=(candidate_growth_fixture(),),
                origin="cycle-1-update",
            )
            candidate_hash = registry.candidate_hash(candidate.ref)
            base_identity = {
                "baseline_hash": "0" * 64,
                "cohort_hash": "1" * 64,
                "source_manifest_hash": "2" * 64,
                "projection_hash": "3" * 64,
                "validator_hash": "4" * 64,
                "model_hash": "5" * 64,
                "sampling_hash": "6" * 64,
            }
            provisional_key = registry.record_candidate_validation(
                candidate.ref,
                candidate_hash=candidate_hash,
                evaluation_identity=base_identity,
                accepted=False,
                reasons=("insufficient independent cases",),
                effectiveness={
                    "accepted": False,
                    "disposition": "provisional",
                },
            )
            expanded_identity = {
                **base_identity,
                "source_manifest_hash": "7" * 64,
            }
            accepted_key = registry.record_candidate_validation(
                candidate.ref,
                candidate_hash=candidate_hash,
                evaluation_identity=expanded_identity,
                accepted=True,
                reasons=(),
                effectiveness={
                    "accepted": True,
                    "disposition": "promoted",
                },
            )

            self.assertNotEqual(provisional_key, accepted_key)
            self.assertEqual(len(registry.list_candidate_evaluations(candidate.ref)), 2)
            self.assertEqual(
                registry.load_candidate_validation(candidate.ref)["evaluation_key"],
                accepted_key,
            )
            self.assertEqual(
                registry.load_candidate_validation(
                    candidate.ref,
                    evaluation_key=provisional_key,
                )["status"],
                "provisional",
            )
            snapshot = registry.freeze()
            with self.assertRaisesRegex(
                ValidationError, "matching successful validation"
            ):
                registry.promote_validated_batch(
                    {candidate.ref: candidate_hash},
                    validated_evaluations={candidate.ref: provisional_key},
                    transition_id="cycle-provisional",
                    input_version=snapshot.version,
                    input_hash=snapshot.registry_hash,
                    input_refs=tuple(spec.ref for spec in snapshot.specs),
                )
            transition = registry.promote_validated_batch(
                {candidate.ref: candidate_hash},
                validated_evaluations={candidate.ref: accepted_key},
                transition_id="cycle-accepted",
                input_version=snapshot.version,
                input_hash=snapshot.registry_hash,
                input_refs=tuple(spec.ref for spec in snapshot.specs),
            )
            self.assertEqual(transition.promoted, (candidate.ref,))
            promotion = json.loads(
                (
                    Path(directory)
                    / "signals_candidates"
                    / candidate.category
                    / candidate.signal_id
                    / f"v{candidate.version}"
                    / "promotion.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(promotion["evaluation_key"], accepted_key)

    def test_batch_promotion_fails_closed_and_recovers_exact_prepared_transition(
        self,
    ) -> None:
        fault_stages = (
            "after_transition_prepared",
            "after_stable_spec",
            "after_stable_tests",
            "after_stable_skill",
            "after_stable_stats",
            "after_stable_manifest",
            "after_registry_version",
            "before_output_snapshot",
            "after_output_snapshot",
            "after_promotion_record",
            "before_transition_applied",
        )
        for fault_stage in fault_stages:
            with self.subTest(fault_stage=fault_stage), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                registry = self._registry(directory)
                snapshot = registry.freeze()
                candidates = (
                    SignalSpec(
                        signal_id="recoverable_growth_deterministic",
                        version=1,
                        category="financial",
                        description="Recoverable deterministic growth candidate.",
                        execution_type=SignalExecutionType.DETERMINISTIC,
                        function="financial.revenue_growth_yoy",
                        source_types=("financials",),
                    ),
                    SignalSpec(
                        signal_id="recoverable_growth_llm",
                        version=1,
                        category="financial",
                        description="Recoverable LLM growth candidate.",
                        execution_type=SignalExecutionType.LLM,
                        skill_file="skill.md",
                        source_types=("financials",),
                    ),
                )
                candidate_hashes: dict[str, str] = {}
                evaluation_keys: dict[str, str] = {}
                for index, candidate in enumerate(candidates):
                    registry.stage_candidate(
                        candidate,
                        skill=(
                            "Extract comparable revenue direction from cited facts."
                            if candidate.execution_type is SignalExecutionType.LLM
                            else None
                        ),
                        tests=(candidate_growth_fixture(),),
                        origin="cycle-recovery",
                    )
                    candidate_hash = registry.candidate_hash(candidate.ref)
                    candidate_hashes[candidate.ref] = candidate_hash
                    evaluation_keys[candidate.ref] = registry.record_candidate_validation(
                        candidate.ref,
                        candidate_hash=candidate_hash,
                        evaluation_identity={
                            "baseline_hash": "0" * 64,
                            "cohort_hash": f"{index + 1}" * 64,
                            "source_manifest_hash": "3" * 64,
                            "projection_hash": "4" * 64,
                            "validator_hash": "5" * 64,
                            "model_hash": "6" * 64,
                            "sampling_hash": "7" * 64,
                        },
                        accepted=True,
                        reasons=(),
                        effectiveness={
                            "accepted": True,
                            "disposition": "promoted",
                        },
                    )

                def inject(stage, _signal_ref):
                    if stage == fault_stage:
                        raise RuntimeError(f"fault after {fault_stage}")

                registry._fault_injector = inject

                with self.assertRaisesRegex(RuntimeError, "fault after"):
                    registry.promote_validated_batch(
                        candidate_hashes,
                        validated_evaluations=evaluation_keys,
                        transition_id="cycle-recovery",
                        input_version=snapshot.version,
                        input_hash=snapshot.registry_hash,
                        input_refs=tuple(spec.ref for spec in snapshot.specs),
                    )

                interrupted = SignalRegistry(
                    root / "signals",
                    candidate_root=root / "signals_candidates",
                )
                with self.assertRaisesRegex(
                    ValidationError, "prepared transition requiring recovery"
                ):
                    interrupted.freeze()

                recovered = interrupted.promote_validated_batch(
                    candidate_hashes,
                    validated_evaluations=evaluation_keys,
                    transition_id="cycle-recovery",
                    input_version=snapshot.version,
                    input_hash=snapshot.registry_hash,
                    input_refs=tuple(spec.ref for spec in snapshot.specs),
                )
                self.assertEqual(set(recovered.promoted), {item.ref for item in candidates})
                self.assertEqual(recovered.output_version, snapshot.version + 1)
                stable_refs = {spec.ref for spec in interrupted.freeze().specs}
                self.assertTrue({item.ref for item in candidates}.issubset(stable_refs))
                replay = interrupted.promote_validated_batch(
                    candidate_hashes,
                    validated_evaluations=evaluation_keys,
                    transition_id="cycle-recovery",
                    input_version=snapshot.version,
                    input_hash=snapshot.registry_hash,
                    input_refs=tuple(spec.ref for spec in snapshot.specs),
                )
                self.assertEqual(replay, recovered)

    def test_executor_uses_point_in_time_raw_info_and_tracks_observed_states(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            store = RawInfoStore(
                documents=(
                    RawInfoDocument.create(
                        document_id="financial_1",
                        company_id="issuer_1",
                        source_type="financials",
                        published_at=NOW - timedelta(days=2),
                        available_at=NOW - timedelta(days=1),
                        content=sec_company_facts_content(
                            ("2023-01-01", "2023-12-31", 100.0, "2024-02-01"),
                            ("2024-01-01", "2024-12-31", 125.0, "2025-01-10"),
                        ),
                    ),
                    RawInfoDocument.create(
                        document_id="financial_future",
                        company_id="issuer_1",
                        source_type="financials",
                        published_at=NOW + timedelta(days=1),
                        available_at=NOW + timedelta(days=1),
                        content=sec_company_facts_content(
                            ("2024-01-01", "2024-12-31", 125.0, "2025-01-10"),
                            ("2025-01-01", "2025-12-31", 50.0, "2026-01-10"),
                        ),
                    ),
                )
            )
            executor = SignalExecutor(registry.freeze(), store)
            batch = executor.execute_batch(
                ("revenue_growth_yoy:v1",),
                company_id="issuer_1",
                as_of=NOW,
            )
            result = batch.results[0]
            self.assertEqual(result.value, SignalValue.POSITIVE)
            self.assertEqual(result.supporting_evidence[0].document_id, "financial_1")
            registry.record_retrieval(result.ref)
            registry.record_result(result, is_surge=True)
            stats = registry.load_stats("revenue_growth_yoy")
            self.assertEqual(stats.retrieved, 1)
            self.assertEqual(stats.states["positive"], {"total": 1, "surge": 1})

    def test_signal_retrieval_policy_keeps_relevant_old_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            spec = registry.load_spec("guidance_acceleration:v1")
            self.assertEqual(
                spec.retrieval_policy,
                SignalRetrievalPolicy(
                    query_terms=(
                        "guidance outlook forecast",
                        "raises lowers reaffirms",
                    ),
                    lookback_days=730,
                    comparison_requirement=(
                        "Current guidance versus explicit prior guidance."
                    ),
                ),
            )
            documents = [
                RawInfoDocument.create(
                    document_id=f"recent-{index}",
                    company_id="issuer_1",
                    source_type="filing",
                    published_at=NOW - timedelta(days=index),
                    available_at=NOW - timedelta(days=index),
                    content=f"Routine administrative disclosure number {index}.",
                )
                for index in range(10)
            ]
            relevant = RawInfoDocument.create(
                document_id="older-relevant",
                company_id="issuer_1",
                source_type="filing",
                published_at=NOW - timedelta(days=20),
                available_at=NOW - timedelta(days=20),
                content="Management reported guidance acceleration for the year.",
            )
            executor = SignalExecutor(
                registry.freeze(),
                RawInfoStore(documents=(*documents, relevant)),
            )

            resolution = executor.prepare_inputs(
                (spec.ref,),
                company_id="issuer_1",
                as_of=NOW,
            )[0]

            self.assertEqual(
                resolution.request.query,
                "guidance outlook forecast raises lowers reaffirms",
            )
            self.assertIn(
                "older-relevant",
                {item.document_id for item in resolution.documents},
            )
            self.assertEqual(resolution.coverage.eligible_document_count, 11)
            self.assertEqual(resolution.coverage.selected_document_count, 10)
            self.assertEqual(resolution.coverage.query_matched_document_count, 1)
            self.assertTrue(resolution.coverage.selection_truncated)

    def test_execution_failure_does_not_pollute_or_consume_observation_stats(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            spec = registry.load_spec("revenue_growth_yoy:v1")
            failed = signal_execution_failure_result(
                spec,
                status=SignalExecutionStatus.VALIDATION_FAILED,
                error_code="fixture_validation_failed",
                error_message="fixture output did not satisfy its contract",
            )

            self.assertFalse(
                registry.record_observation(
                    "same-observation",
                    failed,
                    is_surge=True,
                )
            )
            stats = registry.load_stats(spec.signal_id)
            self.assertEqual(stats.retrieved, 0)
            self.assertEqual(stats.executed, 0)
            self.assertEqual(stats.unavailable, 0)
            self.assertEqual(stats.processed_observation_ids, set())

            recovered = SignalResult(
                signal_id=spec.signal_id,
                version=spec.version,
                value=SignalValue.UNAVAILABLE,
                confidence=0.0,
                interpretation="No eligible point-in-time document was available.",
                coverage=SignalCoverage.UNAVAILABLE,
            )
            self.assertTrue(
                registry.record_observation(
                    "same-observation",
                    recovered,
                    is_surge=True,
                )
            )
            stats = registry.load_stats(spec.signal_id)
            self.assertEqual(stats.retrieved, 1)
            self.assertEqual(stats.executed, 1)
            self.assertEqual(stats.unavailable, 1)
            self.assertEqual(
                stats.processed_observation_ids,
                {"same-observation"},
            )

    def test_definition_only_registry_records_observations_without_stats_artifact(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            for path in (Path(directory) / "signals").rglob("stats.json"):
                path.unlink()
            spec = registry.load_spec("revenue_growth_yoy:v1")
            self.assertEqual(registry.load_stats(spec.signal_id).retrieved, 0)
            result = SignalResult(
                signal_id=spec.signal_id,
                version=spec.version,
                value=SignalValue.POSITIVE,
                confidence=0.9,
                interpretation="Revenue grew on comparable periods.",
            )
            self.assertTrue(
                registry.record_observation(
                    "definition-only-observation",
                    result,
                    is_surge=True,
                )
            )
            persisted = registry.load_stats(spec.signal_id)
            self.assertEqual(persisted.retrieved, 1)
            self.assertEqual(persisted.states["positive"], {"total": 1, "surge": 1})

    def test_invalid_result_evidence_isolated_as_execution_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            document = RawInfoDocument.create(
                document_id="announcement_1",
                company_id="issuer_1",
                source_type="company_announcement",
                published_at=NOW,
                available_at=NOW,
                content="The customer entered volume deployment.",
            )

            class BadRunner:
                def execute(self, spec, documents, skill, as_of):
                    return (
                        SignalResult(
                            signal_id=spec.signal_id,
                            version=spec.version,
                            value=SignalValue.POSITIVE,
                            confidence=0.9,
                            interpretation="Volume deployment started.",
                            supporting_evidence=(
                                SignalEvidence(
                                    document_id="invented_doc",
                                    exact_span="volume deployment",
                                    timestamp=as_of,
                                ),
                            ),
                        ),
                        AgentUsage(llm_calls=1),
                    )

            executor = SignalExecutor(
                registry.freeze(),
                RawInfoStore(documents=(document,)),
                llm_runner=BadRunner(),
            )
            batch = executor.execute_batch(
                ("guidance_acceleration:v1",),
                company_id="issuer_1",
                as_of=NOW,
            )

            self.assertEqual(len(batch.results), 1)
            result = batch.results[0]
            self.assertEqual(result.value, SignalValue.UNAVAILABLE)
            self.assertEqual(
                result.execution_status,
                SignalExecutionStatus.VALIDATION_FAILED,
            )
            self.assertIn("outside its inputs", result.execution_error_message)
