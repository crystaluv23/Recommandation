PYTHONPATH=.:src:scripts /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 - <<'PY'
from tests.test_unavailable_finding_repair import UnavailableFindingRepairTests as T
from stock_opportunity_agent.research.evolution_research_validation import _unavailable_signal_state_errors
from stock_opportunity_agent.research.evolution_core import ResearchState
fixture=T();rows=[]
for text in [
 'Customer concentration is unavailable, so its coverage remains unknown.',
 'Customer concentration is weak.',
 'Customer concentration is 0%.',
 'Customer concentration is unknown, but customer concentration is weak.',
 'Commercial expansion was disclosed. Customer concentration remains unknown.',
 'Customer concentration remains unknown; financing has no binding change.',
 'Customer concentration is unavailable and is not evidence of economic absence.',
]:
 value=fixture.prior().to_dict();value['current_beliefs'].append(text)
 detected=_unavailable_signal_state_errors(fixture.prior(),ResearchState.from_dict(value),fixture.batch())
 step,caller=fixture.reflect(value,extra_outputs=(fixture.prior().to_dict(),))
 rows.append({'text':text,'helper_issues':len(detected),'accepted_unchanged':text in step.value.current_beliefs,'calls':len(caller.calls)})
print(__import__('json').dumps(rows,indent=2))
PY
