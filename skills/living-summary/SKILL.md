---
name: living-summary
description: Generate and persist a structured living summary for Salesforce cases. Use when asked to take an SFDC CaseNumber, pull EmailMessage conversation history with sf CLI, produce a concise technical summary with Problem/Cause/Validation/Solution sections, and update Case fields Problem__c, Cause__c, Validation__c, Solution__c, and Solution_Instructions__c.
---

# Living Summary

## Overview
Use this skill to build a technical "living summary" for a Salesforce case from email history.
Keep execution medium freedom: use the bundled script for deterministic data collection, then adapt synthesis quality and detail to the case context.

## Prerequisites
- Authenticate `sf` CLI to the target Salesforce org.
- Ensure read access to `Case` and `EmailMessage`.
- Ensure edit access to case custom fields `Problem__c`, `Cause__c`, `Validation__c`, `Solution__c`, and `Solution_Instructions__c`.

## Workflow
1. Pull the email history for the case number.

```bash
python3 scripts/fetch_case_email_history.py \
  --case-number 02622597 \
  --target-org my-org-alias
```

- Output directory defaults to `./downloads/case-<case-number>/`.
- Script writes:
- `email_history.json` (structured payload for traceability)
- `email_history.txt` (chronological transcript for summarization)

2. Review `email_history.txt` and confirm the thread has usable technical context.
- If some messages or bodies are missing, continue and report gaps as `Information not available.` in the final summary.

3. Run the mandatory summary prompt against the transcript content.
- Replace `{{EMAIL_HISTORY}}` with the full transcript.
- Return only the structured summary.
- Save the output to a local file, for example `living_summary.txt`.

```text
Task: Analyze the provided support ticket email conversation and generate a structured, concise technical summary in the specified format.

Output Format (mandatory)

Problem: Provide a clear, descriptive summary of the reported issue or query. Include all error messages, affected components, and observed behavior. Ensure this section is understandable without reading the original conversation.

Cause: Describe the identified or suspected cause of the issue. Mark uncertain causes as “Suspected.” If multiple hypotheses were discussed, list all and strike through the ones ruled out.

Validation Steps: List the actions taken to investigate, confirm, or reproduce the issue and validate potential causes. Group actions by date, omitting the year, and list in reverse chronological order

Additional Rule: If the customer performed steps that were explicitly stated (in the email conversation) as not relevant to this issue, those steps must be excluded from the summary. All other steps may be included, and if an engineer later determines them unnecessary, they can be manually removed.

Solution / Possible Solution: Use “Solution” if the issue has been confirmed resolved. Use “Possible Solution” if pending verification or further testing. Specify who implemented or verified it (e.g., Support Engineer, Customer). Explain the technical reasoning behind why the approach resolves or may resolve the issue.

Solution Instructions: Provide the detailed step-by-step instructions given or executed to apply the resolution. Include any relevant commands, configurations, or settings mentioned. If none were provided, clearly state: “No explicit instructions in the conversation.”

Style & Content Rules Remove all personal identifiers (names, emails, phone numbers, organizations).

Preserve all technical content: logic, terminology, configuration details, and error codes.

Improve grammar, readability, and structure — do not alter technical meaning.

Avoid personal pronouns. Use impersonal, directive phrasing (e.g., “Ensure to verify,” “Confirm whether…”).

Maintain neutral, audit-ready, factual tone.

If any section lacks information, explicitly note: “Information not available.”

Do not oversummarize or remove essential technical context.

Final Instruction: Generate the structured summary strictly following the format and rules above.

Conversation:
{{EMAIL_HISTORY}}
```

4. Update the Salesforce case living-summary fields from the structured summary.

```bash
python3 scripts/update_case_living_summary.py \
  --case-number 02622597 \
  --summary-file /absolute/path/living_summary.txt \
  --target-org my-org-alias
```

- Field mapping:
- `Problem` -> `Problem__c`
- `Cause` -> `Cause__c`
- `Validation Steps` -> `Validation__c`
- `Solution / Possible Solution` -> `Solution__c`
- `Solution Instructions` -> `Solution_Instructions__c`
- If a section is absent, script writes `Information not available.` for that field.
- Use `--dry-run` first to preview mapped values before updating Salesforce.

## Output Checklist
- Use section headers exactly:
- `Problem`
- `Cause`
- `Validation Steps`
- `Solution / Possible Solution`
- `Solution Instructions`
- Remove personal identifiers while keeping technical details intact.
- Use neutral, audit-ready wording.
- If evidence is absent for a section, output `Information not available.`
- Push the final structured summary into Case fields via `scripts/update_case_living_summary.py`.
