# Repository policy

- Never commit provider credentials, user transcripts, or unredacted model payloads containing secrets.
- Keep upstream source and gold patches out of agent-visible task contexts.
- Use exact immutable commit IDs and image digests.
- Treat deterministic verifier output as authoritative for behavior.
- Treat proctor review as a separately reported judgment of taste and mergibility.
- Do not execute the candidate-model matrix until task validation is complete and explicitly approved.
- Prefer direct, proportional edits and verify with focused tests.
