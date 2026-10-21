def _shared_distinctive_phrase(
    left: str,
    right: str,
    *,
    minimum_words: int = 3,
    target_need: str | None = None,
) -> str | None:
    """Return one shared ordered or reordered topic, ignoring routing filler."""

    def words(value: str) -> tuple[str, ...]:
        normalized: list[str] = []
        for token in re.findall(r"[a-z0-9]+", value.casefold()):
            if token in _NEED_RESIDUAL_GENERIC_TOKENS:
                continue
            normalized.append(_singularize_topic_token(token))
        return tuple(normalized)

    left_words = words(left)
    right_words = words(right)

    if target_need is not None:
        # Contrast literal target clauses before interpreting shared objects or
        # periods as a residual-only facet. The original conservative check is
        # retained when the target does not expose an unambiguous split.
        clauses = tuple(
            clause.strip()
            for clause in re.split(r"[;,]\s*(?:(?:and|or)\s+)?", target_need,
                                   flags=re.IGNORECASE)
            if clause.strip()
        )
        def topic_words(value: str) -> tuple[str, ...]:
            # A literal year comparison qualifies all facets; its FY/versus
            # words are not a topic solely because it appears in one clause.
            value = re.sub(
                r"\b(?:fy\s*)?(?:19|20)\d{2}\s+(?:versus|vs\.?|to)\s+"
                r"(?:fy\s*)?(?:19|20)\d{2}\b",
                " ", value, flags=re.IGNORECASE,
            )
            return tuple(token for token in words(value)
                         if not token.isdigit()
                         and not _TEMPORAL_TOPIC_TOKEN.fullmatch(token))

        scope_words: set[str] = set()
        topical_clauses: list[tuple[str, ...]] = []
        topical_texts: list[str] = []
        for clause in clauses:
            bound = _EXPLICIT_AS_OF_BOUND.search(clause) or _SYMBOLIC_AS_OF_BOUND.search(clause)
            prefix = clause[:bound.start()].strip() if bound else ""
            if bound and re.fullmatch(
                r"(?:(?:using|based on|from|with)\s+)?(?:only\s+)?"
                r"(?:(?:disclosures?|information|data|sources?|evidence)\s+)?"
                r"(?:(?:available|published|disclosed)\s*)?",
                prefix, re.IGNORECASE,
            ) and not clause[bound.end():].strip(" .?!"):
                scope_words.update(topic_words(clause))
            else:
                topical_clauses.append(topic_words(clause))
                topical_texts.append(clause)
        clause_words = [set(clause) - scope_words for clause in topical_clauses]
        unique_words = [
            content - set().union(*(other for index, other in enumerate(clause_words)
                                    if index != own_index))
            for own_index, content in enumerate(clause_words)
        ]
        residual_topics = set(topic_words(right))
        # Losing one modifier does not remove a retained facet: its other
        # clause-specific anchors may still be present in the residual.
        answered = [clause for clause, unique in zip(topical_clauses, unique_words)
                    if unique and not unique & residual_topics]
        retained = [clause for clause, unique in zip(topical_clauses, unique_words)
                    if unique & residual_topics]
        # Bare comma-separated nouns can be one facet's list rather than
        # separate questions. They do not establish a safe contrast.
        if (answered and retained and all(unique_words)
                and all(len(set(clause)) >= 2 for clause in topical_clauses)):
            common = set().union(*map(set, answered)) | scope_words
            distinctive = set().union(*map(set, retained)) - common
            distinctive_left = " ".join(token for token in left_words if token in distinctive)
            distinctive_right = " ".join(token for token in right_words if token in distinctive)
            return (
                _shared_distinctive_phrase(distinctive_left, distinctive_right)
                or _shared_distinctive_phrase(
                    distinctive_left, distinctive_right, minimum_words=2,
                )
            )

        # A leading object can scope a noun-facet list without being repeated
        # in each arm. Prove that split locally; do not recognize proper names
        # or erase every word shared with the target.
        def arm_words(value: str) -> tuple[str, ...]:
            value = _EXPLICIT_AS_OF_BOUND.sub(" ", value)
            value = _SYMBOLIC_AS_OF_BOUND.sub(" ", value)
            return topic_words(value)

        arms: list[tuple[str, ...]] = []
        for index, text in enumerate(topical_texts):
            parts = re.split(r"\s+(?:and|or)\s+", text, flags=re.IGNORECASE)
            split_words = [arm_words(part) for part in parts]
            if index and len(parts) > 1 and all(len(set(part)) >= 2 for part in split_words):
                arms.extend(split_words)
            else:
                arms.append(arm_words(text))

        def contains(sequence: tuple[str, ...], phrase: tuple[str, ...]) -> bool:
            return any(sequence[start:start + len(phrase)] == phrase
                       for start in range(len(sequence) - len(phrase) + 1))

        def without(sequence: tuple[str, ...], phrase: tuple[str, ...]) -> tuple[str, ...]:
            result: list[str] = []
            index = 0
            while index < len(sequence):
                if sequence[index:index + len(phrase)] == phrase:
                    index += len(phrase)
                else:
                    result.append(sequence[index])
                    index += 1
            return tuple(result)

        if len(arms) >= 3:
            for size in range(len(arms[0]) - 2, 1, -1):
                prefix = arms[0][:size]
                if not contains(right_words, prefix):
                    continue
                stripped = [without(arm, prefix) for arm in arms]
                contents = [set(arm) - scope_words for arm in stripped]
                distinct = [content - set().union(*(other for index, other in enumerate(contents)
                                                    if index != own))
                            for own, content in enumerate(contents)]
                if not all(len(content) >= 2 for content in distinct):
                    continue
                answered_flags: list[bool] = []
                retained_flags: list[bool] = []
                for index, content in enumerate(distinct):
                    removed = tuple(token for token in stripped[index]
                                    if token in content and token not in residual_topics)
                    answered_flags.append(len(set(removed)) >= 2 and contains(left_words, removed))
                    retained_flags.append(len(content & residual_topics) >= 2)
                answered_arms = [i for i, (a, r) in enumerate(zip(answered_flags, retained_flags)) if a and not r]
                retained_arms = [i for i, (a, r) in enumerate(zip(answered_flags, retained_flags)) if r and not a]
                if answered_arms and retained_arms:
                    # A shortened retained head still identifies its literal
                    # arm. Do not suggest deleting the common object, and do
                    # not lose the error after that object has been removed.
                    retained_specific = set().union(*(
                        content & residual_topics for i, content in enumerate(distinct)
                        if i not in answered_arms
                    ))
                    conflicts = [token for token in without(left_words, prefix)
                                 if token in retained_specific]
                    if conflicts:
                        return " ".join(dict.fromkeys(conflicts))
                    if (0 in retained_arms and contains(left_words, prefix)
                            and all(a != r for a, r in zip(answered_flags, retained_flags))):
                        shared = _shared_distinctive_phrase(
                            " ".join(without(left_words, prefix)),
                            " ".join(without(right_words, prefix)), minimum_words=2,
                        )
                        return shared

    left_topic_words = tuple(
        token
        for token in left_words
        if not token.isdigit() and not _TEMPORAL_TOPIC_TOKEN.fullmatch(token)
    )
    right_topic_words = tuple(
        token
        for token in right_words
        if not token.isdigit() and not _TEMPORAL_TOPIC_TOKEN.fullmatch(token)
    )
    right_ngrams = {
        right_topic_words[start : start + size]
        for size in range(minimum_words, len(right_topic_words) + 1)
        for start in range(len(right_topic_words) - size + 1)
    }
    for size in range(len(left_topic_words), minimum_words - 1, -1):
        for start in range(len(left_topic_words) - size + 1):
            phrase = left_topic_words[start : start + size]
            if phrase in right_ngrams:
                return " ".join(phrase)
    right_word_set = set(right_topic_words)
    reordered_overlap: list[str] = []
    for token in left_topic_words:
        if token in reordered_overlap or token not in right_word_set:
            continue
        reordered_overlap.append(token)
    if len(reordered_overlap) >= minimum_words:
        return " ".join(reordered_overlap)
    temporal_overlap = [
        token
        for token in left_words
        if token in right_words
        and (token.isdigit() or _TEMPORAL_TOPIC_TOKEN.fullmatch(token))
    ]
    if len(reordered_overlap) >= 2 and temporal_overlap:
        return " ".join(dict.fromkeys((*reordered_overlap, *temporal_overlap)))
    return None
