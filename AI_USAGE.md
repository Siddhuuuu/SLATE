# AI_USAGE.md

AI tools were used as development assistance throughout Project SLATE. The
implementation was reviewed, tested, and modified manually rather than being
accepted blindly.

## Development assistance

AI was used to help with:

- Initial project structure and implementation planning
- FastAPI backend and React/tldraw frontend scaffolding
- Experiment and trace-analysis scripts
- Test generation and debugging
- Documentation and README drafting
- Reviewing implementation choices and identifying edge cases

## What was verified manually

The implementation was repeatedly tested against the actual project rather
than relying only on generated code.

Manual verification included:

- Running the complete Python test suite
- Running real frontend builds
- Testing the application with Gemini and Ollama
- Inspecting real model responses and traces
- Debugging streaming and `<think>`-tag leakage
- Verifying the routing heuristic with realistic inputs
- Verifying tldraw APIs against the installed package
- Running the real experiment harness with benchmark crops
- Running the trace-analysis pipeline and generating the final report
- Checking Git status, tracked files, ignored secrets, and the final pushed
  commit

The final test suite completed with:

**88 passed, 0 failed.**

## AI-assisted debugging

Several issues were discovered through real execution rather than static
review, including model-response formatting issues, routing-threshold
problems, token accounting differences, model availability changes, and
provider latency differences.

These were investigated and fixed through code changes followed by tests or
real execution.

## Human decisions

The following decisions remained under my control:

- Final project scope and architecture
- Choice of tldraw for the canvas
- Choice of model-routing as the shipped feature
- Routing thresholds and provider behavior
- Gemini/Ollama experiment design
- Keep-alive and maximum-token experiments
- Latency budget and KPI definitions
- Which experimental results to report
- Final trade-off and recommendation
- Security decisions, including keeping API keys out of Git

AI assistance was therefore used as a development and debugging tool, while
the final implementation, testing, experimental decisions, and submitted
results were reviewed and validated by me.
