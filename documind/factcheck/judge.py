import logging
from typing import Any, Dict, List, Optional
from .llm import query_llm_json

logger = logging.getLogger(__name__)

ALLOWED_VERDICTS = {"Supported", "Contradicted", "Unverifiable"}

JUDGE_PROMPT_TEMPLATE = """You are an objective Fact-Checking Judge.
Your task is to determine whether the CLAIM below is Supported, Contradicted, or Unverifiable based SOLELY on the numbered evidence snippets provided below.

HARD INSTRUCTIONS:
- You must judge ONLY using the facts stated in the numbered EVIDENCE SNIPPETS below.
- Do NOT use your own background memory, assumptions, or external knowledge.
- If the snippets do not contain sufficient direct evidence to prove or disprove the claim, the verdict MUST be "Unverifiable".
- "Supported": The evidence directly confirms the claim.
- "Contradicted": The evidence directly refutes or contradicts the claim.
- "Unverifiable": The evidence is insufficient, ambiguous, or does not address the claim.

Output a strict JSON object with exactly three keys:
1. "verdict": exactly one of ["Supported", "Contradicted", "Unverifiable"]
2. "reason": a single objective sentence explaining the verdict based on the evidence.
3. "evidence_ids": an array of integers representing the specific snippet IDs [1, 2, ...] you relied upon. (Empty [] if Unverifiable).

CLAIM TO VERIFY:
"{claim}"

NUMBERED EVIDENCE SNIPPETS:
{evidence_text}
"""

class ClaimJudgeService:
    """Judges factual claims strictly against retrieved source snippets using LLM verification."""

    def judge_claim(
        self,
        claim_text: str,
        evidence_items: List[Dict[str, Any]],
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Judges a claim against retrieved evidence snippets.
        Guarantees strict verdict validation, evidence_id bounds, and no-evidence fallback.
        """
        # Hard Rule: If retrieval returned nothing, return Unverifiable WITHOUT calling the LLM
        if not evidence_items:
            return {
                "verdict": "Unverifiable",
                "reason": "No relevant factual evidence found in free search sources.",
                "evidence_ids": [],
                "sources": [],
            }

        # Build numbered evidence text
        evidence_lines = []
        valid_ids = set()
        sources_by_id = {}

        for item in evidence_items:
            eid = item["evidence_id"]
            valid_ids.add(eid)
            sources_by_id[eid] = item
            evidence_lines.append(f"[{eid}] Source: {item['title']}\nSnippet: {item['snippet']}")

        evidence_text = "\n\n".join(evidence_lines)
        prompt = JUDGE_PROMPT_TEMPLATE.format(claim=claim_text, evidence_text=evidence_text)

        # Attempt up to 2 times (initial + 1 retry if validation fails)
        for attempt in range(2):
            try:
                res = query_llm_json(prompt, config=config)
                if not isinstance(res, dict):
                    continue

                verdict = str(res.get("verdict", "")).strip().title()
                reason = str(res.get("reason", "")).strip()
                raw_ids = res.get("evidence_ids", [])

                # Validate verdict is one of the 3 allowed values
                if verdict not in ALLOWED_VERDICTS:
                    logger.warning(f"Invalid verdict '{verdict}' on attempt {attempt + 1}")
                    continue

                # Validate evidence_ids are valid integers that exist in the retrieved list
                clean_ids = []
                if isinstance(raw_ids, list):
                    for i in raw_ids:
                        try:
                            val_i = int(i)
                            if val_i in valid_ids:
                                clean_ids.append(val_i)
                        except (ValueError, TypeError):
                            continue

                # Collect only the sources corresponding to the validated evidence_ids
                attached_sources = [sources_by_id[eid] for eid in clean_ids if eid in sources_by_id]
                # If unverifiable but snippets existed, attach the first couple of queried sources for context
                if verdict == "Unverifiable" and not attached_sources:
                    attached_sources = evidence_items[:2]

                return {
                    "verdict": verdict,
                    "reason": reason or ("Evidence verifies claim." if verdict == "Supported" else "Evidence contradicts claim." if verdict == "Contradicted" else "Insufficient evidence to verify."),
                    "evidence_ids": clean_ids,
                    "sources": attached_sources,
                }

            except Exception as e:
                logger.warning(f"Judging attempt {attempt + 1} error: {e}")

        # If both attempts failed, return safe fallback
        return {
            "verdict": "Unverifiable",
            "reason": "Unable to definitively verify claim with available evidence sources.",
            "evidence_ids": [],
            "sources": evidence_items[:2] if evidence_items else [],
        }
