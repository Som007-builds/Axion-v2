You extract claims from several biomedical research papers in one response.

A claim is a falsifiable, source-linked assertion stated by the paper itself.
Do not extract background statements that merely summarise other work without
asserting a finding, and do not extract the paper's aims or methods as claims.
Prefer specific, testable assertions (association, effect, prevalence,
diagnostic performance, mechanism, or a stated limitation).

Rules:
1. Copy the evidence span **verbatim** from the supplied text of *that* paper.
   Do not paraphrase, merge sentences, fix punctuation, or insert ellipses.
2. Every claim must name the `paper_id` of the paper it came from, exactly as
   given in the `=== PAPER <paper_id> ===` delimiter.
3. `section` must be the section label supplied in that paper's document.
4. Keep each claim to one assertion. Split compound sentences when needed.
5. Return at most {max_claims} claims **per paper**, ordered by importance.
6. Return JSON only, with this exact shape:

{{
  "claims": [
    {{
      "paper_id": "PMC1234567",
      "claim_text": "one falsifiable assertion",
      "section": "Results",
      "evidence_span": "verbatim text copied from that paper",
      "claim_type": "association | effect | prevalence | diagnostic | mechanism | limitation | other"
    }}
  ]
}}

If a paper contains no extractable claims, emit no claims for it. Never
invent a paper_id and never reuse another paper's evidence span.

Documents:

{documents}
