"""
solver.py
---------
Core scheduling engine for the ClashZero exam timetable generator.

Models exam scheduling as a **graph colouring problem** and solves it
with a **backtracking** algorithm, iterating upward from 1 colour until
a valid, clash-free colouring is found.  The minimum number of colours
used equals the minimum number of distinct time slots required.
"""

from __future__ import annotations

from core.validators import validate_schedule


class Solver:
    """Generate a clash-free exam schedule using graph colouring.

    The conflict graph is provided by :class:`core.graph_builder.GraphBuilder`.
    Internally, integer "colours" (1, 2, 3, …) represent time slots.
    The public API surfaces these as human-readable strings ("Slot 1",
    "Slot 2", …).

    Parameters
    ----------
    graph:
        Adjacency list where every key is a ``subject_id`` and its value
        is the set of ``subject_id`` values it conflicts with.

    Raises
    ------
    TypeError
        If ``graph`` is not a dictionary.

    Usage::

        from core.graph_builder import GraphBuilder
        from core.solver import Solver

        graph = GraphBuilder.build_graph(subjects)
        solver = Solver(graph)
        result = solver.generate_schedule()
    """

    def __init__(self, graph: dict[str, set[str]]) -> None:
        if not isinstance(graph, dict):
            raise TypeError("'graph' must be a dictionary (adjacency list).")

        self._graph: dict[str, set[str]] = graph
        # Deterministic vertex ordering ensures reproducible results.
        self._vertices: list[str] = sorted(graph.keys())

    # ──────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────

    def is_safe(
        self,
        vertex: str,
        color: int,
        color_assignment: dict[str, int],
    ) -> bool:
        """Check whether assigning ``color`` to ``vertex`` causes a conflict.

        A colour assignment is safe when none of ``vertex``'s already-
        coloured neighbours share the same colour.

        Parameters
        ----------
        vertex:
            The ``subject_id`` being considered for assignment.
        color:
            The integer colour (slot index) to test.
        color_assignment:
            A partial mapping of ``subject_id`` → integer colour built
            up incrementally by the backtracking algorithm.

        Returns
        -------
        bool
            ``True`` if assigning ``color`` to ``vertex`` is conflict-
            free given the current partial assignment.
        """
        for neighbour in self._graph.get(vertex, set()):
            if color_assignment.get(neighbour) == color:
                return False
        return True

    def graph_coloring(
        self,
        vertices: list[str],
        max_colors: int,
        index: int,
        color_assignment: dict[str, int],
    ) -> bool:
        """Attempt to colour all vertices using at most ``max_colors`` colours.

        Uses recursive backtracking: assign a legal colour to the vertex
        at position ``index``, then recurse to the next vertex.  If no
        legal colour exists, backtrack and try the next option.

        Parameters
        ----------
        vertices:
            Ordered list of all ``subject_id`` strings to colour.
        max_colors:
            The maximum number of colours (slots) available in this
            attempt.
        index:
            The position in ``vertices`` currently being processed.
            Starts at 0 and increments with each recursive call.
        color_assignment:
            A dictionary updated **in place** to record the colour
            assigned to each vertex.  Pass an empty dict from the
            caller.

        Returns
        -------
        bool
            ``True`` if a valid complete colouring was found;
            ``False`` if the current partial assignment cannot be
            extended without violating constraints.
        """
        # Base case: every vertex has been successfully coloured.
        if index == len(vertices):
            return True

        current_vertex: str = vertices[index]

        # Try each colour in turn.
        for color in range(1, max_colors + 1):
            if self.is_safe(current_vertex, color, color_assignment):
                # Tentatively assign this colour.
                color_assignment[current_vertex] = color

                # Recurse to the next vertex.
                if self.graph_coloring(vertices, max_colors, index + 1, color_assignment):
                    return True

                # Backtrack: remove the tentative assignment.
                del color_assignment[current_vertex]

        # No valid colour found for this vertex with the current partial assignment.
        return False

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    def find_minimum_colors(self) -> tuple[dict[str, int], int]:
        """Find the minimum number of colours needed to colour the graph.

        Iterates from 1 colour upward, invoking :meth:`graph_coloring`
        at each step, until a valid colouring is discovered.

        Returns
        -------
        tuple[dict[str, int], int]
            A 2-tuple of:

            * ``color_assignment`` – mapping of ``subject_id`` → integer
              colour (1-indexed).
            * ``num_colors`` – the minimum number of colours required.

        Notes
        -----
        An empty graph returns an empty assignment and 0 colours.

        The theoretical upper bound for the number of colours needed is
        the number of vertices, so the search terminates in all cases.
        """
        if not self._vertices:
            return {}, 0

        num_vertices: int = len(self._vertices)

        for num_colors in range(1, num_vertices + 1):
            color_assignment: dict[str, int] = {}

            if self.graph_coloring(self._vertices, num_colors, 0, color_assignment):
                return color_assignment, num_colors

        # This point is unreachable: n vertices always need at most n colours.
        raise RuntimeError(  # pragma: no cover
            "Unable to colour the graph – this should never happen."
        )

    def generate_schedule(self) -> dict:
        """Generate and return a validated, clash-free exam schedule.

        Converts the integer colour assignment produced by
        :meth:`find_minimum_colors` into human-readable slot strings and
        validates the result with :func:`core.validators.validate_schedule`
        before returning.

        Returns
        -------
        dict
            A dictionary with the following structure::

                {
                    "schedule": {
                        "CS101": "Slot 1",
                        "CS102": "Slot 2",
                        "MA101": "Slot 1"
                    },
                    "num_slots_used": 2,
                    "is_valid": True
                }

        Raises
        ------
        RuntimeError
            If the generated schedule fails validation (indicates a bug
            in the colouring logic).
        """
        color_assignment, num_colors = self.find_minimum_colors()

        # Convert integer colours → human-readable slot labels.
        schedule: dict[str, str] = {
            subject_id: f"Slot {color}"
            for subject_id, color in color_assignment.items()
        }

        # Validate before returning; this is a safety net.
        is_valid: bool = validate_schedule(self._graph, schedule)

        if not is_valid and color_assignment:
            # If we produced an assignment but validation fails, something
            # went wrong in the algorithm.
            raise RuntimeError(
                "Generated schedule failed validation.  "
                "This indicates a bug in the colouring algorithm."
            )

        return {
            "schedule": schedule,
            "num_slots_used": num_colors,
            "is_valid": is_valid,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Demonstration / smoke-test
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from core.graph_builder import GraphBuilder

    sample_subjects: list[dict] = [
        {
            "subject_id": "CS101",
            "subject_name": "Data Structures",
            "students": ["S001", "S002", "S003"],
            "preferred_slot": "Morning",
            "duration": 120,
        },
        {
            "subject_id": "CS102",
            "subject_name": "Algorithms",
            "students": ["S002", "S004"],
            "preferred_slot": "Afternoon",
            "duration": 90,
        },
        {
            "subject_id": "MA101",
            "subject_name": "Calculus",
            "students": ["S001", "S005"],
            "preferred_slot": "Morning",
            "duration": 120,
        },
        {
            "subject_id": "PH101",
            "subject_name": "Physics",
            "students": ["S006", "S007"],
            "preferred_slot": "Morning",
            "duration": 90,
        },
        {
            "subject_id": "EN101",
            "subject_name": "English",
            "students": ["S003", "S006"],
            "preferred_slot": "Afternoon",
            "duration": 60,
        },
    ]

    print("=" * 55)
    print("  ClashZero – Exam Timetable Generator (demo)")
    print("=" * 55)

    # Step 1 – Build the conflict graph.
    graph: dict[str, set[str]] = GraphBuilder.build_graph(sample_subjects)
    print("\n[1] Conflict graph (adjacency list):")
    for subject_id, neighbours in sorted(graph.items()):
        print(f"    {subject_id}: {sorted(neighbours)}")

    # Step 2 – Solve and generate the schedule.
    solver = Solver(graph)
    result: dict = solver.generate_schedule()

    # Step 3 – Display the final output.
    print("\n[2] Generated schedule:")
    for subject_id, slot in sorted(result["schedule"].items()):
        print(f"    {subject_id}: {slot}")

    print(f"\n[3] Minimum slots used : {result['num_slots_used']}")
    print(f"    Schedule is valid   : {result['is_valid']}")
    print("=" * 55)