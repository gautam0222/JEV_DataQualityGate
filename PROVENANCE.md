# Project provenance and boundaries

This is an educational data-engineering project. Its implementation is specific
to the decision flow in this repository: profile retail-order rows, isolate
deterministic integrity failures, and optionally use a Jev response as an
advisory signal. It is not a copied implementation of the linked learning
examples.

The project does rely on normal third-party building blocks:

- `pandas` for tabular parsing and quality calculations;
- `pytest` for tests;
- `openpyxl` to read the public Excel workbook; and
- `typesafe-sdk` for the optional live Jev call.

The sample fixture is schema-compatible teaching data. The optional full data
source is the UCI Online Retail dataset, credited in the README under CC BY
4.0. Keep that attribution if the dataset, or a derivative of it, is shared.

No automated checker can prove that prose or code is free of every possible
similarity, or establish how it was authored. Before submitting this project,
the owner should be able to explain the input checks, the 2% demonstration
threshold, the cancellation rule, and the difference between offline rules and
live Jev advice. Those are the project-specific design decisions worth
documenting and defending.
