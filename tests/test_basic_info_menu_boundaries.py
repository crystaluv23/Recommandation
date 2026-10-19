"""Independent entry-point and source-coverage counterexamples for Basic Info."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import TestCase, mock

from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.resolution import (
    RawInfoRequest,
    _matches_source_type,
    _rank_documents,
    _retrieval_contract_coverage,
    _select_required_source_documents,
)
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    BasicInfoPolicy,
    InformationPlan,
    default_information_plan,
    execute_information_plan,
)


AS_OF = datetime(2025, 9, 30, tzinfo=timezone.utc)


def filing(identifier, *, source_type="filing", form=None, title=None, days=1,
           content=None):
    """Return an inert original-document fixture with explicit form metadata."""

    metadata = {}
    if form is not None:
        metadata["form"] = form
    if title is not None:
        metadata["title"] = title
    return RawInfoDocument.create(
        document_id=identifier,
        company_id="issuer_fixture",
        source_type=source_type,
        published_at=AS_OF - timedelta(days=days),
        available_at=AS_OF - timedelta(days=days),
        content=content or f"Source fixture {identifier}; no research conclusion.",
        metadata=metadata,
    )


class BasicInfoMenuEntryBoundaryTests(TestCase):
    def test_alias_only_backends_support_fixed_templates_without_rewriting_them(self):
        from stock_opportunity_agent.research.basic_info_orientation import (
            make_orientation_request, orientation_menu,
        )
        from stock_opportunity_agent.research.evolution_output_validation import (
            _validate_plan_for_proposer_context,
        )

        plan = replace(default_information_plan(), basic_info_policy=BasicInfoPolicy((
            make_orientation_request("operating_report"),
            make_orientation_request("market_backbone"),
        )))
        before = deepcopy(plan.to_dict())
        for available in (("filing_body", "price_daily"),
                          ("sec_filing", "historical_price"),
                          ("10-q", "prices")):
            with self.subTest(available=available):
                original_inventory = tuple(available)
                _validate_plan_for_proposer_context(plan, available_source_types=available)
                menu = orientation_menu(available)
                self.assertEqual(set(menu["available_action_ids"]), {
                    "orientation.v1.operating_report", "orientation.v1.market_backbone",
                })
                self.assertEqual(available, original_inventory)
                self.assertEqual(plan.to_dict(), before)
                self.assertEqual(plan.basic_info_policy.requests[0].source_types, ("filing",))
                self.assertEqual(plan.basic_info_policy.requests[1].source_types, ("market_data",))

    def test_social_route_does_not_support_filing_or_author_plan_source_aliases(self):
        from stock_opportunity_agent.models import StructuredValidationError
        from stock_opportunity_agent.research.basic_info_orientation import (
            compile_basic_info_requests, make_orientation_request, orientation_menu,
        )
        from stock_opportunity_agent.research.evolution_output_validation import (
            _validate_plan_for_proposer_context,
        )

        operating = make_orientation_request("operating_report")
        market = make_orientation_request("market_backbone")
        plan = replace(default_information_plan(),
                       basic_info_policy=BasicInfoPolicy((operating, market)))
        available = ("social_media", "price_daily")
        with self.assertRaises(StructuredValidationError) as caught:
            _validate_plan_for_proposer_context(plan, available_source_types=available)
        unsupported = [issue for issue in caught.exception.issues
                       if issue.code == "plan_source_type_unsupported"]
        self.assertEqual(len(unsupported), 1)
        self.assertEqual(unsupported[0].paths, ("B.requests[0].source_types[0]",))
        self.assertEqual(orientation_menu(available)["available_action_ids"],
                         ["orientation.v1.market_backbone"])
        # Compatible backend aliases are execution routes; they do not make
        # the fixed Plan template's own source declaration authorable.
        with self.assertRaises(StructuredValidationError):
            compile_basic_info_requests(BasicInfoPolicy((
                replace(operating, source_types=("sec_filing",)), market,
            )))

    def test_all_five_descriptors_compile_without_mutating_the_plan(self):
        from stock_opportunity_agent.research.basic_info_orientation import (
            compile_basic_info_requests, make_orientation_request, orientation_menu,
        )

        menu = orientation_menu()
        self.assertEqual(menu["version"], "basic-info-orientation-v1")
        self.assertEqual({row["action"] for row in menu["actions"]}, {
            "market_backbone", "operating_report", "management_commentary",
            "scoped_news", "financial_facts",
        })
        for row in menu["actions"]:
            with self.subTest(action=row["action"]):
                for position in (0, 1):
                    request = make_orientation_request(
                        row["action"],
                        lookback_days=row["bounds"]["lookback_days"][position],
                        max_documents=row["bounds"]["max_documents"][position],
                    )
                    policy = BasicInfoPolicy((request,))
                    before = deepcopy(policy.to_dict())
                    compiled, = compile_basic_info_requests(policy)
                    self.assertEqual(policy.to_dict(), before)
                    self.assertIsNone(request.query)
                    self.assertEqual(compiled.query, row["internal_fixed_query"])
                    self.assertEqual(compiled.request_id, request.request_id)

    def test_template_id_cannot_hide_free_semantics_or_noninteger_parameters(self):
        from stock_opportunity_agent.research.basic_info_orientation import (
            compile_basic_info_requests, make_orientation_request,
        )

        canonical = make_orientation_request("operating_report")
        variants = (
            replace(canonical, description=canonical.description + " Find a target price."),
            replace(canonical, source_types=("news",)),
            replace(canonical, query="business operations segments products services customers risks"),
            replace(canonical, lookback_days=True),
            replace(canonical, lookback_days=1.5),
            replace(canonical, lookback_days=731),
            replace(canonical, max_documents=True),
            replace(canonical, max_documents=1.5),
            replace(canonical, max_documents=6),
            replace(canonical, minimum_distinct_periods=2),
            replace(canonical, required_source_groups=(("10-k",),)),
            replace(canonical, request_id="orientation.v2.operating_report"),
        )
        for request in variants:
            with self.subTest(request=request.to_dict()):
                with self.assertRaises(ValidationError):
                    compile_basic_info_requests(BasicInfoPolicy((request,)))

    def test_legal_direct_execution_passes_compiled_recipe_to_the_resolver(self):
        from stock_opportunity_agent.research.basic_info_orientation import (
            compile_basic_info_requests,
        )

        class ReachedResolver(Exception):
            pass

        plan = default_information_plan()
        before = deepcopy(plan.to_dict())
        resolver = mock.Mock()
        resolver.resolve_basic_info.side_effect = ReachedResolver()
        with self.assertRaises(ReachedResolver):
            execute_information_plan(
                plan=plan,
                company_id="issuer_fixture",
                company_basic_source={},
                prediction_time=AS_OF,
                signal_registry=None,
                signal_executor=SimpleNamespace(resolver=resolver),
                controller=None,
                signal_agent=None,
                predictor=None,
                prediction_sink=None,
                ground_truth_provider=None,
            )
        self.assertEqual(resolver.resolve_basic_info.call_args.args[0],
                         compile_basic_info_requests(plan.basic_info_policy))
        self.assertEqual(plan.to_dict(), before)

    def test_raw_proposal_rejects_parameter_coercion_before_archive_parser(self):
        from stock_opportunity_agent.research.basic_info_orientation import (
            make_orientation_request, validate_raw_orientation_policy,
        )

        canonical = make_orientation_request("scoped_news").to_dict()
        for field in ("lookback_days", "max_documents"):
            for value in (True, 1.5, "1"):
                with self.subTest(field=field, value=value):
                    raw = {"requests": [{**canonical, field: value}]}
                    with self.assertRaises(ValidationError):
                        validate_raw_orientation_policy(raw)

    def test_proposer_and_direct_execution_share_template_rejections(self):
        from stock_opportunity_agent.models import StructuredValidationError
        from stock_opportunity_agent.research.basic_info_orientation import (
            compile_basic_info_requests,
        )
        from stock_opportunity_agent.research.evolution_output_validation import (
            _validate_plan_for_proposer_context,
        )

        original = default_information_plan()
        requests = list(original.basic_info_policy.requests)
        index = next(index for index, row in enumerate(requests)
                     if row.request_id == "orientation.v1.operating_report")
        for mutation in (
            {"query": "free research"},
            {"description": "Free original research instructions."},
            {"source_types": ("news",)},
            {"lookback_days": 731},
            {"max_documents": 6},
        ):
            with self.subTest(mutation=mutation):
                changed = list(requests)
                changed[index] = replace(changed[index], **mutation)
                plan = replace(original, basic_info_policy=BasicInfoPolicy(tuple(changed)))
                with self.assertRaises(StructuredValidationError) as compiler_error:
                    compile_basic_info_requests(plan.basic_info_policy)
                with self.assertRaises(StructuredValidationError) as proposer_error:
                    _validate_plan_for_proposer_context(
                        plan, available_source_types=(
                            "market_data", "filing", "earnings_call", "news",
                            "sec_company_facts",
                        ),
                    )
                compiler_issues = {(issue.code, issue.paths)
                                   for issue in compiler_error.exception.issues}
                proposer_issues = {(issue.code, issue.paths)
                                   for issue in proposer_error.exception.issues}
                self.assertTrue(compiler_issues <= proposer_issues)
                resolver = mock.Mock()
                resolver.resolve_basic_info.side_effect = AssertionError("retrieval reached")
                with self.assertRaises(StructuredValidationError) as core_error:
                    execute_information_plan(
                        plan=plan, company_id="issuer_fixture", company_basic_source={},
                        prediction_time=AS_OF, signal_registry=None,
                        signal_executor=SimpleNamespace(resolver=resolver), controller=None,
                        signal_agent=None, predictor=None, prediction_sink=None,
                        ground_truth_provider=None,
                    )
                self.assertEqual(
                    {(issue.code, issue.paths) for issue in core_error.exception.issues},
                    compiler_issues,
                )
                resolver.resolve_basic_info.assert_not_called()

    def test_direct_execution_rejects_free_requests_before_resolving(self):
        invalid = (
            RawInfoRequest("free", "Recent news.", ("news",), 180, 1,
                           query="merger target price"),
            RawInfoRequest("free", "Recent posts.", ("social_media",), 180, 1),
            RawInfoRequest("free", "Recent news.", ("news",), None, 1),
            RawInfoRequest("free", "Recent news.", ("news",), 365, 10),
            RawInfoRequest("free", "Search merger target prices.", ("news",), 180, 1),
        )
        for request in invalid:
            with self.subTest(request=request.to_dict()):
                resolver = mock.Mock()
                # Reaching the resolver is itself the old admission failure;
                # no controller, model, outcome provider or real store exists.
                resolver.resolve_basic_info.side_effect = AssertionError(
                    "unvalidated request reached retrieval"
                )
                plan = replace(default_information_plan(),
                               basic_info_policy=BasicInfoPolicy((request,)))
                with self.assertRaises(ValidationError):
                    execute_information_plan(
                        plan=plan,
                        company_id="issuer_fixture",
                        company_basic_source={},
                        prediction_time=AS_OF,
                        signal_registry=None,
                        signal_executor=SimpleNamespace(resolver=resolver),
                        controller=None,
                        signal_agent=None,
                        predictor=None,
                        prediction_sink=None,
                        ground_truth_provider=None,
                    )
                resolver.resolve_basic_info.assert_not_called()

    def test_archived_free_request_remains_losslessly_readable(self):
        # Readability is distinct from permission to execute this old policy.
        raw = default_information_plan().to_dict()
        raw["basic_info_policy"] = {"requests": [{
            "request_id": "legacy_deep_query",
            "description": "Find an original company filing.",
            "source_types": ["filing"],
            "lookback_days": 730,
            "max_documents": 1,
            "query": "business risk segment economics",
        }]}
        before = deepcopy(raw)
        restored = InformationPlan.from_dict(raw)
        self.assertEqual(restored.to_dict(), before)
        self.assertEqual(raw, before)


class BasicInfoExactFormBoundaryTests(TestCase):
    def test_nonfiling_metadata_cannot_upgrade_source_family(self):
        for source_type in ("news", "market_data", "sec_company_facts", "earnings_call"):
            with self.subTest(source_type=source_type):
                document = filing("nonfiling", source_type=source_type, form="10-K")
                self.assertFalse(_matches_source_type(document, ("10-k",)))

    def test_operating_action_reserves_business_background_then_latest_interim(self):
        from stock_opportunity_agent.research.basic_info_orientation import (
            compile_basic_info_requests, make_orientation_request,
        )

        annual = filing("annual", form="10-K", days=200)
        quarter = filing("quarter", form="10-Q", days=30)
        older_quarter = filing(
            "older_quarter", form="10-Q", days=120,
            content="business operations segments products services customers risks " * 10,
        )
        current = filing("current", form="8-K", days=1)
        for count, documents, expected in (
            (1, (current, annual, quarter), ["annual"]),
            (1, (current, quarter), ["quarter"]),
            (2, (current, annual, older_quarter, quarter), ["annual", "quarter"]),
        ):
            with self.subTest(count=count, expected=expected):
                policy = BasicInfoPolicy((make_orientation_request(
                    "operating_report", max_documents=count,
                ),))
                request, = compile_basic_info_requests(policy)
                selected = _select_required_source_documents(
                    _rank_documents(documents, request), request,
                )
                self.assertEqual([row.document_id for row in selected], expected)
                self.assertTrue(_retrieval_contract_coverage(selected, request)["contract_satisfied"])

    def test_substring_title_reference_and_amendment_do_not_prove_original(self):
        cases = (
            filing("substring", form="110-KX"),
            filing("suffix", form="10-K-unsupported"),
            filing("amendment", form="10-K/A"),
            filing("title_reference", form="8-K",
                   title="Contains an exhibit to Form 10-K"),
            filing("title_only", title="Contains an exhibit to Form 10-K"),
            filing("conflicting_type", source_type="10-k", form="8-K"),
        )
        for document in cases:
            with self.subTest(document=document.document_id):
                self.assertFalse(_matches_source_type(document, ("10-k",)))

    def test_original_annual_or_interim_forms_are_positive_controls(self):
        for form in ("10-K", "10-Q", "20-F", "40-F"):
            for source_type in ("filing", "sec_filing", "filing_body", form.lower()):
                with self.subTest(form=form, source_type=source_type):
                    document = filing("valid", source_type=source_type, form=form)
                    self.assertTrue(_matches_source_type(document, (form.lower(),)))

    def test_current_reports_remain_legal_generic_research_material(self):
        for form in ("8-K", "6-K", "10-K/A"):
            with self.subTest(form=form):
                document = filing("generic", form=form)
                self.assertTrue(_matches_source_type(document, ("filing",)))

    def test_interim_alone_satisfies_annual_or_interim_source_group(self):
        request = RawInfoRequest(
            "coverage_fixture", "Annual or interim source coverage.",
            ("filing",), 730, 1,
            required_source_groups=(("10-k", "10-q", "20-f", "40-f"),),
        )
        quarter = filing("quarter", form="10-Q", days=30)
        newer_current = filing("current", form="8-K", days=1)
        ranked = _rank_documents((quarter, newer_current), request)
        self.assertEqual(ranked[0].document_id, "current")
        selected = _select_required_source_documents(ranked, request)
        self.assertEqual([row.document_id for row in selected], ["quarter"])
        self.assertTrue(_retrieval_contract_coverage(selected, request)["contract_satisfied"])

    def test_current_report_title_cannot_clear_operating_report_gap(self):
        request = RawInfoRequest(
            "coverage_fixture", "Annual or interim source coverage.",
            ("filing",), 730, 1,
            required_source_groups=(("10-k", "10-q", "20-f", "40-f"),),
        )
        document = filing("current", form="8-K", title="Exhibit to Form 10-Q")
        coverage = _retrieval_contract_coverage((document,), request)
        self.assertFalse(coverage["contract_satisfied"])
        self.assertEqual(coverage["satisfied_source_group_count"], 0)
        self.assertEqual(len(coverage["missing_requirements"]), 1)
