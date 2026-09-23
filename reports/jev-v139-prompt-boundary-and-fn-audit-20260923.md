# Jev V139 prompt-boundary and false-negative audit

Date: 2026-09-23

## Corrected conclusion

The large direction gap in the first Jev shadow was primarily an input-contract
defect, not evidence that Jev is intrinsically much more conservative than the
historical LLM.

The original Jev state forwarded `final_context.analysis_prompt`. That field is
an evolvable instruction for an upstream analysis role. In this run it told the
recipient not to generate a prediction and to require a quantitative bridge to
the 2x threshold. The historical LLM received the same `final_context` as
untrusted user payload under a 4,046-character system contract that explicitly
said the opposite: `possible` is a screening category, a probability above 50%,
an explicit price target, and a quantified valuation bridge are not required.
Jev did not have an equivalent chat-role hierarchy to resolve that conflict.

After removing `analysis_prompt` and `context_contract`, adding the fixed active
screening contract, and asking direction as the sole question, Jev matched the
historical LLM's binary choice on all 21 comparable cases. Both paths produced
TP=10, FP=3, TN=6, FN=2 and Binary F1=0.800.

This remains an in-sample diagnostic over one evolved Plan. It repairs the
comparison boundary; it does not establish out-of-sample superiority or approve
a production cutover.

## What was checked

### Case, evidence, and label mapping

- Each of the 21 non-empty historical `final_context` objects matched exactly
  one persisted `blind_predictor_predict` user payload by complete object
  equality.
- Jev case keys and labels came from the same ordered trajectory record. No
  case-to-label or positive-class mapping error was found.
- Both direction probes preserved the frozen source-shadow hash
  `5bd82c478c86d63b482926da34d0481c55924030133932bb6ae645fcf8b7525a`.
- All 42 probe request-body hashes recomputed successfully. Raw responses were
  persisted before parsing, all question ids matched, and neither probe retried.
- The 21 corrected calls used 6,051-13,377 input tokens. The two corrected false
  negatives used 6,970 and 7,172 input tokens. There was no provider error or
  evidence of request truncation.

The evidence objects given to Jev and the historical LLM were therefore the
same. Their effective instructions were not.

### Three controlled direction comparisons

| Path | Accuracy | Precision | Recall | F1 | TP / FP / TN / FN |
|---|---:|---:|---:|---:|---:|
| Original Jev: conflicted state + simultaneous magnitude | 0.667 | 1.000 | 0.417 | 0.588 | 5 / 0 / 9 / 7 |
| Jev diagnostic: conflicted state + direction only | 0.619 | 1.000 | 0.333 | 0.500 | 4 / 0 / 9 / 8 |
| Jev corrected: fixed contract + direction only | 0.762 | 0.769 | 0.833 | **0.800** | 10 / 3 / 6 / 2 |
| Historical LLM | 0.762 | 0.769 | 0.833 | **0.800** | 10 / 3 / 6 / 2 |

Removing the simultaneous magnitude question changed only one raw-context
choice and did not remove the conservative pattern. Repairing the instruction
boundary changed ten four-way choices and eight binary choices. The corrected
binary choices agreed with the historical LLM in 21/21 cases.

The corrected Jev distribution had Brier 0.189, log loss 0.583, and ROC AUC
0.810 on this panel. Those values are descriptive, in-sample diagnostics. Jev
`confidence` is distribution concentration rather than correctness probability;
it cannot be used as a fitness weight.

### Upstream content defects

Two source-data defects remain independent of the Jev prompt repair:

1. `case_020` targets CIK `0001964504`, whose SEC evidence identifies Aris
   Mining Corporation, but the supplied news and earnings-call projection
   discuss Aris Water Solutions, produced-water volumes, the Permian Basin, and
   water-solutions margins. This issuer collision invalidates causal learning
   from the case. Excluding it leaves Jev and the historical LLM still exactly
   aligned, with F1 0.783 on 20 cases.
2. `case_008` contains the target name `Ciena` inside the supposedly anonymous
   final context. Both models received the leak, so it does not explain their
   difference, but it violates blind-evaluation discipline. Excluding both
   cases 008 and 020 again leaves exact Jev/LLM alignment, with F1 0.762 on 19
   cases.

The contaminated case must not generate a Signal or Plan update. The identity
leak also needs upstream remediation before a held-out acceptance run.

## Corrected false negatives

