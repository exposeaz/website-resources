"""One Claude call per post: relevance, summary, tags, suggested tags, stance."""

import hashlib
import json
import logging

import anthropic

from config import settings

log = logging.getLogger(__name__)

RELEVANCE_VALUES = ["relevant", "unsure", "not_relevant"]
NEWS_TAG = "news"


def _vocab_line(t):
    line = f"- {t['id']}: {t['label']}"
    return f"{line} (only when {t['scope']})" if t.get("scope") else line


def scoped_tags(tags):
    """Tags with a narrow, explicit scope; tag_review re-checks these on stored articles."""
    return [t for t in tags if t.get("scope")]


def scoped_signature(tags):
    """Changes whenever any scope's wording changes, so tag_review knows what to re-check."""
    return hashlib.sha1(json.dumps(scoped_tags(tags), sort_keys=True).encode()).hexdigest()[:12]


_RELEVANCE_RULES = """Relevance:
- "relevant": antizionism (its ideology, rhetoric, history, institutions, or responses to it), or a theme in the tag vocabulary below as it bears on antizionism, is a substantial topic of the post.
- "unsure": antizionism comes up only in passing or as background to another subject (e.g. Israeli politics or security, antisemitism generally, Jewish identity), or you cannot tell. A human will review these.
- "not_relevant": the post has no connection to antizionism at all.
When in doubt, choose "unsure"."""


def _score_rubric():
    lo, hi = settings.RELEVANCE_SCORE_MIN, settings.RELEVANCE_SCORE_MAX
    return (f"relevance_score: {lo} to {hi}, how useful the post would be as a library resource on antizionism or on "
            f"any theme in the tag vocabulary as it bears on antizionism. Judge depth, not how often the word "
            f"\"antizionism\" appears: a post centred on one of these themes (e.g. its history, sources, or institutions) "
            f"can score {hi}. {hi} = develops one or more of these themes in depth, with its own analysis, evidence, or "
            f"history; {lo} = these themes are barely present. A post that mainly restates a familiar thesis without "
            f"developing it scores below one that does.")


def _tag_rule():
    return (f"{settings.MIN_TAGS} to {settings.MAX_TAGS} IDs from this vocabulary, most central first. Tag only themes "
            f"the post as a whole is about or develops at some length; a theme mentioned in a sentence or an aside does "
            f"not count. Fewer, accurate tags are better than more, weaker ones. A tag with an \"only when\" note "
            f"applies only when that note is true. Use \"{NEWS_TAG}\" when the post mainly reports events rather than "
            f"arguing or analyzing.")


def _score_schema():
    return {"type": "integer", "enum": list(range(settings.RELEVANCE_SCORE_MIN, settings.RELEVANCE_SCORE_MAX + 1))}


class ClassifyError(Exception):
    pass


class ClassifyAuthError(Exception):
    """Missing or rejected credentials; fails every post the same way, so the run should stop."""


