---
name: sfdc-draft-email-response
description: Draft Salesforce case response emails directly with sf CLI and no bundled scripts. Use when asked to look up an SFDC case by CaseNumber, base a draft on the latest inbound and outbound case emails, include the current user's signature with leading Hello removed, set private draft behavior, and preserve reply/thread linkage plus contact relations.
---

# SFDC Draft Email Response

## Overview
Use direct `sf` CLI commands and adapt to the case context.
Keep this skill high freedom: use the same intent and validation checks, but choose the exact queries/field set based on what the case data requires.

## Objectives
- Resolve the case from `CaseNumber`.
- Read the latest inbound and latest outbound `EmailMessage` for the case.
- Draft a response that reflects current thread context.
- Include current user's Salesforce signature with the leading `Hello` line removed.
- Ensure the resulting draft is private (`IsPrivateDraft=true`).
- Preserve linkage and recipients so the draft can be sent as a real reply.

## Flexible Workflow
1. Gather context.
- Case: `Id`, `Subject`, `ContactId`, `Contact.Email`.
- Latest inbound email: sender/recipients, subject, body, thread info.
- Latest outbound email: sender/recipients, subject, thread info, status.
- Current user signature from `User.Signature`.

2. Compose draft body.
- Build a concise response line using latest inbound/outbound context.
- Append signature content after removing the leading `Hello` line.
- Keep text and HTML versions aligned.

3. Create or update draft.
- Prefer an `EmailMessage` draft (`Status='5'`) with `IsPrivateDraft=true`.
- Treat `IsPrivateDraft` as create-only. Do not attempt to update it on an existing draft.
- If the latest draft already has `IsPrivateDraft=true`, update that draft.
- If the latest draft has `IsPrivateDraft=false`, create a replacement draft with `IsPrivateDraft=true` and copy recipients/body/thread linkage.
- Ensure core fields: `ParentId`, `Incoming=false`, `Status='5'`, `IsPrivateDraft=true`, `Subject`, `FromAddress`, `ToAddress`, optional `CcAddress`/`BccAddress`, `TextBody`.

4. Apply reply/thread linkage.
- Set `ReplyToEmailMessageId` using latest outbound when available, else inbound.
- Set `ThreadIdentifier` using latest outbound when available, else inbound.
- Set `ValidatedFromAddress` and `MessageDate` as needed for sender consistency.

5. Apply contact relations.
- Resolve `To`/`Cc` emails to `Contact` records.
- Set `EmailMessageRelation.RelationId` for `RelationType='ToAddress'` and `RelationType='CcAddress'`.
- Prefer the case contact relation when email matches.

6. Verify output.
- Draft remains `Status='5'`.
- `IsPrivateDraft=true`.
- Correct case parent.
- Reply/thread linkage present.
- Expected recipients and contact relations present.

## Notes
- Use `sf` CLI with `--json` for deterministic parsing.
- Do not rely on bundled scripts in this skill.
- If Lightning UI does not show API-created drafts consistently, prefer updating an existing UI-seeded draft for the same case.

## Command Reference (No `--help` Needed)
Use these command patterns directly.

- Resolve case by number:
`sf data query --query "SELECT Id, CaseNumber, Subject, ContactId, Contact.Email FROM Case WHERE CaseNumber='<CaseNumber>' LIMIT 1" --json`
- Get current user id:
`sf org display user --json`
- Latest inbound email:
`sf data query --query "SELECT Id, ParentId, Incoming, Status, Subject, FromAddress, FromName, ToAddress, CcAddress, BccAddress, TextBody, HtmlBody, MessageDate, CreatedDate, ThreadIdentifier, ReplyToEmailMessageId, ValidatedFromAddress FROM EmailMessage WHERE ParentId='<CaseId>' AND Incoming=true ORDER BY MessageDate DESC, CreatedDate DESC LIMIT 1" --json`
- Latest outbound email:
`sf data query --query "SELECT Id, ParentId, Incoming, Status, Subject, FromAddress, FromName, ToAddress, CcAddress, BccAddress, TextBody, HtmlBody, MessageDate, CreatedDate, ThreadIdentifier, ReplyToEmailMessageId, ValidatedFromAddress FROM EmailMessage WHERE ParentId='<CaseId>' AND Incoming=false ORDER BY MessageDate DESC, CreatedDate DESC LIMIT 1" --json`
- Latest draft for the case:
`sf data query --query "SELECT Id, ParentId, Incoming, Status, IsPrivateDraft, Subject, FromAddress, ToAddress, CcAddress, BccAddress, TextBody, HtmlBody, MessageDate, CreatedDate, ThreadIdentifier, ReplyToEmailMessageId, ValidatedFromAddress FROM EmailMessage WHERE ParentId='<CaseId>' AND Incoming=false AND Status='5' ORDER BY CreatedDate DESC LIMIT 1" --json`
- Current user signature:
`sf data query --query "SELECT Id, Name, Email, Signature FROM User WHERE Id='<UserId>' LIMIT 1" --json`
- Optional field mutability check:
`sf api request rest '/services/data/v66.0/sobjects/EmailMessage/describe' --target-org <OrgAlias> | jq '.fields[] | select(.name=="IsPrivateDraft") | {name, createable, updateable}'`
- Create private draft (recommended when draft is not private):
`sf api request rest '/services/data/v66.0/sobjects/EmailMessage' --method POST --body @/tmp/emailmessage_private_create.json --target-org <OrgAlias>`
- Update existing draft content/linkage (only if already private):
`sf api request rest '/services/data/v66.0/sobjects/EmailMessage/<DraftId>' --method PATCH --body @/tmp/emailmessage_patch.json --target-org <OrgAlias>`
- Query draft relations:
`sf data query --query "SELECT Id, EmailMessageId, RelationType, RelationAddress, RelationId FROM EmailMessageRelation WHERE EmailMessageId='<DraftId>' ORDER BY RelationType, RelationAddress" --json`
- Update relation contact mapping:
`sf data update record --sobject EmailMessageRelation --record-id <RelationRowId> --values "RelationId=<ContactId>" --json`
