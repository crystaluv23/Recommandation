"""Network-free associated controls for narrative navigation integration."""
from contextlib import ExitStack
import socket
import unittest
from unittest.mock import patch

attempts=[]


def forbidden(*args,**kwargs):
    attempts.append('network')
    raise AssertionError('network forbidden in offline navigation checks')


if __name__=='__main__':
    names=['test_signal_source_reading','test_data_disclosure','test_data_resolution','test_stage_contracts',
        'test_evolution_signal_role_adapters','test_signal_edge_correction','test_signal_correction_reservation',
        'test_signal_measurement_input_selection','test_signal_financials','test_signal_execution_provenance']
    with ExitStack() as guards:
        for target,name in ((socket,'create_connection'),(socket.socket,'connect'),(socket.socket,'connect_ex')):
            guards.enter_context(patch.object(target,name,side_effect=forbidden))
        result=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromNames(names))
    print('network_attempts='+str(len(attempts)))
    if not result.wasSuccessful() or attempts: raise SystemExit(1)