def _system_prompt(tags):
    vocab = "\n".join(_vocab_line(t) for t in tags)
    return f"""You review Substack posts for a nonprofit's resource library on antizionism.

{_RELEVANCE_RULES}

relevance_reason: one sentence explaining the relevance judgment.

{_score_rubric()}

too_thin: true if the post is too brief or slight to stand alone as a library resource, e.g. a teaser, a short note pointing elsewhere, or a few lines reacting to a link; false for a short but complete argument or report.

roundup: true if the post is mainly a newsletter digest, link roundup, event listing, fundraising appeal, or organizational announcement; false if it is an article, essay, interview, or report with its own substantive content.

tags: {_tag_rule()}
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


def _clean_tags(ids, tags):
    """Vocabulary IDs only, deduplicated, at most MAX_TAGS."""
    vocab_ids = {t["id"] for t in tags}
    kept = [t for t in dict.fromkeys(ids) if t in vocab_ids]
    if len(kept) < len(ids):
        log.warning("Dropped non-vocabulary tags: %s", set(ids) - vocab_ids)
    return kept[: settings.MAX_TAGS]


def _clean(result, tags):
    vocab_names = {t["id"] for t in tags} | {t["label"].lower() for t in tags}
    result["tags"] = _clean_tags(result["tags"], tags)
    suggested = [s.strip() for s in result["suggested_tags"] if s.strip().lower() not in vocab_names]
    result["suggested_tags"] = list(dict.fromkeys(suggested))[: settings.MAX_SUGGESTED_TAGS]
    return result


class Classifier:
    def __init__(self, tags):
        self.tags = tags
        self.client = anthropic.Anthropic(max_retries=settings.MAX_RETRIES)
        self.system = _system_prompt(tags)
        self.schema = _output_schema(tags)
        self.scoped_signature = scoped_signature(tags)
        self.retag_system = _retag_system(tags)
        self.retag_schema = _retag_schema(tags)
        # Changes whenever the retag rules or vocabulary change, so retag knows what to re-judge
        self.retag_signature = hashlib.sha1(
            (self.retag_system + json.dumps(self.retag_schema, sort_keys=True)).encode()).hexdigest()[:12]

    def classify(self, post):
        return _clean(self._call(self.system, _user_message(post), self.schema, settings.MAX_OUTPUT_TOKENS), self.tags)

    def review_scoped_tags(self, article, scoped):
        """{tag id: bool} for each scoped tag, judged from the stored article record."""
        system = ("You review short records of Substack posts for a nonprofit's resource library on antizionism. "
                  "Judge only from the record given. For each tag, answer true only if its condition holds:\n"
                  + "\n".join(f"- {t['id']}: {t['scope']}" for t in scoped))
        schema = {"type": "object", "properties": {t["id"]: {"type": "boolean"} for t in scoped},
                  "required": [t["id"] for t in scoped], "additionalProperties": False}
        return self._call(system, _retag_message(article), schema, settings.TAG_REVIEW_MAX_OUTPUT_TOKENS)

    def retag(self, article):
        """relevance, relevance_score and tags for a stored article, judged from its title, summary and stance."""
        result = self._call(self.retag_system, _retag_message(article), self.retag_schema, settings.RETAG_MAX_OUTPUT_TOKENS)
        result["tags"] = _clean_tags(result["tags"], self.tags)
        return result

    def group_duplicates(self, articles):
        """Groups of near-duplicate articles from one publication: [{"keep": i, "drop": [j, ...], "reason": str}]."""
        return self._call(_DEDUPE_SYSTEM, _dedupe_message(articles), _DEDUPE_SCHEMA,
                          settings.DEDUPE_MAX_OUTPUT_TOKENS)["groups"]

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


def _retag_system(tags):
    vocab = "\n".join(_vocab_line(t) for t in tags)
    return f"""You review short records of Substack posts for a nonprofit's resource library on antizionism.
Judge only from the record given.

{_RELEVANCE_RULES}

{_score_rubric()}

tags: {_tag_rule()}
{vocab}"""


def _retag_schema(tags):
    # Array length bounds aren't supported by structured outputs; enforced in _clean_tags()
    return {
        "type": "object",
        "properties": {
            "relevance": {"type": "string", "enum": RELEVANCE_VALUES},
            "relevance_score": _score_schema(),
            "tags": {"type": "array", "items": {"type": "string", "enum": [t["id"] for t in tags]}},
        },
        "required": ["relevance", "relevance_score", "tags"],
        "additionalProperties": False,
    }


def _retag_message(a):
    return (f"Publication: {a['publication']}\nTitle: {a['title']}\nSummary: {a['summary']}\n"
            f"Stance: {a['stance']}")


_DEDUPE_SYSTEM = """You review the posts one Substack publication has in a nonprofit's resource library on antizionism.
Judge only from the records given.

Find posts that make essentially the same argument as another post in the list: the same main thesis, without a distinct contribution of their own. A distinct contribution is something like a specific case, event, document, or historical episode examined, data, or a different line of argument. Posts that share a thesis but each have a distinct contribution are not duplicates.

Group the duplicates. In each group, keep the post most useful to a reader: the one with the greatest distinct contribution or, if all are equally general, the fullest statement of the argument. Leave out posts that have no duplicate.

For each group give keep (the kept post's number), drop (the other posts' numbers), and reason (one sentence on the shared argument)."""

_DEDUPE_SCHEMA = {
    "type": "object",
    "properties": {
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "keep": {"type": "integer"},
                    "drop": {"type": "array", "items": {"type": "integer"}},
                    "reason": {"type": "string"},
                },
                "required": ["keep", "drop", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["groups"],
    "additionalProperties": False,
}


def _dedupe_message(articles):
    return "\n\n".join(f"[{i}] {a['date']} | {a['title']}\nSummary: {a['summary']}\nTags: {', '.join(a['tags'])}"
                        for i, a in enumerate(articles))
