# Puffin Ship — Working Rules

1. No AI attribution, anywhere, ever. Claude/AI must never appear as a git author, co-author, committer, or contributor, and never in commit messages, PR descriptions, code comments, documentation, or product output. Commits use Chandler's identity only. Never add "Co-Authored-By" or "Generated with…" trailers.
2. No internal or server-side implementation details in user-facing docs or UI. Describe what users do, not how the server works — no cache paths, internal file layouts, or infrastructure details.
3. Quality bar: every change ships with rigorous automated tests and a self-audit for edge cases and gaps before it's called done. Design for how real users actually behave and misuse features, not the happy path.
4. Model usage: use the strongest model for judgment-heavy work; downgrade to a cheaper model only when it can clearly still do the task well, to conserve usage credits.
5. Docs serve three audiences equally: people using the web UI/UX, developers, and YAML authors.
