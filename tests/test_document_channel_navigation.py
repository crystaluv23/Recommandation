"""Production Reflect navigation, correction preservation and case boundaries."""

import json
from datetime import datetime, timedelta, timezone
from unittest import TestCase

from tests.evolution_runtime_test_support import ScriptedRoleCaller
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    ResearchState, SignalBatchResult, CandidateExecutionRejected, RuntimeBudgetExceeded,
    _DocumentChannelProvider,
    _assemble_final_context, default_information_plan,
)
from stock_opportunity_agent.research.evolution_plan_roles import (
    LLMResearchController, _DocumentChannelCaller,
)


AS_OF = datetime(2025, 9, 30, tzinfo=timezone.utc)


def document(identifier, *, company="issuer", days_old=0, content="Source body."):
    """Create one exact immutable source with controlled scope and availability."""
    available = AS_OF - timedelta(days=days_old)
    return RawInfoDocument.create(
        document_id=identifier, company_id=company, source_type="news",
        published_at=available, available_at=available, content=content,
    )


def channel(outputs, documents):
    """Exercise the real provider and adapter while replacing only model I/O."""
    provider = _DocumentChannelProvider(
        RawInfoStore(documents=documents), company_id="issuer", as_of=AS_OF,
    )
    caller = ScriptedRoleCaller(outputs)
    return _DocumentChannelCaller(caller, provider), caller, provider


def request(wrapper, *, stage="research_controller_reflect"):
    return wrapper.complete_json(
        stage=stage, system_prompt="Fixture contract.", payload={},
        allow_outcomes=False, max_output_tokens=100, max_request_tokens=1000,
    )


