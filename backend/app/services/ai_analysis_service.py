"""AI analysis service using Claude API for market research insights."""
from __future__ import annotations
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def _avg(values: List[Optional[float]]) -> Optional[float]:
    present = [float(v) for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _format_metric(value: Optional[float], digits: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}"


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
        avg_price = _avg([comp.get("price") for comp in competitor_data])
        avg_bsr = _avg([comp.get("bsr") for comp in competitor_data])
        avg_reviews = _avg([comp.get("review_count") for comp in competitor_data])
        avg_rating = _avg([comp.get("rating") for comp in competitor_data])

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
        market_baseline = (
            "Market baseline:\n"
            f"- Competitors analyzed: {len(competitor_data)}\n"
            f"- Avg price: {_format_metric(avg_price)}\n"
            f"- Avg BSR: {_format_metric(avg_bsr, 0)}\n"
            f"- Avg review count: {_format_metric(avg_reviews, 0)}\n"
            f"- Avg rating: {_format_metric(avg_rating, 1)}"
        )

        prompt = f"""You are an expert Amazon marketplace analyst. Analyze the following product compared to its competitors and provide actionable insights.

{lang_instruction}

{category_text}
{market_baseline}

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
- Explain tradeoffs using the market baseline and the reference product, not generic ecommerce advice
- Focus recommendations on how to improve the reference product against similar products in this market
- If data is missing for some fields, note it but do not invent missing metrics
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


class ForecastInsightsAnalysisService:
    """Service for generating AI insights from forecast data."""

    def __init__(self, api_key: str):
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)

    def analyze(
        self,
        *,
        forecast_data: Dict[str, Any],
        language: str = "en",
    ) -> Dict[str, Any]:
        """Generate structured forecast insights."""
        lang_instruction = "Respond entirely in Italian." if language == "it" else "Respond entirely in English."
        prompt = f"""You are an expert ecommerce forecasting analyst. Review the forecast dataset below and produce executive insights for a business stakeholder.

{lang_instruction}

Forecast dataset:
{json.dumps(forecast_data, ensure_ascii=False, indent=2)}

Return a JSON object with exactly this structure:
{{
  "summary": "2-4 sentence executive summary",
  "key_trends": ["trend 1", "trend 2", "trend 3"],
  "risks": ["risk 1", "risk 2", "risk 3"],
  "opportunities": ["opportunity 1", "opportunity 2", "opportunity 3"],
  "recommendations": [
    {{
      "priority": "high|medium|low",
      "action": "clear recommended action",
      "rationale": "why this action follows from the forecast",
      "expected_impact": "expected business impact"
    }}
  ]
}}

Rules:
- Base all insights on the provided forecast metrics, prediction intervals, daily pattern, and recent history when available.
- Do not invent products, channels, campaigns, or causes not supported by the data.
- Recommendations must be concrete and operational, not generic business advice.
- Provide 3-5 recommendations ordered by importance.
- Return ONLY the JSON object, no markdown or commentary."""

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2200,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = message.content[0].text.strip()
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
                response_text = "\n".join(lines)

            analysis = json.loads(response_text)
            required_keys = {"summary", "key_trends", "risks", "opportunities", "recommendations"}
            missing = required_keys - analysis.keys()
            if missing:
                logger.warning("Forecast insights missing keys: %s", missing)
                for key in missing:
                    analysis[key] = "" if key == "summary" else []

            normalized_recs = []
            for rec in analysis.get("recommendations", []):
                normalized_recs.append(
                    {
                        "priority": rec.get("priority", "medium"),
                        "action": rec.get("action", ""),
                        "rationale": rec.get("rationale", ""),
                        "expected_impact": rec.get("expected_impact", ""),
                    }
                )
            analysis["recommendations"] = normalized_recs
            return analysis
        except json.JSONDecodeError as e:
            logger.error("Failed to parse forecast AI response as JSON: %s", e)
            raise ValueError(f"AI returned invalid JSON: {e}")
        except Exception:
            logger.exception("Forecast AI analysis failed")
            raise


class ProductTrendInsightsAnalysisService:
    """Service for generating structured product trend insights."""

    def __init__(self, api_key: str):
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)

    def analyze(
        self,
        *,
        trend_data: Dict[str, Any],
        language: str = "en",
    ) -> Dict[str, Any]:
        """Generate structured insights for product trends."""
        lang_instruction = "Respond entirely in Italian." if language == "it" else "Respond entirely in English."
        prompt = f"""You are an expert ecommerce analyst. Review the product trend dataset below and produce executive insights for a business stakeholder.

{lang_instruction}

Trend dataset:
{json.dumps(trend_data, ensure_ascii=False, indent=2)}

Return a JSON object with exactly this structure:
{{
  "summary": "2-4 sentence executive summary",
  "key_trends": ["trend 1", "trend 2", "trend 3"],
  "risks": ["risk 1", "risk 2", "risk 3"],
  "opportunities": ["opportunity 1", "opportunity 2", "opportunity 3"],
  "recommendations": [
    {{
      "priority": "high|medium|low",
      "action": "clear recommended action",
      "rationale": "why this action follows from the trend data",
      "expected_impact": "expected business impact"
    }}
  ]
}}

Rules:
- Base every insight only on the provided trend score, direction, strength, category concentration, BSR movement, and sales deltas.
- Do not invent causes, campaigns, pricing moves, stock issues, or competitor actions unless directly supported by the data.
- Recommendations must reference actual products or product groups from the dataset when relevant.
- Prioritize operationally useful actions.
- Provide 3-5 recommendations ordered by importance.
- Return ONLY the JSON object, no markdown or commentary."""

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2200,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = message.content[0].text.strip()
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
                response_text = "\n".join(lines)

            analysis = json.loads(response_text)
            required_keys = {"summary", "key_trends", "risks", "opportunities", "recommendations"}
            missing = required_keys - analysis.keys()
            if missing:
                logger.warning("Product trend insights missing keys: %s", missing)
                for key in missing:
                    analysis[key] = "" if key == "summary" else []

            normalized_recs = []
            for rec in analysis.get("recommendations", []):
                normalized_recs.append(
                    {
                        "priority": rec.get("priority", "medium"),
                        "action": rec.get("action", ""),
                        "rationale": rec.get("rationale", ""),
                        "expected_impact": rec.get("expected_impact", ""),
                    }
                )
            analysis["recommendations"] = normalized_recs
            return analysis
        except json.JSONDecodeError as e:
            logger.error("Failed to parse product trend AI response as JSON: %s", e)
            raise ValueError(f"AI returned invalid JSON: {e}")
        except Exception:
            logger.exception("Product trend AI analysis failed")
            raise
