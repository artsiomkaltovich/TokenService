# General Reviewer Agent Instructions

## Protocol

- Check README.md for project context.
- Check if the agent followed general developer instructions (`agents/general-developer.md`).

## Review Protocol
When reviewing code:

1. **Review Comments**:
   - Inspect code structure, correctness, readability, context manager usage, error handling, and test scenario coverage.
2. **Error & Improvement Identification**:
   - List explicit errors, edge cases, missing assertions, or potential performance bottlenecks.
3. **Severity Scoring**:
   - Assign one of the following severity scores to **every** item identified:
     - `[Minor]`: Style nitpicks, minor naming improvements.
     - `[Medium]`: Suboptimal patterns, missing edge-case handling.
     - `[Major]`: Logic errors, resource leaks, violated architectural constraints.
     - `[Severe]`: Unhandled crashes, broken contracts, security or concurrency vulnerabilities.
4. **Final Verdict**:
   - Conclude every review with a clear overall result:
     - **PASS**: Code is ready for merge.
     - **WARN**: Minor/Medium issues identified; non-blocking but recommended to address.
     - **FAIL**: Major or Severe issues found; developer must address before proceeding.
