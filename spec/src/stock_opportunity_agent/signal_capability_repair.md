# Restricted historical capability repair

Owns the implementation delegated by `SignalRegistry.capability_repair(plan,
plan_hash=...)`. The approved scope and unchanged ordinary promotion policy are
defined in [signal_library](signal_library.md#explicit-capability-repair-of-an-unhealthy-historical-registry).
The helper depends on the capability layer only; it must not import research
or weaken its full validator. The upper preparation driver invokes the genuine
full candidate validator against the immutable original baseline, checks batch
duplicates, persists complete validation/admission records and freezes the plan.
Recovery reuses only these exact bound records, not a validation against a
partially advanced successor. Shared execution-behavior identity lives in the
capability layer and is reused by the existing candidate validator.

The plan schema `signal-capability-repair-plan-v1` binds a separate authority
file by path/hash, transition id, candidate hashes, exact admission keys and
admission-file hashes, complete real validation records, validator identity and
code-file bindings. Its externally frozen hash identifies this one transaction.
The authority `signal-capability-repair-authority-v1` binds the user's explicit
approval/proposal receipt, original root/version/ordered refs/definition hash,
every original relative path/hash, exact disabled reasons, explicitly approved
spec/fixture changes and declared synthetic fixture CIK. It is frozen before
preparation; an arbitrary changed plan or authority cannot recover an existing
transaction. Control files belong outside either Registry; input source and
successor/candidate roots must not alias or nest in the original source.

All disabled refs must have exactly one next version. Non-approved definitions
and skills are identical except version; new fixtures differ solely by explicit
body+metadata CIK with identical old values, units, dates, source family, expected
outcomes and other fields. Explicitly approved changes must equal their exact
authority-bound spec and fixtures. Admission-v1 must match candidate, input hash,
validator identity, complete nonempty validation and exact immutable record hash.
The same rename-resistant behavior identity and normalized-description checks
exclude duplicates against other baseline identities and within the batch.

Before prepared, compare the complete successor byte inventory to the original.
On recovery, original files remain immutable except the exact designated output
manifests and registry version; new files are limited to exact staged next-version
spec/tests/admission, the transaction and any previously missing empty default
stats required by the existing materializer. Verify contents of every permitted
partial state, not merely filenames. Reject symlinks, deletion, unknown files,
unrelated prepared transitions and unknown transition status. A read-only original
view is constructed without constructor side effects and must still reproduce
the exact failure map and original immutable definition snapshot.

Prepared/applied transitions bind the complete plan/authority identity. Prepared
blocks ordinary reads; only this exact repair may use recovery access. The shared
existing materializer and admission copy are reused. A repair performs the actual
full capability audit and rechecks complete membership and permitted bytes before
any version increment, promotion or applied marker; output freeze must pass too.
All permitted fault points recover precisely the same versions/admissions once.
Applied replay verifies all nine exact promotion markers and the complete applied
record without writes. Compare canonical JSON identities, preserving scalar types;
Python's True==1 or 13==13.0 cannot make altered records an exact replay.
Ordinary readers also verify a repair-applied record's complete shape/plan hash,
strict version relation and current raw local complete definitions/skills hash.
The committed local admission bytes/keys and input/candidate lineage also match
the frozen plan; manifest and definition version fields retain integer types.
Verify the historical output refs at the repair output version, not mutable
latest refs forever. Current version may advance under the existing ordinary
promotion contract. At the repair output version itself require latest membership
to equal that output; later updates/additions preserve the old exact versions,
skills and admissions while remaining readable. This repair check adds no new
successor authorization or alternate transition-chain policy.
Recompute the historical spec/skill/tests content hash for every repaired ref,
using the same shared version hash as candidate and stable admission readers;
checking a stored candidate-hash string alone cannot preserve historical proof.
Changing only prepared to applied cannot expose an uncommitted output. This
check uses no recursive Registry reads and needs no original source, candidate
directory or external authority files to read a portable committed Registry.
Failure leaves prepared state unreadable, with no ordinary publication claim.
Original source files are checked again after successful application. Missing
historical runtime stats may be initialized to exact empty defaults only in the
successor, never imported as new-version effect or committed learning.

Tests and real migration must cover input drift, identity-only scope, wrong
approval payloads, missing/legacy/mutated admissions, duplicate behaviors,
all relevant materialization/version/marker faults, complete-output failure,
unrelated prepared transitions and idempotent applied replay. Publication and
recovery evidence do not prove fresh consumers, Mining, Slow completion or gain.
