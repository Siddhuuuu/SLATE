# ATTRIBUTION.md

## PenEcho

I did not study or directly reimplement PenEcho's source code or
architecture in detail during development.

Project SLATE was developed from the assignment requirements and an
independent project design. No specific PenEcho implementation, code, or
architecture was deliberately copied.

The following parts were developed independently from the assignment
requirements:

- The metrics and KPI layer (`backend/kpis.py`)
- The six-segment latency model
- The provider-routing feature (`backend/router.py`)
- The experiment harness and trace-analysis pipeline
- The React/tldraw canvas implementation

## Other References

- **tldraw** — official package documentation and installed source were
  consulted to verify the APIs used by the canvas implementation.
- **W3C Pointer Events** — referenced for browser pointer-event behavior.

These are normal technical references and are not copied implementations.

## AI Assistance

AI tools were used as development assistance for planning, implementation,
debugging, testing, and documentation. The final implementation and
experimental results were reviewed and validated through local tests,
frontend builds, real provider requests, and the final experiment harness.
