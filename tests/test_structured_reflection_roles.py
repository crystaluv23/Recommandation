"""Production role wiring with locally scripted, catalog-sourced reflections."""

import json
import unittest
import tempfile
from pathlib import Path
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.research.evolution_core import (
    MagnitudeClass, PlanMetaMemory, PlanMetaReflection, RoundMetaEntry,
)
from stock_opportunity_agent.research.evolution_plan_roles import (
    LLMBlindPredictor, LLMInformationPlanProposer, LLMPlanCritic, LLMRoundReflector,
    _structured_reflection_items,
)
from stock_opportunity_agent.research.evolution_reflection_memory import (
    ReflectionMemoryIndex, violates_opportunity_proof_gate,
)
from stock_opportunity_agent.research.evolution_output_validation import _validate_fixed_plan_semantics
from stock_opportunity_agent.research.evolution_signal_roles import LLMSignalMiningModel
from stock_opportunity_agent.research.signal_evolution import (
    SignalEvolutionEngine, project_slow_method_memory, read_slow_sources,
    slow_method_memory_sources, validate_slow_memory,
)
from stock_opportunity_agent.models import StructuredValidationError, ValidationError
from stock_opportunity_agent.research.scheme_evolution import CandidateExecutionRejected, RuntimeBudgetExceeded, score_predictions
from tests.scheme_evolution_test_support import (
    EvolutionWorkspace, NoChangeUpdateModel, NOW, RawInfoDocument, RawInfoStore, SEED_CATALOG,
    SignalRegistry, fixture_mining_config, make_case, make_record, make_trajectory,
)


