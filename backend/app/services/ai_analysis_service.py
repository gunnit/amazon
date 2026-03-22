"""AI analysis service using Claude API for market research insights."""
from __future__ import annotations
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class AIAnalysisService:
    """Service for generating AI-powered competitive analysis."""

    def __init__(self, api_key: str):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)

    def analyze(
        self,
        product_data: Dict[str, Any],
        competitor_data: List[Dict[str, Any]],
        category: Optional[str] = None,
        language: str = "en",
    ) -> Dict[str, Any]:
        """Generate AI analysis comparing product against competitors.

        Returns dict with: strengths, weaknesses, recommendations, overall_score, summary
        """
        lang_instruction = "Respond entirely in Italian." if language == "it" else "Respond entirely in English."

        # Build comparison table
        competitors_text = ""
        for i, comp in enumerate(competitor_data, 1):
            competitors_text += (
                f"\nCompetitor {i}: ASIN={comp.get('asin', 'N/A')}, "
                f"Title={comp.get('title', 'N/A')}, "
                f"Brand={comp.get('brand', 'N/A')}, "
                f"Price={comp.get('price', 'N/A')}, "
                f"BSR={comp.get('bsr', 'N/A')}, "
                f"Reviews={comp.get('review_count', 'N/A')}, "
                f"Rating={comp.get('rating', 'N/A')}"
            )

        category_text = f"Category: {category}" if category else "Category: Unknown"

        prompt = f"""You are an expert Amazon marketplace analyst. Analyze the following product compared to its competitors and provide actionable insights.

{lang_instruction}

{category_text}

Source Product:
- ASIN: {product_data.get('asin', 'N/A')}
- Title: {product_data.get('title', 'N/A')}
- Brand: {product_data.get('brand', 'N/A')}
- Price: {product_data.get('price', 'N/A')}
- BSR (Best Sellers Rank): {product_data.get('bsr', 'N/A')}
- Review Count: {product_data.get('review_count', 'N/A')}
- Rating: {product_data.get('rating', 'N/A')}

Competitors:{competitors_text}

Provide your analysis as a JSON object with exactly this structure:
{{
  "strengths": ["strength 1", "strength 2", ...],
  "weaknesses": ["weakness 1", "weakness 2", ...],
  "recommendations": [
    {{
      "area": "area name",
      "priority": "high|medium|low",
      "action": "specific action to take",
      "expected_impact": "expected result"
    }}
  ],
  "overall_score": <integer 1-100>,
  "summary": "A concise narrative summary of the competitive position"
}}

Rules:
- Provide 3-5 strengths and weaknesses each
- Provide 3-6 recommendations ordered by priority
- overall_score: 80+ means strong position, 50-79 average, below 50 needs improvement
- Base analysis on real metrics: price competitiveness, BSR ranking, review quantity and quality
- If data is missing for some fields, note it but still provide analysis based on available data
- Return ONLY the JSON object, no other text"""

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = message.content[0].text.strip()
            # Strip markdown code fences if present
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                # Remove first and last lines (code fences)
                lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
                response_text = "\n".join(lines)

            analysis = json.loads(response_text)

            # Validate required fields
            required_keys = {"strengths", "weaknesses", "recommendations", "overall_score", "summary"}
            if not required_keys.issubset(analysis.keys()):
                missing = required_keys - analysis.keys()
                logger.warning(f"AI analysis missing keys: {missing}")
                for key in missing:
                    if key == "overall_score":
                        analysis[key] = 50
                    elif key == "summary":
                        analysis[key] = ""
                    else:
                        analysis[key] = []

            # Clamp score
            analysis["overall_score"] = max(1, min(100, int(analysis["overall_score"])))

            return analysis

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            raise ValueError(f"AI returned invalid JSON: {e}")
        except Exception as e:
            logger.exception("AI analysis failed")
            raise
