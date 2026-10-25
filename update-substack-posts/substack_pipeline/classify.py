"""One Claude call per post: relevance, summary, tags, suggested tags, stance."""

import json
import logging

import anthropic

from config import settings

log = logging.getLogger(__name__)

RELEVANCE_VALUES = ["relevant", "unsure", "not_relevant"]


class ClassifyError(Exception):
    pass


def _system_prompt(tags):
    vocab = "\n".join(f"- {t['id']}: {t['label']}" for t in tags)
    return f"""You review Substack posts for a nonprofit's resource library on antizionism.

Relevance:
- "relevant": antizionism (its ideology, rhetoric, history, institutions, or responses to it) is a topic of the post, even loosely or in passing.
- "unsure": you cannot tell whether the post touches on antizionism.
- "not_relevant": the post has no connection to antizionism at all.
When in doubt between "not_relevant" and anything else, do not choose "not_relevant".

relevance_reason: one sentence explaining the relevance judgment.

too_thin: true if the post is too brief or slight to stand alone as a library resource, e.g. a teaser, a short note pointing elsewhere, or a few lines reacting to a link; false for a short but complete argument or report.

roundup: true if the post is mainly a newsletter digest, link roundup, event listing, fundraising appeal, or organizational announcement; false if it is an article, essay, interview, or report with its own substantive content.

tags: {settings.MIN_TAGS} to {settings.MAX_TAGS} IDs from this vocabulary, most applicable first:
{vocab}

suggested_tags: up to {settings.MAX_SUGGESTED_TAGS} broad themes the vocabulary above does not cover, that could apply to many posts and would be useful as a filter in a resource library. Not details specific to this post (people, events, documents, or one-off arguments). Empty if none. Never repeat a vocabulary tag.

stance: a short phrase describing the author's position, e.g. "critical of X" or "news report, no clear position".

summary: {settings.SUMMARY_MIN_SENTENCES} to {settings.SUMMARY_MAX_SENTENCES} sentences on what the author argues or reports, attributed to the author ("The author argues..."). Neutral wording; do not evaluate the argument.

If the text is only a paywalled preview, judge from what is available."""


def _output_schema(tags):
    # Array length bounds aren't supported by structured outputs; enforced in _clean()
    return {
        "type": "object",
        "properties": {
            "relevance": {"type": "string", "enum": RELEVANCE_VALUES},
            "relevance_reason": {"type": "string"},
            "too_thin": {"type": "boolean"},
            "roundup": {"type": "boolean"},
            "tags": {"type": "array", "items": {"type": "string", "enum": [t["id"] for t in tags]}},
            "suggested_tags": {"type": "array", "items": {"type": "string"}},
            "stance": {"type": "string"},
            "summary": {"type": "string"},
        },
        "required": ["relevance", "relevance_reason", "too_thin", "roundup", "tags", "suggested_tags", "stance", "summary"],
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
        try:
            response = self.client.beta.messages.create(
                model=settings.MODEL,
                max_tokens=settings.MAX_OUTPUT_TOKENS,
                # No extended thinking, so MAX_OUTPUT_TOKENS covers the JSON alone
                thinking={"type": "between_tools"},
                system=self.system,
                messages=[{"role": "user", "content": _user_message(post)}],
                output_config={"format": {"type": "json_schema", "schema": self.schema}},
                betas=[settings.FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.APIStatusError as exc:
            raise ClassifyError(f"API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ClassifyError(f"API connection error: {exc}") from exc

        if response.stop_reason != "end_turn":
            raise ClassifyError(f"Unexpected stop_reason {response.stop_reason!r}")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise ClassifyError("No text block in response")
        return _clean(json.loads(text), self.tags)
