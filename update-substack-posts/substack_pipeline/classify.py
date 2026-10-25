"""One Claude call per post: relevance, summary, tags, suggested tags, stance."""

import json
import logging

import anthropic

from config import settings

log = logging.getLogger(__name__)

RELEVANCE_VALUES = ["relevant", "unsure", "not_relevant"]
NEWS_TAG = "news"


def _score_rubric():
    lo, hi = settings.RELEVANCE_SCORE_MIN, settings.RELEVANCE_SCORE_MAX
    return (f"relevance_score: {lo} to {hi}, how central antizionism is to the post and how useful it would be "
            f"as a resource on antizionism. {hi} = antizionism is the core subject, examined in depth; "
            f"{lo} = antizionism is barely present.")


def _score_schema():
    return {"type": "integer", "enum": list(range(settings.RELEVANCE_SCORE_MIN, settings.RELEVANCE_SCORE_MAX + 1))}


class ClassifyError(Exception):
    pass


class ClassifyAuthError(Exception):
    """Missing or rejected credentials; fails every post the same way, so the run should stop."""


def _system_prompt(tags):
    vocab = "\n".join(f"- {t['id']}: {t['label']}" for t in tags)
    return f"""You review Substack posts for a nonprofit's resource library on antizionism.

Relevance:
- "relevant": antizionism (its ideology, rhetoric, history, institutions, or responses to it) is a substantial topic of the post.
- "unsure": antizionism comes up only in passing or as background to another subject (e.g. Israeli politics or security, antisemitism generally, Jewish identity), or you cannot tell. A human will review these.
- "not_relevant": the post has no connection to antizionism at all.
When in doubt, choose "unsure".

relevance_reason: one sentence explaining the relevance judgment.

{_score_rubric()}

too_thin: true if the post is too brief or slight to stand alone as a library resource, e.g. a teaser, a short note pointing elsewhere, or a few lines reacting to a link; false for a short but complete argument or report.

roundup: true if the post is mainly a newsletter digest, link roundup, event listing, fundraising appeal, or organizational announcement; false if it is an article, essay, interview, or report with its own substantive content.

tags: {settings.MIN_TAGS} to {settings.MAX_TAGS} IDs from this vocabulary, most applicable first. Be generous: include every tag that plausibly applies. Use "{NEWS_TAG}" when the post mainly reports events rather than arguing or analyzing.
{vocab}

suggested_tags: up to {settings.MAX_SUGGESTED_TAGS} broad themes the vocabulary above does not cover, that could apply to many posts and would be useful as a filter in a resource library. Be generous; a human curates them. Each must be a subject the post is about (e.g. a movement, institution, region, historical period, or field). Not tone, genre, or format (e.g. satire, polemic, interview), and not details specific to this post (people, events, documents, or one-off arguments). Never repeat a vocabulary tag.

stance: a short phrase describing the author's position, e.g. "critical of X" or "news report, no clear position".

summary: {settings.SUMMARY_MIN_SENTENCES} to {settings.SUMMARY_MAX_SENTENCES} sentences on what the author argues or reports, attributed to the author ("The author argues..."). Neutral wording; do not evaluate the argument. Do not mention paywalls, previews, or missing text; the summary is published as is.

If the text is only a paywalled preview, judge from what is available."""


def _output_schema(tags):
    # Array length bounds aren't supported by structured outputs; enforced in _clean()
    return {
        "type": "object",
        "properties": {
            "relevance": {"type": "string", "enum": RELEVANCE_VALUES},
            "relevance_reason": {"type": "string"},
            "relevance_score": _score_schema(),
            "too_thin": {"type": "boolean"},
            "roundup": {"type": "boolean"},
            "tags": {"type": "array", "items": {"type": "string", "enum": [t["id"] for t in tags]}},
            "suggested_tags": {"type": "array", "items": {"type": "string"}},
            "stance": {"type": "string"},
            "summary": {"type": "string"},
        },
        "required": ["relevance", "relevance_reason", "relevance_score", "too_thin", "roundup", "tags", "suggested_tags", "stance", "summary"],
        "additionalProperties": False,
    }


def _user_message(post):
    context = f"Publication: {post.publication}"
    if post.publication_description:
        context += f"\nAbout the publication: {post.publication_description}"
    paywall = "\nNote: paywalled post; only the public preview is available." if post.paywalled else ""
    return f"{context}\nTitle: {post.title}\nPublished: {post.published}{paywall}\n\n<post>\n{post.text}\n</post>"


def _clean(result, tags):
    vocab_ids = {t["id"] for t in tags}
    vocab_names = vocab_ids | {t["label"].lower() for t in tags}

    kept = [t for t in dict.fromkeys(result["tags"]) if t in vocab_ids]
    if len(kept) < len(result["tags"]):
        log.warning("Dropped non-vocabulary tags: %s", set(result["tags"]) - vocab_ids)
    result["tags"] = kept[: settings.MAX_TAGS]

    suggested = [s.strip() for s in result["suggested_tags"] if s.strip().lower() not in vocab_names]
    result["suggested_tags"] = list(dict.fromkeys(suggested))[: settings.MAX_SUGGESTED_TAGS]
    return result


class Classifier:
    def __init__(self, tags):
        self.tags = tags
        self.client = anthropic.Anthropic(max_retries=settings.MAX_RETRIES)
        self.system = _system_prompt(tags)
        self.schema = _output_schema(tags)

    def classify(self, post):
        return _clean(self._call(self.system, _user_message(post), self.schema, settings.MAX_OUTPUT_TOKENS), self.tags)

    def retag(self, article):
        """relevance_score and news (bool) for a stored article, judged from its title, summary and stance."""
        return self._call(_retag_system(), _retag_message(article), _retag_schema(), settings.RETAG_MAX_OUTPUT_TOKENS)

    def _call(self, system, user, schema, max_tokens):
        try:
            response = self.client.beta.messages.create(
                model=settings.MODEL,
                max_tokens=max_tokens,
                # No extended thinking, so max_tokens covers the JSON alone
                thinking={"type": "between_tools"},
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"format": {"type": "json_schema", "schema": schema}},
                betas=[settings.FALLBACK_BETA],
                fallbacks="default",
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise ClassifyAuthError(f"Claude rejected the credentials ({exc.status_code}): {exc.message}") from exc
        except TypeError as exc:
            # The SDK raises TypeError when it finds no credentials at all
            if "authentication method" not in str(exc):
                raise
            raise ClassifyAuthError("No Claude credentials found; set ANTHROPIC_API_KEY") from exc
        except anthropic.APIStatusError as exc:
            raise ClassifyError(f"API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ClassifyError(f"API connection error: {exc}") from exc

        if response.stop_reason != "end_turn":
            raise ClassifyError(f"Unexpected stop_reason {response.stop_reason!r}")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise ClassifyError("No text block in response")
        return json.loads(text)


def _retag_system():
    return f"""You review short records of Substack posts for a nonprofit's resource library on antizionism.
Judge only from the record given.

{_score_rubric()}

news: true if the post mainly reports events rather than arguing or analyzing."""


def _retag_schema():
    return {
        "type": "object",
        "properties": {"relevance_score": _score_schema(), "news": {"type": "boolean"}},
        "required": ["relevance_score", "news"],
        "additionalProperties": False,
    }


def _retag_message(a):
    return (f"Publication: {a['publication']}\nTitle: {a['title']}\nSummary: {a['summary']}\n"
            f"Stance: {a['stance']}\nTags: {', '.join(a['tags'])}\nRelevance note: {a['relevance_reason']}")