class DocumentChannelNavigationTests(TestCase):
    def test_recent_page_fetch_reaches_controller_and_persistable_final_context(self):
        sources = [document(f"old-{i:02}", days_old=100-i) for i in range(45)]
        recent = document("recent", content="A distinct source established a new project.")
        sources.extend((recent, document("future", days_old=-1),
                        document("other", company="other-issuer")))
        state = ResearchState(hypotheses=["Fixture."], next_information_needs=["Check project."])
        caller = ScriptedRoleCaller([
            {"inspect_document_catalog": {"cursor": 40}},
            {"fetch_documents": [{"document_id": "recent"}]},
            {**state.to_dict(), "need_dispositions": []},
        ])
        provider = _DocumentChannelProvider(
            RawInfoStore(documents=sources), company_id="issuer", as_of=AS_OF,
        )
        controller = LLMResearchController(caller)
        controller.set_document_channel(provider)
        step = controller.reflect(
            default_information_plan(), state, SignalBatchResult(results=(), signal_calls=0),
        )
        self.assertEqual(step.value, state)
        self.assertEqual(step.usage.llm_calls, 3)
        initial = caller.calls[0]["payload"]["document_catalog"]
        self.assertEqual(initial["counts"], {"eligible": 46, "included": 20, "omitted": 26})
        final_payload = caller.calls[-1]["payload"]
        self.assertEqual(final_payload["document_catalog"], initial)
        page = final_payload["document_catalog_pages"][0]
        self.assertEqual(page["cursor"], 40)
        ids = {c["document_id"] for c in page["cards"]}
        self.assertIn("recent", ids)
        self.assertFalse(ids & {"future", "other"})
        self.assertEqual(final_payload["document_channel"], provider.document_views)
        context = _assemble_final_context(
            plan=default_information_plan(), company_id="issuer", additional_identity_aliases=(),
            basic_info={"requests": []}, state=step.value, rounds=(), prediction_time=AS_OF,
            document_views=provider.document_views,
        )
        archived = json.loads(json.dumps(context))
        self.assertEqual(archived["document_channel"][0]["text"], recent.content)
        self.assertEqual(archived["document_channel"][0]["reference"]["content_hash"], recent.content_hash)
        prompt = caller.calls[0]["system_prompt"]
        self.assertIn("inspect_document_catalog", prompt)
        self.assertIn("two exchanges total", prompt)
        self.assertIn("does not create a new ResearchState evidence", prompt)

    def test_pages_and_views_survive_semantic_correction_but_not_mechanical_request(self):
        sources = [document(f"doc-{i:02}", days_old=30-i) for i in range(25)]
        wrapper, caller, provider = channel([
            {"inspect_document_catalog": {"cursor": 20}},
            {"fetch_documents": [{"document_id": "doc-24"}]},
            {"answer": "invalid-state"}, {"answer": "corrected-state"},
            {"patch_ops": []},
        ], sources)
        _, first_usage = request(wrapper)
        request(wrapper, stage="research_controller_reflect_correction")
        corrected = caller.calls[-1]["payload"]
        self.assertEqual(len(corrected["document_catalog_pages"]), 1)
        self.assertEqual(corrected["document_channel"], provider.document_views)
        self.assertEqual(first_usage.llm_calls, 3)
        self.assertEqual(wrapper.exchanges, 2)
        request(wrapper, stage="research_controller_reflect_patch_mechanics_correction")
        self.assertEqual(caller.calls[-1]["payload"], {})

    def test_invalid_and_repeated_catalog_requests_fail_closed(self):
        sources = [document(f"doc-{i}") for i in range(21)]
        for query in ({"cursor": True}, {"cursor": -1}, {"cursor": 22},
                      {"cursor": "20"}, {"cursor": 0}, {"cursor": 20, "limit": 100}, []):
            with self.subTest(query=query):
                wrapper, _, provider = channel([{"inspect_document_catalog": query}], sources)
                with self.assertRaises(ValidationError):
                    request(wrapper)
                self.assertEqual(provider.document_views, [])
        wrapper, _, _ = channel([
            {"inspect_document_catalog": {"cursor": 20}},
            {"inspect_document_catalog": {"cursor": 20}},
        ], sources)
        with self.assertRaisesRegex(ValidationError, "already disclosed"):
            request(wrapper)

    def test_computed_cards_survive_semantic_correction(self):
        from tests.test_compute_tools import BARS, market_document

        market = market_document(BARS)
        provider = _DocumentChannelProvider(
            RawInfoStore(documents=(market,)), company_id="issuer",
            as_of=datetime(2025, 7, 31, tzinfo=timezone.utc), market_documents=(market,),
        )
        caller = ScriptedRoleCaller([
            {"compute": [{"metric": "price_shape", "params": {"window_days": 180}}]},
            {"answer": "invalid-state"}, {"answer": "corrected-state"},
        ])
        wrapper = _DocumentChannelCaller(caller, provider)
        request(wrapper)
        request(wrapper, stage="research_controller_reflect_correction")
        self.assertEqual(caller.calls[-1]["payload"]["computed_metrics"], provider.computed_metrics)
        self.assertEqual(wrapper.exchanges, 1)

    def test_catalog_fetch_and_compute_share_existing_exchange_budget(self):
        sources = [document(f"doc-{i:02}") for i in range(50)]
        wrapper, _, provider = channel([
            {"inspect_document_catalog": {"cursor": 20}},
            {"fetch_documents": [{"document_id": "doc-20"}]},
            {"compute": []},
        ], sources)
        with self.assertRaisesRegex(ValidationError, "exchange budget"):
            request(wrapper)
        self.assertEqual(wrapper.exchanges, 2)
        self.assertEqual(len(provider.document_views), 1)
        self.assertEqual(provider.computed_metrics, [])

    def test_mixed_cross_company_future_or_unknown_fetch_does_not_persist_partial_batch(self):
        sources = (document("valid"), document("other", company="other-issuer"),
                   document("future", days_old=-1))
        for identifier in ("other", "future", "unknown"):
            with self.subTest(identifier=identifier):
                wrapper, _, provider = channel([{"fetch_documents": [
                    {"document_id": "valid"}, {"document_id": identifier},
                ]}], sources)
                with self.assertRaises(ValidationError):
                    request(wrapper)
                self.assertEqual(provider.document_views, [])

    def test_duplicate_fetch_in_same_batch_does_not_persist_views(self):
        wrapper, _, provider = channel([{"fetch_documents": [
            {"document_id": "valid"}, {"document_id": "valid"},
        ]}], (document("valid"),))
        with self.assertRaisesRegex(ValidationError, "already fetched"):
            request(wrapper)
        self.assertEqual(provider.document_views, [])

    def test_next_case_provider_has_no_prior_disclosures(self):
        wrapper, _, provider = channel([
            {"fetch_documents": [{"document_id": "first"}]}, {"answer": "state"},
        ], (document("first"),))
        request(wrapper)
        self.assertTrue(provider.document_views)
        next_wrapper, next_caller, _ = channel([{"answer": "state"}], (document("next"),))
        request(next_wrapper)
        self.assertNotIn("document_channel", next_caller.calls[0]["payload"])
        self.assertNotIn("document_catalog_pages", next_caller.calls[0]["payload"])

    def test_mid_exchange_budget_or_candidate_stop_preserves_actual_usage(self):
        for failure in (
            RuntimeBudgetExceeded("preflight", usage=AgentUsage(llm_calls=1, tokens=7)),
            CandidateExecutionRejected("research_controller_reflect", "stop",
                                       usage=AgentUsage(llm_calls=1, tokens=7)),
        ):
            with self.subTest(failure=type(failure).__name__):
                def fail(_request):
                    raise failure

                wrapper, caller, provider = channel([
                    {"fetch_documents": [{"document_id": "valid"}]}, fail,
                ], (document("valid"),))
                with self.assertRaises(type(failure)) as caught:
                    request(wrapper)
                self.assertIs(caught.exception, failure)
                self.assertEqual(failure.usage.llm_calls, 2)
                self.assertEqual(failure.usage.tokens, 12)
                self.assertEqual(caller.calls[-1]["max_request_tokens"], 995)
                self.assertEqual(len(provider.document_views), 1)
