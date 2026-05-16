"""
graph_builder.py
----------------
Builds a conflict graph from a list of subjects for the ClashZero
exam timetable generator.

Each subject is a vertex; an edge is drawn between two subjects when
they share at least one enrolled student, meaning they cannot be
scheduled in the same time slot.
"""

from __future__ import annotations


class GraphBuilder:
    """Constructs an adjacency-list conflict graph from subject data.

    The graph is represented as a dictionary that maps every
    ``subject_id`` to the set of ``subject_id`` values it conflicts
    with (i.e. shares at least one student with).

    Usage::

        from core.graph_builder import GraphBuilder

        graph = GraphBuilder.build_graph(subjects)
    """

    @staticmethod
    def subjects_conflict(subject_a: dict, subject_b: dict) -> bool:
        """Return ``True`` if two subjects share at least one student.

        Parameters
        ----------
        subject_a:
            A subject dictionary containing at minimum a ``"students"``
            key whose value is a list of student identifiers.
        subject_b:
            A second subject dictionary with the same structure.

        Returns
        -------
        bool
            ``True`` when the student sets of both subjects overlap,
            ``False`` otherwise.

        Raises
        ------
        ValueError
            If either subject is missing the ``"students"`` field or if
            the field is not iterable.
        """
        for label, subject in (("subject_a", subject_a), ("subject_b", subject_b)):
            if "students" not in subject:
                raise ValueError(
                    f"Subject '{subject.get('subject_id', label)}' "
                    "is missing the required 'students' field."
                )
            if not isinstance(subject["students"], (list, set, tuple)):
                raise ValueError(
                    f"Subject '{subject.get('subject_id', label)}' has an "
                    "invalid 'students' field; expected a list."
                )

        students_a: set[str] = set(subject_a["students"])
        students_b: set[str] = set(subject_b["students"])

        return not students_a.isdisjoint(students_b)

    @staticmethod
    def build_graph(subjects: list[dict]) -> dict[str, set[str]]:
        """Build and return a conflict graph from a list of subjects.

        Parameters
        ----------
        subjects:
            A list of subject dictionaries.  Each dictionary **must**
            contain:

            * ``"subject_id"`` – a unique string identifier.
            * ``"students"``   – a list of student ID strings.

        Returns
        -------
        dict[str, set[str]]
            An adjacency list where every key is a ``subject_id`` and
            its value is the set of ``subject_id`` values it conflicts
            with.  Isolated vertices (no conflicts) are still present
            in the dictionary with an empty set.

        Raises
        ------
        ValueError
            * If ``subjects`` is not a list.
            * If any subject is missing ``"subject_id"``.
            * If duplicate ``subject_id`` values are detected.
            * If the ``"students"`` field is absent or invalid.

        Examples
        --------
        >>> subjects = [
        ...     {"subject_id": "CS101", "students": ["S001", "S002"]},
        ...     {"subject_id": "MA101", "students": ["S002", "S003"]},
        ...     {"subject_id": "PH101", "students": ["S004"]},
        ... ]
        >>> GraphBuilder.build_graph(subjects)
        {'CS101': {'MA101'}, 'MA101': {'CS101'}, 'PH101': set()}
        """
        if not isinstance(subjects, list):
            raise ValueError("'subjects' must be a list of subject dictionaries.")

        if len(subjects) == 0:
            # Return an empty graph; caller decides how to handle it.
            return {}

        # ── Validate individual subjects and detect duplicates ──────────
        seen_ids: set[str] = set()
        for subject in subjects:
            if "subject_id" not in subject:
                raise ValueError(
                    "A subject entry is missing the required 'subject_id' field."
                )

            subject_id: str = subject["subject_id"]

            if not isinstance(subject_id, str) or not subject_id.strip():
                raise ValueError(
                    "'subject_id' must be a non-empty string; "
                    f"got {subject_id!r}."
                )

            if subject_id in seen_ids:
                raise ValueError(
                    f"Duplicate subject_id detected: '{subject_id}'. "
                    "Every subject must have a unique identifier."
                )
            seen_ids.add(subject_id)

            # Validate students field early (delegates to subjects_conflict later,
            # but we catch structural issues here for clearer error messages).
            if "students" not in subject:
                raise ValueError(
                    f"Subject '{subject_id}' is missing the 'students' field."
                )
            if not isinstance(subject["students"], (list, set, tuple)):
                raise ValueError(
                    f"Subject '{subject_id}': 'students' must be a list."
                )

        # ── Initialise every vertex with an empty adjacency set ─────────
        adjacency: dict[str, set[str]] = {s["subject_id"]: set() for s in subjects}

        # ── Examine every pair of subjects exactly once ─────────────────
        for i in range(len(subjects)):
            for j in range(i + 1, len(subjects)):
                subject_a = subjects[i]
                subject_b = subjects[j]

                if GraphBuilder.subjects_conflict(subject_a, subject_b):
                    id_a: str = subject_a["subject_id"]
                    id_b: str = subject_b["subject_id"]

                    # Add edges in both directions (undirected graph).
                    adjacency[id_a].add(id_b)
                    adjacency[id_b].add(id_a)

        return adjacency