class CatalogCaller:
    """Generate explicit authored fixtures from the actual issued source handles."""

    def __init__(self, callback):
        self.callback = callback
        self.calls = []
        self.request_hash_trace = []

    def complete_json(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        self.request_hash_trace.append(canonical_json_hash(kwargs))
        return self.callback(kwargs), AgentUsage(llm_calls=1)


def authored(sources, *, category, text, outcome=False):
    """One explicit scripted lesson; it does not evaluate LLM research quality."""
    return {
        "category": category, "kind": "action", "brief": text,
        "detail": text + " Compare the archived counterexample before applying this again.",
        "scope": {
            "case_refs": sorted({ref for source in sources for ref in source["case_refs"]}),
            "plan_refs": sorted({ref for source in sources for ref in source["plan_refs"]}),
            "conditions": "When magnitude evidence is insufficient in the supplied case.",
        },
        "limitations": ["The causal explanation is untested."],
        "source_refs": [source["source_ref"] for source in sources],
        "counter_refs": [],
        "outcome_claims": [
            {"source_ref": source["source_ref"], "axis": "magnitude", "correct": False}
            for source in sources
        ] if outcome else [],
    }


class StructuredReflectionRoleLifecycleTests(unittest.TestCase):
    def test_plan_consumer_uses_the_same_proof_gate_for_each_instruction(self):
        from stock_opportunity_agent.research.evolution_core import default_information_plan
        for field, path in (("initial_research_skill", "H_init"),
                            ("reflection_skill", "H_reflect"), ("analysis_prompt", "H_analyse")):
            plan = replace(default_information_plan(), **{
                field: "A positive judgment requires a numerical valuation bridge.",
            })
            with self.subTest(field=field), self.assertRaises(StructuredValidationError) as caught:
                _validate_fixed_plan_semantics(plan)
            self.assertIn((path,), [issue.paths for issue in caught.exception.issues])
            _validate_fixed_plan_semantics(replace(default_information_plan(), **{
                field: "A surge judgment does not require a quantified valuation bridge.",
            }))

    def test_screening_guard_distinguishes_mandatory_proof_from_analysis(self):
        prohibited = (
            "Before making a surge call, require a forward catalyst that quantifies a path to the threshold.",
            "A positive judgment requires a numerical valuation bridge.",
            "Call doubling possible only if there is a proven share-price outcome.",
            "Do not require proof of revenue; a surge judgment requires a quantified price path.",
        )
        permitted = (
            "A surge judgment does not require a quantified valuation bridge.",
            "Never require a guaranteed doubling outcome.",
            "For a possible surge, optionally compare a quantified valuation bridge.",
            "Require a numerical demand path to support likely revenue growth.",
            "Assess a possible surge. Require a quantified revenue bridge when comparing accounting scenarios.",
            "Require a source-backed catalyst for a surge judgment; compare optional price scenarios.",
        )
        for text in prohibited + permitted:
            with self.subTest(text=text):
                self.assertEqual(violates_opportunity_proof_gate(text), text in prohibited)

    def test_action_proof_gate_has_exact_repair_path_and_preserves_facts(self):
        index = ReflectionMemoryIndex.from_case_rows([{
            "source_identity": "case:original", "candidate_judgment_feedback": {"binary_correct": False},
        }], owner_ref="plan:owner")
        valid = authored([index.source_catalog()[0]], category="next_explorations",
                         text="Compare optional catalyst scenarios using dated source evidence.")
        bad_text = "A positive judgment requires a numerical valuation bridge."
        for field in ("brief", "detail"):
            invalid = {**deepcopy(valid), field: bad_text}
            with self.subTest(field=field), self.assertRaises(StructuredValidationError) as caught:
                _structured_reflection_items({"reflection_items": [valid, invalid],
                                              "selected_reflection_refs": []},
                                             index=index, level="plan", owner_ref="plan:owner")
            self.assertEqual(caught.exception.issues[0].paths, (f"reflection_items[1].{field}",))
            for kind in ("fact", "hypothesis"):
                result = index.create_items([{**invalid, "kind": kind}], level="plan", owner_ref="plan:owner")
                self.assertEqual(getattr(result[0], field), bad_text)

    def test_retry_cannot_select_a_new_same_level_item_as_lower_evidence(self):
        index = ReflectionMemoryIndex.from_case_rows([{
            "source_identity": "case:original", "candidate_judgment_feedback": {"binary_correct": False},
        }], owner_ref="plan:owner")
        item = index.create_items([authored(
            [index.source_catalog()[0]], category="next_explorations",
            text="Test the unresolved evidence gap before reusing this rule.",
        )], level="plan", owner_ref="plan:owner")[0]
        with self.assertRaises(StructuredValidationError) as caught:
            _structured_reflection_items({
                "reflection_items": [], "selected_reflection_refs": [item.item_ref],
            }, index=index, level="plan", owner_ref="plan:owner")
        self.assertEqual(caught.exception.issues[0].paths, ("selected_reflection_refs",))

    def test_factual_probability_diagnosis_does_not_redefine_predictor(self):
        trajectory = make_trajectory("probability_case", 15.0, True, MagnitudeClass.TWO_TO_THREE)

        def output(request):
            source = request["payload"]["source_catalog"][0]
            return {"reflection_items": [authored(
                [source], category="plan_issues",
                text="Within the fixed horizon, probability support is uncertain; compare evidence coverage before changing the instruction.",
            )], "selected_reflection_refs": []}

        result = LLMBlindPredictor(CatalogCaller(output)).reflect(
            {"summary": "Direction evidence is available."}, trajectory.prediction, trajectory.ground_truth,
        )
        self.assertIn("probability support", result.value.reflection_items[0].brief)

    def test_case_plan_round_restart_and_proposer_preserve_original_sources(self):
        records, issued = [], {}
        for number in (1, 2):
            record = make_record(f"plan_{number}", 1.0, (1.0, 0.0))
            trajectory = make_trajectory(f"issuer_{number}", 15.0, True, MagnitudeClass.TWO_TO_THREE)

            def posthoc_output(request):
                source = request["payload"]["source_catalog"][0]
                return {"reflection_items": [authored(
                    [source], category="plan_issues",
                    text="For Acme Systems, require a bounded magnitude bridge.",
                )], "selected_reflection_refs": []}

            posthoc = CatalogCaller(posthoc_output)
            predictor = LLMBlindPredictor(posthoc, anonymous_aliases=("Acme Systems",))
            result = predictor.reflect(
                {"summary": "The approved anonymous source supports direction but not magnitude."},
                trajectory.prediction, trajectory.ground_truth,
            )
            trajectory = replace(trajectory, self_reflection=result.value)
            case_item = result.value.reflection_items[0]
            self.assertNotIn("Acme Systems", json.dumps(case_item.to_dict()))
            issued[case_item.item_ref] = case_item.to_dict()

            def critic_output(request):
                payload = request["payload"]
                # Choose the immutable original case unit, not merely its facts.
                sources = [source for source in payload["source_catalog"] if source["canonical_outcomes"].get("magnitude") is False]
                source = sources[-1]
                return {"reflection_items": [authored(
                    [source], category="failed_patterns",
                    text="The realized magnitude exceeded the supplied class; test a range bridge.",
                    outcome=True,
                )], "selected_reflection_refs": [case_item.item_ref]}

            critic = CatalogCaller(critic_output)
            reflection = LLMPlanCritic(critic).critique(
                plan=record.plan, trajectories=(trajectory,), metrics=score_predictions((trajectory,)),
            )
            self.assertEqual(reflection.selected_reflection_refs, (case_item.item_ref,))
            plan_item = reflection.reflection_items[0]
            self.assertEqual(plan_item.scope["plan_refs"], ["reflection_plan:" + canonical_json_hash(record.plan.canonical_dict())])
            issued[plan_item.item_ref] = plan_item.to_dict()
            records.append(replace(record, metrics=score_predictions((trajectory,)), trajectories=(trajectory,), reflection=reflection, evaluation=None, fitness=None))

        def round_output(request):
            payload = request["payload"]
            plan_sources = [source for source in payload["source_catalog"] if source["level"] == "plan" and source["source_ref"].startswith("reflection_source:")]
            return {"reflection_items": [authored(
                plan_sources, category="search_implications",
                text="Across both Plans, require a scenario bridge before adopting a magnitude rule.",
            )], "selected_reflection_refs": [record.reflection.reflection_items[0].item_ref for record in records]}

        reflector = CatalogCaller(round_output)
        entry = LLMRoundReflector(reflector).reflect(round_id=5, records=tuple(records), prior="Reflect across the supplied Plans.")
        self.assertEqual(len(entry.reflection_items[0].scope["plan_refs"]), 2)
        entry = entry.append_plan_reflections(PlanMetaReflection.from_record(record) for record in records)
        # Actual JSON restart and imported round rebase must not alter handles.
        restored = RoundMetaEntry.from_dict(json.loads(json.dumps(entry.to_dict())))
        restored = replace(restored, round_id=-5)
        index = ReflectionMemoryIndex.from_entries([restored.to_model_dict()])
        for item_ref, original in issued.items():
            self.assertEqual(index.read_refs([item_ref], role="proposer")["sources"][0]["content"], original)
            for source_ref in original["source_refs"]:
                self.assertTrue(index.read_refs([source_ref], role="proposer")["sources"])
        for source_ref in entry.reflection_items[0].source_refs:
            self.assertTrue(index.read_refs([source_ref], role="proposer", max_bytes=48000)["sources"])

        def propose_output(request):
            context = request["payload"]["proposal_context"]
            if not context["memory_disclosures"]:
                self.assertTrue(context["meta_info"]["items"])
                ref = context["meta_info"]["items"][0]["item_ref"]
                return {"read_refs": [ref]}
            source = context["memory_disclosures"][0]["sources"][0]
            self.assertIn("detail", source["content"])
            parent = records[0].plan
            return {"B": parent.basic_info_policy.to_dict(), "H_init": parent.initial_research_skill + " Compare magnitude scenarios with explicit counterevidence.", "H_reflect": parent.reflection_skill, "H_analyse": parent.analysis_prompt}

        proposer = CatalogCaller(propose_output)
        proposed = LLMInformationPlanProposer(proposer).propose(
            round_id=6, candidate_index=1, candidate_count=1, proposal_attempt=1,
            forbidden_plan_ids=(), parents=(records[0].plan,), meta_info=(restored,), prior="Use attributable lessons.",
        )
        self.assertIn("Compare magnitude scenarios", proposed.initial_research_skill)
        self.assertEqual(len(proposer.calls), 2)


class SlowAuthoredBriefTests(unittest.TestCase):
    def test_slow_wrong_envelope_repairs_only_issued_containers(self):
        from tests.test_evolution_state_patch import PatchCaller, patch

        def correct(request):
            contract = request["payload"]["output_patch_contract"]
            return patch(contract,
                {"op": "replace", "path": "episode_reflections", "value": []},
                {"op": "add", "path": "lesson_additions", "value": []},
                {"op": "remove", "path": "summary"},
            )

        caller = PatchCaller({"episode_reflections": {}, "summary": "Wrong envelope."}, correct)
        result = LLMSignalMiningModel(caller).reflect_feedback({
            "episode_slots": [], "lesson_slots": [], "feedback_units": [],
        })
        self.assertEqual(result.value, {"episode_reflections": [], "lesson_additions": []})
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(result.usage.llm_calls, 2)

    def test_slow_live_briefs_keep_originals_and_resolve_through_existing_reader(self):
        episode = {
            "episode_ref": "episode-c0001-001", "source_refs": ["feedback-1"],
            "reflection": "The paired evidence excludes a demonstrated gain. " * 120,
            "unresolved_questions": ["Does the same limitation recur on independent cases?"],
            "kind": "hypothesis",
            "brief": "When paired evidence shows no gain, retain the counterexample; the causal explanation remains untested.",
        }
        lesson = {
            "lesson_id": "lesson-c0001-001", "guidance": "Inspect the measured gate and paired counterexamples before adding the rule. " * 120,
            "applicable_scope": "The same measurement and frozen paired population.",
            "support_refs": ["episode-c0001-001"], "counterevidence_refs": ["feedback-1"],
            "limitations": "One paired evaluation does not establish transfer to future cohorts.",
            "qualifies_refs": [], "challenges_refs": [], "kind": "action",
            "brief": "Before reusing the same measurement, inspect the paired counterexample; transfer to future cohorts remains untested.",
        }
        output = {"episode_reflections": [episode], "lesson_additions": [lesson]}
        caller = CatalogCaller(lambda request: deepcopy(output))
        generated = LLMSignalMiningModel(caller).reflect_feedback({
            "episode_slots": [episode["episode_ref"]], "lesson_slots": [lesson["lesson_id"]],
            "feedback_units": [{"feedback_ref": "feedback-1", "result": "No demonstrated paired gain."}],
        })
        self.assertEqual(generated.value, output)
        delta = {"cycle_id": 1, "status": "appended", "processed_feedback_refs": ["feedback-1"], **generated.value}
        original = deepcopy(delta)
        view = project_slow_method_memory([delta], budget_bytes=5000)
        projected = view["memory_deltas"][0]
        self.assertNotIn("reflection", projected["episode_reflections"][0])
        self.assertNotIn("guidance", projected["lesson_additions"][0])
        self.assertEqual(projected["lesson_additions"][0]["counterevidence_refs"], ["feedback-1"])
        source_ref = projected["episode_reflections"][0]["original_ref"]
        catalog = slow_method_memory_sources([delta])
        resolved, manifest = read_slow_sources([source_ref], role_scope="H1", source_catalog=catalog, budget_bytes=64000)
        self.assertEqual(resolved[0]["content"], episode)
        self.assertEqual(manifest["deferred_count"], 0)
        for role in ("blind_predictor", "E1"):
            with self.assertRaises(ValidationError):
                read_slow_sources([source_ref], role_scope=role, source_catalog=catalog, budget_bytes=64000)

        def choose_original(request):
            offered = request["payload"]["available_sources"]
            chosen = next(row for row in offered if row.get("brief") == episode["brief"])
            return {"read_source_refs": [chosen["ref"]]}

        engine = object.__new__(SignalEvolutionEngine)
        engine._active_slow_memory = delta
        engine._active_slow_input = {"feedback_rows": [{"feedback_ref": "feedback-1", "result": "No demonstrated paired gain."}]}
        engine.workspace = SimpleNamespace(committed_slow_artifacts=lambda: [])
        selection_caller = CatalogCaller(choose_original)
        engine.mining_model = LLMSignalMiningModel(selection_caller)
        engine.update_model = engine.mining_model
        disclosed_view = engine._slow_method_view("H1")
        self.assertEqual(disclosed_view["source_entries"][0]["content"], episode)
        self.assertEqual(delta, original)
        self.assertEqual(len(selection_caller.calls), 1)

        # The next Slow reflection sees a brief of prior memory, and can use
        # the same source selector to inspect its immutable original first.
        def next_reflection(request):
            if request["stage"] == "slow_source_read":
                return choose_original(request)
            payload = request["payload"]
            self.assertNotIn("reflection", payload["prior_memory"][0]["episode_reflections"][0])
            self.assertEqual(payload["prior_memory_disclosures"][0]["content"], episode)
            return {"episode_reflections": [{
                **episode, "episode_ref": payload["episode_slots"][0],
                "source_refs": [payload["feedback_units"][0]["feedback_ref"]],
            }], "lesson_additions": []}

        staged = []
        engine.workspace = SimpleNamespace(
            committed_slow_artifacts=lambda: [{"slow_memory": delta}],
            load_slow_memory=lambda cycle_id: None,
            stage_slow_memory=lambda **kwargs: staged.append(kwargs),
        )
        engine.mining_config = SimpleNamespace(reflection_feedback_limit=12)
        next_caller = CatalogCaller(next_reflection)
        engine.mining_model = LLMSignalMiningModel(next_caller)
        prepared = engine._prepare_slow_memory(cycle_id=2, slow_input={
            "contract_hash": "offline-contract", "previous_memory_head": 1,
            "feedback_rows": [{"feedback_ref": "feedback-2", "result": "A fresh paired evaluation has completed."}],
            "source_manifest": [{"ref": "feedback-2"}],
        })
        self.assertEqual(prepared["status"], "appended")
        self.assertEqual(prepared["processed_feedback_refs"], ["feedback-2"])
        self.assertTrue(prepared["model_view_manifest"]["prior_original_reads"]["included_refs"])
        self.assertEqual(len(next_caller.calls), 2)
        self.assertEqual(delta, original)

    def test_slow_lessons_cannot_cite_unused_slots_or_self_support(self):
        episode = {"episode_ref": "episode-1", "source_refs": ["feedback-1"],
            "reflection": "The complete selected outcome is inconclusive.", "unresolved_questions": [],
            "kind": "fact", "brief": "The selected outcome is inconclusive."}
        lesson = {"lesson_id": "lesson-1", "guidance": "Inspect the paired counterexample.",
            "applicable_scope": "The frozen paired population.", "limitations": "Transfer is untested.",
            "support_refs": ["episode-1"], "counterevidence_refs": [], "qualifies_refs": [], "challenges_refs": [],
            "kind": "action", "brief": "On the same population, inspect paired counterexamples before reuse."}
        payload = {"episode_slots": ["episode-1", "unused-episode"], "lesson_slots": ["lesson-1", "lesson-2", "unused-lesson"],
            "feedback_units": [{"feedback_ref": "feedback-1"}]}
        for source in ("unused-episode", "unused-lesson", "lesson-1", "lesson-2"):
            with self.subTest(source=source):
                lessons = [{**lesson, "support_refs": [source]}]
                if source == "lesson-2":
                    lessons.append({**lesson, "lesson_id": "lesson-2", "support_refs": ["lesson-1"]})
                caller = CatalogCaller(lambda request: {"episode_reflections": [episode], "lesson_additions": lessons})
                with self.assertRaises(CandidateExecutionRejected):
                    LLMSignalMiningModel(caller).reflect_feedback(payload)
                correction = json.dumps(caller.calls[1]["payload"])
                self.assertIn("lesson_additions[0].support_refs", correction)
        output = {"episode_reflections": [episode], "lesson_additions": [lesson,
            {**lesson, "lesson_id": "lesson-2", "support_refs": ["feedback-1"], "qualifies_refs": ["lesson-1"]}]}
        result = LLMSignalMiningModel(CatalogCaller(lambda request: output)).reflect_feedback(payload)
        self.assertEqual(result.value, output)
        archived = {"schema_version": "slow-memory-v1", "cycle_id": 1, "contract_hash": "contract",
            "input_hash": "input", "parent_memory_hash": "parent", "reflection_work_hash": "work",
            "status": "appended", "processed_feedback_refs": ["feedback-1"], "pending_feedback_refs": [],
            "model_view_manifest": {}, "usage_ref": "usage", "failure_ref": None, **output}
        validate_slow_memory(archived, available_feedback_refs=["feedback-1"], available_source_refs=["feedback-1"])
        invalid = deepcopy(archived)
        invalid["lesson_additions"][0]["support_refs"] = ["lesson-2"]
        invalid["lesson_additions"][1]["support_refs"] = ["lesson-1"]
        with self.assertRaises(ValidationError):
            validate_slow_memory(invalid, available_feedback_refs=["feedback-1"], available_source_refs=["feedback-1"])
        for row in (*invalid["episode_reflections"], *invalid["lesson_additions"]):
            row.pop("kind"); row.pop("brief")
        # Loading historical schema does not certify or rewrite its old claims.
        self.assertEqual(validate_slow_memory(invalid, available_feedback_refs=["feedback-1"], available_source_refs=["feedback-1"]), invalid)
        for field in ("episode_reflections", "lesson_additions"):
            malformed = deepcopy(archived)
            malformed[field][0]["kind"] = []
            with self.assertRaises(ValidationError):
                validate_slow_memory(malformed, available_feedback_refs=["feedback-1"], available_source_refs=["feedback-1"])
            caller = CatalogCaller(lambda request: {key: malformed[key] for key in ("episode_reflections", "lesson_additions")})
            with self.assertRaises(CandidateExecutionRejected):
                LLMSignalMiningModel(caller).reflect_feedback(payload)
            self.assertIn(field + "[0]", json.dumps(caller.calls[1]["payload"]))

    def test_source_selection_envelope_bounds_large_brief_and_directory(self):
        catalog = {f"source-{i}": {"visible_to": ["H1"], "content": {
            "brief": "Condition and concrete action " * (2000 if i == 0 else 80),
            "kind": "action", "reflection": "Exact original " * 100,
        }} for i in range(300)}
        selected, manifest = read_slow_sources((), role_scope="H1", source_catalog=catalog, budget_bytes=48_000)
        manifest.update(requested_refs=list(catalog), deferred=[{"ref": ref, "reason": "on_request"} for ref in catalog])
        caller = CatalogCaller(lambda request: {"read_source_refs": []})
        engine = object.__new__(SignalEvolutionEngine)
        engine._optional_slow_source_read(model=LLMSignalMiningModel(caller), role_scope="H1",
            source_catalog=catalog, selected=selected, manifest=manifest)
        payload = caller.calls[0]["payload"]
        self.assertLessEqual(len(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()), 32_000)
        first = payload["available_sources"][0]
        self.assertEqual(first["ref"], "source-0")
        self.assertEqual(first["preview_omitted"], "whole_preview_budget")
        self.assertGreater(first["read_bytes"], 48_000)
        self.assertEqual(payload["deferred_count"], 300)
        self.assertGreater(payload["omitted_available_sources"], 0)
        self.assertNotIn("Exact original", json.dumps(payload))

    def test_oversized_original_rejection_retains_completed_selector_usage(self):
        catalog = {"source-large": {"visible_to": ["H1"], "content": {
            "brief": "Inspect the complete original before reuse.",
            "reflection": "Original reflection. " * 3000,
        }}}
        selected, manifest = read_slow_sources(
            (), role_scope="H1", source_catalog=catalog, budget_bytes=48_000,
        )
        manifest.update(requested_refs=["source-large"],
            deferred=[{"ref": "source-large", "reason": "on_request"}])
        caller = CatalogCaller(lambda request: {"read_source_refs": ["source-large"]})
        engine = object.__new__(SignalEvolutionEngine)
        with self.assertRaises(CandidateExecutionRejected) as caught:
            engine._optional_slow_source_read(model=LLMSignalMiningModel(caller),
                role_scope="H1", source_catalog=catalog, selected=selected, manifest=manifest)
        self.assertEqual(caught.exception.stage, "slow_source_read")
        self.assertIn("whole-entry budget", str(caught.exception))
        self.assertEqual(caught.exception.usage.llm_calls, 1)
        self.assertEqual(caught.exception.details["request_refs"], caller.request_hash_trace)
        self.assertEqual(caught.exception.details["requested_refs"], ["source-large"])

    def test_legacy_slow_text_is_retained_without_invented_brief(self):
        delta = {"cycle_id": 1, "episode_reflections": [{"episode_ref": "old", "reflection": "Original unreviewed text."}], "lesson_additions": []}
        view = project_slow_method_memory([delta], budget_bytes=3000)
        episode = view["memory_deltas"][0]["episode_reflections"][0]
        self.assertEqual(episode, delta["episode_reflections"][0])
        self.assertNotIn("brief", episode)


class FastToSlowConsumptionTests(unittest.TestCase):
    def test_h1_reads_exact_original_from_bounded_meta_and_accounts_once(self):
        expected = "When paired evidence is insufficient, compare the same population before reuse. " * 12
        memory = PlanMetaMemory(entries=[RoundMetaEntry(round_id=1, evidence_refs=("offline-observations",),
            successful_patterns=tuple(f"Observation {i}: {expected}" for i in range(180)))])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            cases = tuple(make_case(f"memory_case_{i}", 4.0 if i < 2 else 1.1) for i in range(4))
            fail_h1 = False
            chosen = []

            def respond(request):
                if request["stage"] == "slow_source_read":
                    offered = next(row for row in request["payload"]["available_sources"] if row.get("brief"))
                    chosen.append(offered)
                    return {"read_source_refs": [offered["ref"]]}
                if fail_h1 == "budget":
                    raise RuntimeBudgetExceeded("Local zero-call H1 preflight budget.")
                if fail_h1:
                    return {"invalid_output": []}
                return {"conclusion": "no_testable_hypothesis", "hypotheses": [],
                    "no_hypothesis": {"reason_code": "insufficient_retrieval_basis", "rationale": ["No additional measurable source is available."], "need_refs": []},
                    "need_dispositions": []}

            caller = CatalogCaller(respond)
            engine = SignalEvolutionEngine(registry=registry, raw_info_store=RawInfoStore(documents=tuple(
                RawInfoDocument.create(document_id=f"news-{i}", company_id=case.company_id, source_type="news",
                    published_at=NOW, available_at=NOW, content="An operational event was disclosed.")
                for i, case in enumerate(cases))), discovery_cases=cases,
                meta_memory=memory, workspace=EvolutionWorkspace(root / "workspace"),
                mining_model=LLMSignalMiningModel(caller), update_model=NoChangeUpdateModel(),
                llm_signal_runner=None, mining_config=fixture_mining_config(4))
            first = engine._run_hypothesis_mining(cycle_id=1)
            self.assertEqual([call["stage"] for call in caller.calls], ["slow_source_read", "signal_mining_hypotheses"])
            payload = caller.calls[1]["payload"]
            self.assertGreater(len(json.dumps(memory.archive_view()).encode()), 150_000)
            self.assertLessEqual(len(json.dumps(payload["meta_info"], ensure_ascii=False, separators=(",", ":")).encode()), 32_000)
            self.assertLessEqual(len(json.dumps(payload["meta_source_catalog"], ensure_ascii=False, separators=(",", ":")).encode()), 16_000)
            source = payload["meta_memory_disclosures"][0]["content"]["content"]
            self.assertEqual(source["detail"], chosen[0]["brief"])
            self.assertEqual(payload["meta_context_audit"]["round_ids"], [1])
            audit = first["audit"]["stages"]["H1"]
            self.assertEqual(audit["usage"]["llm_calls"], 2)
            self.assertEqual(audit["request_refs"], caller.request_hash_trace)
            cycle_dir = engine.workspace.experiments_root / "cycles" / "cycle-0001"
            cycle_dir.mkdir(parents=True)
            (cycle_dir / "slow_loop_validation.json").write_text(json.dumps({"validation": {
                "refined_hypotheses": {}, "agent_audits": {"mining_pipeline": first["audit"]}}}))
            engine.workspace.cycle_state_path.write_text(json.dumps({"last_completed_cycle": 1,
                "last_completed_round": 0, "run_contract_hash": "contract", "active_cycle": None}))
            repeated = engine._run_hypothesis_mining(cycle_id=2)
            self.assertEqual(repeated["audit"]["status"], "unchanged_h1_work_suppressed")
            self.assertEqual(repeated["audit"]["stages"]["H1"]["usage"]["llm_calls"], 1)
            self.assertEqual(repeated["audit"]["stages"]["H1"]["request_refs"], caller.request_hash_trace[-1:])
            # A genuinely changed memory forces H1; failure must retain the read cost.
            memory.append(RoundMetaEntry(round_id=2, evidence_refs=("offline-new-observation",), successful_patterns=("A new independent observation is inconclusive.",)))
            fail_h1 = True
            before = len(caller.calls)
            with self.assertRaises(CandidateExecutionRejected) as caught:
                engine._run_hypothesis_mining(cycle_id=3)
            self.assertEqual(caught.exception.usage.llm_calls, len(caller.calls) - before)
            self.assertEqual(caught.exception.details["request_refs"], list(dict.fromkeys(caller.request_hash_trace[before:])))
            fail_h1 = "budget"
            with self.assertRaises(RuntimeBudgetExceeded) as budget:
                engine._run_hypothesis_mining(cycle_id=3)
            self.assertEqual(budget.exception.usage.llm_calls, 1)

    def test_h1_action_backlog_uses_authored_brief_not_compatibility_detail(self):
        record = make_record("action_plan", 1.0, (1.0, 0.0))
        trajectory = make_trajectory("action_case", 15.0, True, MagnitudeClass.TWO_TO_THREE)
        marker = "UNREAD_FULL_DETAIL_SENTINEL " * 400

        def output(request):
            item = authored([request["payload"]["source_catalog"][0]], category="next_explorations",
                text="When magnitude support is missing, ask for a scenario bridge.")
            item["detail"] = marker
            return {"reflection_items": [item], "selected_reflection_refs": []}

        reflection = LLMPlanCritic(CatalogCaller(output)).critique(plan=record.plan,
            trajectories=(trajectory,), metrics=score_predictions((trajectory,)))
        record = replace(record, reflection=reflection, trajectories=(trajectory,),
            metrics=score_predictions((trajectory,)), evaluation=None, fitness=None)
        memory = PlanMetaMemory(entries=[RoundMetaEntry(round_id=1, evidence_refs=(record.plan_id,),
            plan_reflections=(PlanMetaReflection.from_record(record),))])
        engine = object.__new__(SignalEvolutionEngine)
        engine.meta_memory = memory
        actions, audit = engine._reflection_action_inventory()
        self.assertEqual(actions[0]["need"], reflection.reflection_items[0].brief)
        self.assertEqual(actions[0]["reflection_item_ref"], reflection.reflection_items[0].item_ref)
        self.assertNotIn("UNREAD_FULL_DETAIL_SENTINEL", json.dumps(actions))
        self.assertEqual(audit["omitted_count"], 0)


if __name__ == "__main__":
    unittest.main()