The original seven Jev false negatives were cases 008, 010, 011, 012, 020, 021,
and 023. The corrected contract turned 008, 010, 012, 020, and 023 positive.
Their old false-negative reflections describe the prompt defect or, for case
020, contaminated evidence; they are not valid self-evolution lessons.

Only cases 011 and 021 remain false negatives. They are exactly the same two
false negatives as the historical LLM.

### Case 011: CIK 0001164727, realized 2.0178x

- Corrected Jev choice: `unlikely`; positive probability 0.11; confidence 0.78.
- Evidence favoring rejection: the supplied $67 analyst target was only modestly
  above the 63.444 baseline; guidance was reaffirmed; divestitures and cash did
  not quantify a 2x bridge.
- Underweighted evidence: more than 60% year-to-date appreciation, a sharp
  high-volume move to 65.75, and the possibility that the re-rating could
  continue beyond the analyst target.
- Existing historical reflection: the decision treated the analyst target as a
  ceiling and allowed threshold arithmetic to crowd out a momentum-extension
  scenario.

This is a useful hypothesis for future cases: an analyst target below 2x should
not act as a hard ceiling when strong price-volume confirmation is already
present. The realized outcome was only 2.0178x, so this borderline case is weak
evidence for a broad rule and must be validated across cases before promotion.

### Case 021: CIK 0001658551, realized 2.3746x

- Corrected Jev choice: `unlikely`; positive probability 0.06; confidence 0.89.
- Evidence favoring rejection: a $3.50 equity offering and dilution, declining
  pre-cutoff price, negative revenue growth, negative operating cash flow, high
  burn, and no supplied within-horizon readout or quantified valuation bridge.
- Underweighted evidence: approximately $56.9-65.5 million of offering proceeds,
  runway into 2026, a Chief Commercial Officer appointment, Phase 3 preparation,
  and commercialization readiness from a low starting price.
- Existing historical reflection: the decision counted financing mainly as
  dilution, rather than separating dilution from runway extension and catalyst
  funding; it also treated the lack of a quantified bridge as decisive.

This produces a concrete research instruction: decompose financing events into
dilution, runway, milestone funding, and commercialization readiness, then seek
the dated catalyst that can fall inside the horizon. It does not prove that
runway extension caused the later surge.

## Reflection value and limits

The shadow made no chat-LLM explanation or post-label reflection calls. There
are no newly generated Jev-specific reflection texts. The descriptions above
use the already persisted historical LLM reflections because corrected Jev and
the historical LLM made the same decisions on every case.

These reflections are valuable for generating falsifiable changes to evidence
requests, weighting rules, and scenario checks. They cannot identify the actual
cause of the later price move because the reflection packet contains the label
and ex-ante context, not post-outcome causal evidence. A safe self-evolution
flow therefore treats them as candidate lessons and requires cross-case or
held-out validation before changing a Signal, Plan, routing rule, or fitness.

## Suitability for self-evolution

Jev is suitable for narrow, fixed, repeated decisions when the state contains
only the evidence needed for that question and the criteria fully encode the
active contract. It is useful here for:

- producing an immutable category plus full choice distribution;
- highlighting concentrated wrong answers and LLM/Jev disagreements;
- supplying an extra realized-label probability signal to the reflection LLM;
- running cheap, reproducible screening checks after the contract is frozen.

It should not replace the reflection LLM or be asked to infer a long causal
chain from a large mixed-purpose context. The existing Signal-routing shadow is
also not ready for replacement: its `context_only` option is broad enough that
almost any prefiltered card can appear useful, leading to 88.5% non-`no_match`
decisions and cap saturation in 77/80 rounds. That is a routing-criteria design
gap. A useful next routing test needs a narrower necessity or incremental-value
criterion and must execute the alternative Signal sets before claiming outcome
value.

## Implemented correction

Runtime and shadow now share one Jev request builder. It strips upstream role
instructions, supplies the fixed screening semantics, asks direction alone, and
requests magnitude only after a positive direction. Probability and confidence
remain extra reflection signals and do not affect fitness or promotion.

Artifacts:

- Raw-context probe manifest:
  `b4d595095d041c4316f5cd1b355533c77f18c6fc11893b5c13665b483dad6f92`
- Corrected parity probe manifest:
  `a2bca5af6cbbd1fe918efe15eec9c446ebcef8a18edb6c3c3a1ffb9483772772`
- Machine-readable audit:
  `reports/jev-v139-prompt-boundary-and-fn-audit-summary-20260923.json`
