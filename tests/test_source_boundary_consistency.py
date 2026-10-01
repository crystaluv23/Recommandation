"""Cross-consumer source visibility and real Mining wire regression checks."""

import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import TestCase

from stock_opportunity_agent.data.disclosure import document_catalog
from stock_opportunity_agent.data.markup import nonvisible_html_ranges
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import RawInfoRequest, _normalized_visible_text, _select_context_spans
from stock_opportunity_agent.research.evolution_core import _normalized_projection_text
from stock_opportunity_agent.research.evolution_output_validation import _market_data_absence_paths
from stock_opportunity_agent.research.evolution_research_validation import _future_source_date_refs
from stock_opportunity_agent.research.evolution_transport import ExternalRequestPending, _CaseIdentityProjection
from stock_opportunity_agent.research.mining_agent_tools import narrative_catalog
from stock_opportunity_agent.research.mining_role_model import MiningAgentRoleModel
from tests.test_same_request_guard import _client


AS_OF = datetime(2025, 7, 31, tzinfo=timezone.utc)


class SourceBoundaryConsistencyTests(TestCase):
    def test_visibility_excludes_nested_and_incomplete_hidden_content_across_consumers(self):
        examples = (
            ('alpha<div hidden>secret<span>nested</span>tail</div>omega', 'alpha omega'),
            ('<head><title>secret</title></head><p>cash 10</p>', 'cash 10'),
            ('x<div STYLE="DISPLAY: NONE !important">secret<div>nested</div>end</div>y', 'x y'),
            ('x<ix:header><ix:hidden>taxonomy</ix:hidden></ix:header>y', 'x y'),
            ('x<script>secret</script><style>secret</style><template>secret</template>y', 'x y'),
            ('x<div style="visibility:hidden">secret</div>y', 'x y'),
            ('x<ix:header>unclosed', 'x'),
            ('x<div aria-hidden="true">ordinary</div>y', 'x ordinary y'),
            ('x<div style="display:block">ordinary</div>y', 'x ordinary y'),
        )
        for raw, expected in examples:
            with self.subTest(raw=raw):
                visible, origins = _normalized_visible_text(raw)
                projected, runs = _normalized_projection_text(raw, raw_offset=100)
                self.assertEqual(''.join(visible).strip(), expected)
                self.assertEqual(projected, expected)
                hidden = nonvisible_html_ranges(raw)
                self.assertTrue(all(not any(a <= start < b for a, b in hidden)
                                    for ch, (start, end) in zip(visible, origins) if not ch.isspace()))
                self.assertTrue(all(100 <= a <= b <= 100 + len(raw) for _, _, a, b in runs))

    def test_hidden_header_cannot_consume_body_budget_or_hide_shared_read_directory(self):
        header = '<div hidden><ix:header>' + ('taxonomy 2026 ' * 8000) + '</ix:header></div>'
        body = '<h1>Item 1. Financial Statements.</h1><p>Operating revenues 14876 and cash 1203.</p>'
        raw = header + body
        doc = RawInfoDocument.create(document_id='filing', company_id='issuer', source_type='filing',
                                     published_at=AS_OF, available_at=AS_OF, content=raw)
        request = RawInfoRequest(request_id='operating', description='Inspect operating report.',
                                 source_types=('filing',), lookback_days=730, max_documents=1)
        spans = _select_context_spans((doc,), request, 2000, as_of=AS_OF)
        self.assertTrue(spans)
        self.assertLessEqual(sum(s.billable_chars for s in spans), 2000)
        for span in spans:
            self.assertGreaterEqual(span.start, len(header))
            self.assertEqual(span.exact_text, raw[span.start:span.end])
        projected = ' '.join(_normalized_projection_text(s.exact_text)[0] for s in spans)
        self.assertIn('Operating revenues 14876', projected)
        self.assertNotIn('taxonomy', projected)
        catalog = document_catalog(RawInfoStore(documents=(doc,)), company_id='issuer', as_of=AS_OF)
        card = catalog['cards'][0]
        mining = narrative_catalog((doc, doc), ())
        row = mining[0]['windows'][0]['entries'][0]
        self.assertEqual(len(mining[0]['windows'][0]['entries']), 1)
        self.assertEqual(row['sections'], card['sections'])
        self.assertEqual(row['readable_start'], card['readable_start'])
        self.assertGreaterEqual(row['readable_start'], len(header))
        section = row['sections'][0]
        self.assertIn('Item 1.', raw[section['raw_start']:section['raw_end']])
        self.assertTrue(row['discovery_only'])
        self.assertEqual(doc.content, raw)

    def test_market_absence_links_the_right_subject_and_respects_denials(self):
        baseline = {'status': 'available'}
        affirmative = ('No market data was supplied.', 'Market data is missing.',
                       'Market data was not available.', 'No price or market data is available.',
                       'No financial projections or market data are provided.')
        allowed = ('The gap was not missing market data but missing forward projections.',
                   'I did not claim market data was absent.',
                   'This is not a claim that all market data was absent.',
                   'The error was not that market data was absent, but that I underweighted it.',
                   'Market data was not missing.', 'If market data is unavailable, request it.',
                   'Market data is available but forward estimates are missing.')
        for text in affirmative + allowed:
            with self.subTest(text=text):
                self.assertEqual(bool(_market_data_absence_paths((('reasons', (text,)),), baseline)),
                                 text in affirmative)
        self.assertEqual(_market_data_absence_paths((('reasons', affirmative),), {'status': 'unavailable'}), [])

    def test_bounded_future_estimates_keep_later_publication_and_actuals_forbidden(self):
        allowed = (
            'What analyst consensus estimates for 2025 and 2026 EPS and revenue were published and available as of 2025-07-31?',
            'Retrieve 2026 consensus EPS estimates available by the prediction date.',
            'Provide the expected 2026 launch schedule disclosed as of the prediction date.',
            'What 2025 guidance was available as of 2025-07-31?',
            'What had the issuer disclosed by 2025-07-31 about the timing of a report To Be Released in November 2025?',
        )
        prohibited = (
            'Fetch analyst consensus estimates published in 2026.',
            'Fetch 2026 estimates published in 2026 and compare with estimates available as of 2025-07-31.',
            'Inspect forecasts released on 2026-01-15 compared to estimates available as of 2025-07-31.',
            'Read Q3 2025 estimates released Q3 2025 compared with estimates available as of 2025-07-31.',
            'What 2026 actual revenue results are available as of 2025-07-31?',
            'What 2026 EPS estimates and realized results were available as of 2025-07-31?',
            'Read 2026 forecasts as of 2026-07-31.',
            'Fetch the latest 2026 earnings release.',
            'Check the 2026 estimates without requiring results published after the prediction date.',
            'Fetch estimates released after the prediction date and compare with those available as of 2025-07-31.',
        )
        for text in allowed + prohibited:
            with self.subTest(text=text):
                self.assertEqual(bool(_future_source_date_refs(text, date(2025, 7, 31),
                                 field_name='next_information_needs')), text in prohibited)

    def test_multiple_explicit_issuer_ciks_and_domains_restore_without_masking_financial_values(self):
        aliases = ('cik_0002009312', 'cik_0000895728', 'Aureus', 'Enbridge', 'Enbridge Inc.')
        projection = _CaseIdentityProjection(aliases, '', '', expand_aliases=False)
        value = {'sources': [{'cik': 2009312}, {'cik': 895728}], 'cash': 895728,
                 'quote': '0002009312 https://aureusgreenway.com/20250630 https://enbridgeenergy.com/2025 '
                          'namespace_aureusgreenway.com_20250630 https://www.aureusgreenway.com/2025 '
                          'https://fasb.org/us-gaap/2025', 'business': 'energy efficiency in green travel'}
        view, inverse = projection.project(value)
        self.assertNotIn('0002009312', json.dumps(view))
        self.assertNotIn('aureus', json.dumps(view).lower())
        self.assertNotIn('enbridge', json.dumps(view).lower())
        self.assertIn('https://fasb.org/us-gaap/2025', view['quote'])
        self.assertEqual(view['business'], value['business'])
        self.assertEqual(view['cash'], value['cash'])
        self.assertEqual(projection.restore(view, inverse), value)

    def test_production_mining_adapter_wire_masks_and_restores_tool_handle_from_exact_cache(self):
        aliases = ('cik_0002009312', 'Aureus', 'Aureus Greenway Golf Club Limited')
        handle = 'document-sec:cik_0002009312:000149315225011966'
        view = {'research_axis': {'axis': 'direction'}, 'label_map': {'case-001': 'positive'},
                'budget': {}, 'measurable_evidence_manifest': {}, 'signal_catalog': [],
                'last_action_result': {'document_ref': handle,
                                      'masked': 'CIK 0002009312 http://aureusgreenway.com/20250630'}}
        with tempfile.TemporaryDirectory() as directory:
            caller = _client(Path(directory))
            model = MiningAgentRoleModel(caller, identity_aliases=aliases)
            with self.assertRaises(ExternalRequestPending) as pending:
                model.next_action(view)
            recorded = json.loads(Path(pending.exception.request_path).read_text())
            wire = recorded['request']['wire_request']['body_utf8']
            self.assertNotIn('0002009312', wire)
            self.assertNotIn('aureusgreenway', wire.lower())
            anonymous = json.loads(recorded['request']['messages'][-1]['content'])
            caller.cache.store(recorded['request_hash'], {
                'json_output': {'action': 'read_span', 'document_ref': anonymous['last_action_result']['document_ref'],
                                'offset': 12000, 'length': 4000},
                'model': 'deepseek-v4-flash', 'usage': {'tokens': 10, 'cost': 0},
            })
            result = model.next_action(view)
            self.assertEqual(result['document_ref'], handle)
            self.assertEqual(result['offset'], 12000)
            self.assertIsNone(getattr(caller._chain_state, 'identity_projection', None))
            self.assertEqual(view['last_action_result']['document_ref'], handle)
