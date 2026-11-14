You extract claims from one biomedical research paper.

A claim is a falsifiable, source-linked assertion stated by the paper itself.
Do not extract background statements that merely summarise other work without
asserting a finding, and do not extract the paper's aims or methods as claims.
Prefer specific, testable assertions (association, effect, prevalence,
diagnostic performance, mechanism, or a stated limitation).

Rules:
1. Copy the evidence span **verbatim** from the supplied text. Do not paraphrase,
   merge sentences, fix punctuation, or insert ellipses.
2. `section` must be the section label supplied in the document heading.
3. Keep each claim to one assertion. Split compound sentences when needed.
4. Return at most {max_claims} claims, ordered by importance.
5. Return JSON only, with this exact shape:

{{
  "claims": [
    {{
      "claim_text": "one falsifiable assertion",
      "section": "Results",
      "evidence_span": "verbatim text copied from that section",
      "claim_type": "association | effect | prevalence | diagnostic | mechanism | limitation | other",
      "population": "optional: study population or null",
      "intervention": "optional: exposure/intervention or null",
      "outcome": "optional: measured outcome or null",
      "direction": "optional: increase | decrease | no_difference | mixed | null"
    }}
  ]
}}

If the paper contains no extractable claims, return {{"claims": []}}.

Document:
{document}
