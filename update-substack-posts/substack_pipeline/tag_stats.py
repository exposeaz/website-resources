"""Suggested-tag frequency across data/articles.json, to review candidates for config/tags.json.

Run from update-substack-posts/: python -m substack_pipeline.tag_stats
"""

from collections import Counter

from substack_pipeline import state


def main():
    articles = state.load_articles()
    counts = Counter(tag.lower() for a in articles for tag in a.get("suggested_tags", []))
    if not counts:
        print(f"No suggested tags across {len(articles)} articles.")
        return
    print(f"Suggested tags across {len(articles)} articles:\n")
    width = max(len(t) for t in counts)
    for tag, n in counts.most_common():
        print(f"{tag.ljust(width)}  {n}")


if __name__ == "__main__":
    main()
