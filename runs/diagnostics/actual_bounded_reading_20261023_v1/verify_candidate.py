"""Offline candidate controls and source-only navigation measurements."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

from stock_opportunity_agent.data.disclosure import document_card
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.research.evolution_core import _normalized_projection_text

OUT = Path(__file__).resolve().parent
attempts = []


def forbidden(*args, **kwargs):
    attempts.append('forbidden')
    raise AssertionError('offline validation cannot access network')


if __name__ == '__main__':
    with ExitStack() as guards:
        for target, name in ((socket, 'create_connection'), (socket.socket, 'connect')):
            guards.enter_context(patch.object(target, name, side_effect=forbidden))
        oracle_path = OUT/'current-oracle/oracle.json'
        oracle = json.loads(oracle_path.read_bytes())
        navigation = []
        for source in oracle['bindings']['sources']:
            path = Path(source['path'])
            assert hashlib.sha256(path.read_bytes()).hexdigest() == source['sha256']
            document = RawInfoDocument.from_dict(json.loads(path.read_bytes()))
            text, runs = _normalized_projection_text(document.content)
            card = document_card(document, include_sections=True)
            excerpts = []
            for excerpt in oracle['source_excerpts']:
                if excerpt['document_id'] != document.document_id:
                    continue
                start, end = excerpt['content_char_start'], excerpt['content_char_end']
                assert document.content[start:end] == excerpt['literal']
                overlap = [(a, b) for a, b, x, y in runs if x < end and start < y]
                excerpts.append({'excerpt_id': excerpt['excerpt_id'],
                    'normalized_start_bound': min(a for a, b in overlap),
                    'normalized_end_bound': max(b for a, b in overlap)})
            navigation.append({'document_id':document.document_id, 'normalized_characters':len(text),
                'current_signal_card_navigation':'preview140/read_start0/coordinate_length only',
                'existing_data_section_count':card.get('section_count',0),
                'existing_data_visible_sections':len(card.get('sections',())),
                'existing_data_section_coordinates':'raw; not interchangeable with normalized Signal reads',
                'source_only_review_excerpts':excerpts})
        (OUT/'narrative-navigation.json').write_text(json.dumps({
            'scope':'input-only diagnosis; oracle coordinates were never shown to a production role',
            'oracle_sha256':hashlib.sha256(oracle_path.read_bytes()).hexdigest(),
            'sources':navigation},indent=2)+'\n')
        names = ['test_signal_source_reading', 'test_data_resolution', 'test_stage_contracts',
            'test_evolution_signal_role_adapters', 'test_signal_edge_correction',
            'test_signal_correction_reservation', 'test_signal_measurement_input_selection',
            'test_signal_financials', 'test_signal_execution_provenance']
        suite = unittest.defaultTestLoader.loadTestsFromNames(names)
        result = unittest.TextTestRunner().run(suite)
        print('network_attempts=' + str(len(attempts)))
        if not result.wasSuccessful() or attempts:
            raise SystemExit(1)
