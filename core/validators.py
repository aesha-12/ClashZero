"""
validators.py
-------------
Validation utilities for the ClashZero exam timetable generator.

Provides a single public function, ``validate_schedule``, which verifies
that a generated schedule is conflict-free and complete with respect to
the underlying conflict graph.
"""

from __future__ import annotations


def validate_schedule(
    graph: dict[str, set[str]],
    schedule: dict[str, str],
) -> bool:
    """Validate that a schedule is clash-free and covers every subject.

    A schedule is considered valid when **both** of the following
    conditions hold:

    1. **Completeness** – every vertex (subject) in ``graph`` appears
       as a key in ``schedule``.
    2. **Clash-freedom** – for every edge ``(u, v)`` in ``graph``, the
       assigned slot of ``u`` differs from the assigned slot of ``v``.

    Parameters
    ----------
    graph:
        An adjacency list produced by :class:`core.graph_builder.GraphBuilder`.
        Keys are ``subject_id`` strings; values are sets of neighbouring
        ``subject_id`` strings.
    schedule:
        A mapping from ``subject_id`` to a slot string (e.g. ``"Slot 1"``).

    Returns
    -------
    bool
        ``True`` if the schedule is both complete and clash-free;
        ``False`` otherwise.

    Raises
    ------
    TypeError
        If ``graph`` or ``schedule`` is not a dictionary.

    Examples
    --------
    >>> graph = {"CS101": {"MA101"}, "MA101": {"CS101"}, "PH101": set()}
    >>> schedule = {"CS101": "Slot 1", "MA101": "Slot 2", "PH101": "Slot 1"}
    >>> validate_schedule(graph, schedule)
    True

    >>> bad = {"CS101": "Slot 1", "MA101": "Slot 1", "PH101": "Slot 2"}
    >>> validate_schedule(graph, bad)
    False
    """
    if not isinstance(graph, dict):
        raise TypeError("'graph' must be a dictionary (adjacency list).")
    if not isinstance(schedule, dict):
        raise TypeError("'schedule' must be a dictionary mapping subject IDs to slots.")

    # ── 1. Completeness check ────────────────────────────────────────────
    for subject_id in graph:
        if subject_id not in schedule:
            # At least one subject has not been assigned a slot.
            return False

    # ── 2. Clash-freedom check ───────────────────────────────────────────
    for subject_id, neighbours in graph.items():
        assigned_slot: str = schedule[subject_id]

        for neighbour_id in neighbours:
            # Guard against a neighbour that somehow slipped through without
            # a slot assignment (shouldn't happen after the completeness check
            # above, but we stay defensive).
            if neighbour_id not in schedule:
                return False

            if schedule[neighbour_id] == assigned_slot:
                # Two conflicting subjects share the same slot – invalid.
                return False

    return True