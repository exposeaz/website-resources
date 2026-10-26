(function () {
  // ---- CONFIGURE THIS ----
  // The Squarespace stub sets EAN_RESOURCES_BASE to a commit-pinned jsDelivr URL;
  // @main is only the fallback.
  var DATA_URL = window.EAN_RESOURCES_BASE ? window.EAN_RESOURCES_BASE + "/data.json"
    : "https://cdn.jsdelivr.net/gh/exposeaz/website-resources@main/data.json";

  // Wording shown above a single Substack's articles. {title} and {link} are filled in.
  var SUBSTACK_NOTE = "This is a set of articles from {title} related to antizionism, automatically curated by AI. " +
    "See the full Substack for all posts: {link}";

  // Wording shown above the Substack cards in the Substacks category.
  var SUBSTACKS_INTRO = "Each Substack below links to a set of its articles related to antizionism, automatically curated by AI. " +
    "Select a Substack to browse its articles, or visit the full Substack for everything it publishes.";

  // Substack articles aren't a top-level category; each one appears under its
  // publication's card in the Substacks category, matched by web address.
  var SUBSTACK_CATEGORY = "substacks";
  var ARTICLE_CATEGORY = "substack-articles";
  var LAYOUT_KEY = "ean-layout";
  // Results are shown this many at a time, with a "Show more" button for the next batch
  var PAGE_SIZE = 20;

  var root = document.getElementById("ean-resources-root");
  var state = {
    data: null, view: "categories", categoryId: null, substackId: null,
    search: "", activeTags: [], tagMode: "any", modalResourceId: null, layout: loadLayout(),
    shown: PAGE_SIZE, pageKey: null
  };

  // Card/list choice is remembered per visitor; storage can be unavailable
  // (private windows, blocked site data), so it falls back to cards.
  function loadLayout() {
    try { return localStorage.getItem(LAYOUT_KEY) === "list" ? "list" : "cards"; } catch (e) { return "cards"; }
  }
  function saveLayout() {
    try { localStorage.setItem(LAYOUT_KEY, state.layout); } catch (e) { /* not remembered */ }
  }

  function hostOf(url) {
    try { return new URL(url).host.toLowerCase(); } catch (e) { return null; }
  }
  function resourceById(id) {
    return state.data.resources.filter(function (r) { return r.id === id; })[0];
  }
  function substackFor(article) {
    var host = hostOf(article.url);
    return state.data.resources.filter(function (r) {
      return r.category === SUBSTACK_CATEGORY && hostOf(r.url) === host;
    })[0];
  }
  function articlesFor(substack) {
    var host = hostOf(substack.url);
    return state.data.resources.filter(function (r) {
      return r.category === ARTICLE_CATEGORY && hostOf(r.url) === host;
    });
  }
  // Newest first by full date when present, else by year; undated sink to the end
  function byNewest(a, b) {
    var da = a.date || (a.year ? String(a.year) : ""), db = b.date || (b.year ? String(b.year) : "");
    return db.localeCompare(da);
  }
  function bylineFor(r) {
    if (r.category === ARTICLE_CATEGORY) {
      var sub = substackFor(r);
      return "via " + (sub ? sub.title : r.author);
    }
    return r.author;
  }

  function esc(s) {
    return (s || "").replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function matchesFilters(r) {
    // Every word must appear somewhere, in any order, so "Adam Louis-Klein" matches "Louis-Klein, Adam"
    var words = state.search.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (words.length) {
      var hay = [r.title, r.author, r.description, r.reference].join(" ").toLowerCase();
      if (!words.every(function (w) { return hay.indexOf(w) !== -1; })) return false;
    }
    if (state.activeTags.length) {
      var n = tagMatches(r);
      if (state.tagMode === "all" ? n < state.activeTags.length : n === 0) return false;
    }
    return true;
  }

  function tagMatches(r) {
    var tags = r.tags || [];
    return state.activeTags.filter(function (t) { return tags.indexOf(t) !== -1; }).length;
  }

  // "Any" mode: resources matching more of the selected tags come first (stable otherwise)
  function rankByTagMatches(items) {
    if (state.tagMode !== "any" || state.activeTags.length < 2) return items;
    return items.map(function (r, i) { return { r: r, i: i, n: tagMatches(r) }; })
      .sort(function (a, b) { return b.n - a.n || a.i - b.i; })
      .map(function (x) { return x.r; });
  }

  function categoryLabel(id) {
    var c = state.data.categories.filter(function (c) { return c.id === id; })[0];
    return c ? c.label : id;
  }

  // Squarespace's own button classes so tag pills pick up the
  // site's real Button color/shape/hover from Design > Buttons.
  function tagBtnClasses(active) {
    return "sqs-block-button-element ean-tag" +
      (active ? " sqs-block-button-element--primary" : " sqs-block-button-element--tertiary");
  }

  function renderToolbar() {
    var html = '<div class="ean-toolbar">';
    html += '<input class="ean-search" type="text" placeholder="Search titles, descriptions, citations..." value="' + esc(state.search) + '" />';
    html += '<button type="button" class="ean-clear-btn" data-clear-filters="1">Clear filters</button>';
    html += '<div class="ean-segmented ean-layout-toggle" role="group" aria-label="Layout">';
    ["cards", "list"].forEach(function (l) {
      html += '<button type="button" data-layout="' + l + '" aria-pressed="' + (state.layout === l) + '">' +
        (l === "cards" ? "Cards" : "List") + '</button>';
    });
    html += '</div>';
    html += '</div>';
    html += '<div class="ean-tagbar">';
    state.data.tags.forEach(function (t) {
      var active = state.activeTags.indexOf(t.id) !== -1;
      html += '<button class="' + tagBtnClasses(active) + '" data-tag="' + t.id + '" data-active="' + active + '">' + esc(t.label) + '</button>';
    });
    html += '</div>';
    // Only meaningful once two or more tags are selected
    if (state.activeTags.length > 1) {
      html += '<div class="ean-tagmode"><span class="ean-tagmode-label">Selected tags:</span>';
      html += '<div class="ean-segmented" role="group" aria-label="Tag matching">';
      [["any", "Match any"], ["all", "Match all"]].forEach(function (m) {
        html += '<button type="button" data-tagmode="' + m[0] + '" aria-pressed="' + (state.tagMode === m[0]) + '">' + m[1] + '</button>';
      });
      html += '</div></div>';
    }
    return html;
  }

  // Simple line-icon fallback shown when a resource has no image.
  // Rendered on a colored field (--ean-card-image-bg) using currentColor,
  // so it automatically follows text color / brand accent.
  var CATEGORY_ICONS = {
    "books": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5.5C10.2 4.4 7.7 4 5.5 4.2A1 1 0 0 0 4.6 5.2v13a1 1 0 0 0 1.1 1c2-.2 4.3.2 6.3 1.3" fill="currentColor" fill-opacity=".08"/><path d="M12 5.5C10.2 4.4 7.7 4 5.5 4.2A1 1 0 0 0 4.6 5.2v13a1 1 0 0 0 1.1 1c2-.2 4.3.2 6.3 1.3"/><path d="M12 5.5c1.8-1.1 4.3-1.5 6.5-1.3a1 1 0 0 1 .9 1v13a1 1 0 0 1-1.1 1c-2-.2-4.3.2-6.3 1.3" fill="currentColor" fill-opacity=".08"/><path d="M12 5.5c1.8-1.1 4.3-1.5 6.5-1.3a1 1 0 0 1 .9 1v13a1 1 0 0 1-1.1 1c-2-.2-4.3.2-6.3 1.3"/><path d="M12 5.5v14.8"/></svg>',
    "scholarly-articles": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h8l4 4v11.5a1.5 1.5 0 0 1-1.5 1.5H6a1.5 1.5 0 0 1-1.5-1.5V4.5A1.5 1.5 0 0 1 6 3Z" fill="currentColor" fill-opacity=".06"/><path d="M14 3v3.5A1.5 1.5 0 0 0 15.5 8H18"/><path d="M8 11h5M8 14h3.5"/></svg>',
    "data-research": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="12" width="3.4" height="7" fill="currentColor" fill-opacity=".12" stroke="currentColor"/><rect x="10.3" y="7" width="3.4" height="12" fill="currentColor" fill-opacity=".12" stroke="currentColor"/><rect x="16.6" y="4" width="3.4" height="15" fill="currentColor" fill-opacity=".12" stroke="currentColor"/><path d="M2.5 20.5h19"/></svg>',
    "essays": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20l4.5-1.2L19 8.3a1.8 1.8 0 0 0 0-2.6l-.7-.7a1.8 1.8 0 0 0-2.6 0L5.2 15.5 4 20Z" fill="currentColor" fill-opacity=".08"/><path d="M4 20l4.5-1.2L19 8.3a1.8 1.8 0 0 0 0-2.6l-.7-.7a1.8 1.8 0 0 0-2.6 0L5.2 15.5 4 20Z"/><path d="M14.5 6.5l3 3"/></svg>',
    "substacks": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2" fill="currentColor" fill-opacity=".06"/><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m4 6.5 8 6.2 8-6.2"/></svg>'
  };

  // If a resource's image URL 404s, times out, or otherwise fails to load
  // (these are all hotlinked third-party URLs), swap in the same category
  // icon used when there's no image at all, instead of leaving a collapsed
  // empty box.
  window.__eanImgError = function (imgEl, category) {
    var icon = CATEGORY_ICONS[category] || CATEGORY_ICONS["essays"];
    var wrap = imgEl.parentElement;
    wrap.classList.add("ean-res-image--fallback");
    wrap.innerHTML = icon;
  };

  function resourceImageHtml(r, extraClass) {
    var cls = "ean-res-image" + (extraClass ? " " + extraClass : "");
    if (r.image) {
      return '<div class="' + cls + '"><img src="' + esc(r.image) + '" alt="" loading="lazy" onerror="window.__eanImgError(this, \'' + esc(r.category) + '\')"></div>';
    }
    var icon = CATEGORY_ICONS[r.category] || CATEGORY_ICONS["essays"];
    return '<div class="' + cls + ' ean-res-image--fallback">' + icon + '</div>';
  }

  function renderResourceCard(r) {
    var html = '<div class="ean-res-card" data-res="' + esc(r.id) + '">';
    // Image block disabled sitewide (Sept 2026): only ~30% of resources
    // have a real image, so most cards were just showing a repeated
    // generic category icon instead of adding anything. `data.json` still
    // carries the `image` field and resourceImageHtml()/CATEGORY_ICONS/the
    // onerror fallback are all still intact below — to bring images back,
    // just re-add: html += resourceImageHtml(r);
    html += '<div class="ean-res-header">';
    html += '<span class="ean-res-badge">' + esc(categoryLabel(r.category)) + '</span>';
    if (r.year) {
      html += '<span class="ean-res-year">' + esc(String(r.year)) + '</span>';
    }
    html += '</div>';
    html += '<h4>' + esc(r.title) + '</h4>';
    if (bylineFor(r)) {
      html += '<div class="ean-res-author">' + esc(bylineFor(r)) + '</div>';
    }
    html += substackCountHtml(r);
    html += tagsHtml(r);
    html += '</div>';
    return html;
  }

  function tagsHtml(r) {
    if (!r.tags || !r.tags.length) return "";
    return '<div class="ean-res-tags">' + r.tags.map(function (t) {
      var tagDef = state.data.tags.filter(function (x) { return x.id === t; })[0];
      var match = state.activeTags.indexOf(t) !== -1;
      return '<span data-tag="' + esc(t) + '" data-match="' + match + '">' + esc(tagDef ? tagDef.label : t) + '</span>';
    }).join('') + '</div>';
  }

  // On a Substack card: how many curated articles it holds, or that it opens on Substack
  function substackCountHtml(r) {
    if (r.category !== SUBSTACK_CATEGORY) return "";
    var n = articlesFor(r).length;
    return '<div class="ean-res-count">' + (n ? n + ' article' + (n === 1 ? '' : 's') : 'Opens on Substack &#8599;') + '</div>';
  }

  function renderResourceRow(r) {
    var meta = [bylineFor(r), r.year ? String(r.year) : "", categoryLabel(r.category)].filter(Boolean);
    var html = '<div class="ean-res-row" data-res="' + esc(r.id) + '">';
    html += '<div class="ean-res-row-main"><h4>' + esc(r.title) + '</h4>';
    html += '<div class="ean-res-row-meta">' + meta.map(esc).join(' &middot; ') + '</div>';
    html += substackCountHtml(r) + '</div>';
    html += tagsHtml(r);
    html += '</div>';
    return html;
  }

  // Cards (masonry grid) or list, per the visitor's layout choice
  function renderItems(items) {
    var total = items.length;
    items = rankByTagMatches(items).slice(0, state.shown);
    var html = state.layout === "list"
      ? '<div class="ean-res-list">' + items.map(renderResourceRow).join('') + '</div>'
      : '<div class="ean-res-grid">' + items.map(renderResourceCard).join('') + '</div>';
    if (total > items.length) {
      html += '<div class="ean-show-more-wrap"><button type="button" class="ean-show-more" data-show-more="1">' +
        'Show more</button><span>Showing ' + items.length + ' of ' + total + '</span></div>';
    }
    return html;
  }

  // No image here deliberately — the modal is the reading view, so it
  // leads with the description at a larger, friendlier size instead.
  function renderResourceModal(r) {
    var html = '<div class="ean-modal-overlay" data-modal-overlay="1">';
    html += '<div class="ean-modal" role="dialog" aria-modal="true">';
    html += '<button class="ean-modal-close" data-modal-close="1" aria-label="Close">&times;</button>';
    html += '<div class="ean-modal-body">';
    html += '<div class="ean-res-header">';
    html += '<span class="ean-res-badge">' + esc(categoryLabel(r.category)) + '</span>';
    if (r.year) {
      html += '<span class="ean-res-year">' + esc(String(r.year)) + '</span>';
    }
    html += '</div>';
    html += '<h4>' + esc(r.title) + '</h4>';
    if (bylineFor(r)) {
      html += '<div class="ean-res-author">' + esc(bylineFor(r)) + '</div>';
    }
    if (r.description) {
      html += '<p class="ean-res-desc">' + esc(r.description) + '</p>';
    } else {
      html += '<p class="ean-res-desc empty">No description yet.</p>';
    }
    if (r.reference) {
      html += '<p class="ean-res-reference">' + esc(r.reference) + '</p>';
    }
    if (r.url) {
      html += '<a class="ean-res-link" href="' + esc(r.url) + '" target="_blank" rel="noopener">Continue to source &rarr;</a>';
    }
    html += '</div></div></div>';
    return html;
  }

  // A single category: Substack cards alphabetical (they're publications,
  // not dated pieces); everything else newest first.
  function renderCategoryResources(categoryId, items) {
    var sorted = items.slice().sort(categoryId === SUBSTACK_CATEGORY
      ? function (a, b) { return a.title.localeCompare(b.title); }
      : byNewest);
    return renderItems(sorted);
  }

  // One Substack's curated articles, under a header linking to the full Substack
  function renderSubstackView(filtering) {
    var sub = resourceById(state.substackId);
    var items = articlesFor(sub).sort(byNewest);
    if (filtering) items = items.filter(matchesFilters);
    var link = '<a href="' + esc(sub.url) + '" target="_blank" rel="noopener">' + esc(sub.title) + ' &#8599;</a>';
    var html = '<div class="ean-crumb"><a href="#" class="ean-crumb-link" data-back="1">&larr; All categories</a> / ' +
      '<a href="#" class="ean-crumb-link" data-back-substacks="1">' + esc(categoryLabel(SUBSTACK_CATEGORY)) + '</a> / ' + esc(sub.title);
    if (filtering) html += ' — ' + items.length + ' result' + (items.length === 1 ? '' : 's');
    html += '</div>';
    html += '<div class="ean-substack-head"><h3>' + esc(sub.title) + '</h3>';
    if (sub.description) html += '<p>' + esc(sub.description) + '</p>';
    html += '<p class="ean-substack-note">' +
      esc(SUBSTACK_NOTE).replace("{title}", esc(sub.title)).replace("{link}", link) + '</p></div>';
    html += items.length
      ? renderItems(items)
      : '<div class="ean-empty">No articles match your filters.</div>';
    return html;
  }

  function render() {
    // A new listing (view, search or tags changed) starts again from the first page
    var pageKey = JSON.stringify([state.view, state.categoryId, state.substackId, state.search, state.activeTags, state.tagMode]);
    if (pageKey !== state.pageKey) {
      state.pageKey = pageKey;
      state.shown = PAGE_SIZE;
    }
    var filtering = state.search.trim() !== "" || state.activeTags.length > 0;
    var html = renderToolbar();

    if (state.view === "substack") {
      html += renderSubstackView(filtering);
    } else if (state.view === "category") {
      // A category is already selected, so search/tag filters narrow
      // *within* it instead of jumping out to a cross-category search —
      // only the top-level categories view searches everything at once.
      var items = state.data.resources.filter(function (r) { return r.category === state.categoryId; });
      if (filtering) items = items.filter(matchesFilters);
      html += '<div class="ean-crumb"><a href="#" class="ean-crumb-link" data-back="1">&larr; All categories</a> / ' + esc(categoryLabel(state.categoryId));
      if (filtering) html += ' — ' + items.length + ' result' + (items.length === 1 ? '' : 's');
      html += '</div>';
      if (state.categoryId === SUBSTACK_CATEGORY) html += '<p class="ean-substack-note ean-substacks-intro">' + esc(SUBSTACKS_INTRO) + '</p>';
      html += items.length
        ? renderCategoryResources(state.categoryId, items)
        : '<div class="ean-empty">' + (filtering ? 'No resources match your filters in this category.' : 'No resources in this category yet.') + '</div>';
    } else if (filtering) {
      // Newest first; in "match any" mode, more matching tags still come first
      var results = state.data.resources.filter(matchesFilters).sort(byNewest);
      html += '<div class="ean-crumb">' + results.length + ' result' + (results.length === 1 ? '' : 's') + '</div>';
      html += results.length
        ? renderItems(results)
        : '<div class="ean-empty">No resources match your filters.</div>';
    } else {
      var asList = state.layout === "list";
      html += asList ? '<div class="ean-res-list">' : '<div class="ean-cat-grid">';
      state.data.categories.forEach(function (c) {
        if (c.id === ARTICLE_CATEGORY) return;
        var count = state.data.resources.filter(function (r) { return r.category === c.id; }).length;
        var countHtml = '<div class="ean-cat-count">' + count + ' resource' + (count === 1 ? '' : 's') + '</div>';
        if (asList) {
          html += '<div class="ean-res-row ean-cat-row" data-cat="' + c.id + '">';
          html += '<div class="ean-res-row-main"><h4>' + esc(c.label) + '</h4>';
          if (c.blurb) html += '<div class="ean-res-row-meta">' + esc(c.blurb) + '</div>';
          html += '</div>' + countHtml + '</div>';
        } else {
          html += '<div class="ean-cat-card" data-cat="' + c.id + '">';
          html += '<h3>' + esc(c.label) + '</h3>';
          html += '<p>' + esc(c.blurb || '') + '</p>';
          html += countHtml + '</div>';
        }
      });
      html += '</div>';
    }

    if (state.modalResourceId) {
      var modalRes = state.data.resources.filter(function (r) { return r.id === state.modalResourceId; })[0];
      if (modalRes) html += renderResourceModal(modalRes);
    }

    root.innerHTML = html;
    attachEvents();
    layoutMasonry();
  }

  // Computes the masonry layout by hand instead of using CSS `columns:` —
  // see the comment on .ean-res-grid in the CSS for why. Places each card
  // in whichever column is currently shortest, left-to-right by column,
  // matching the reading order the resources are already sorted in.
  var MASONRY_COLUMN_WIDTH = 220;
  var MASONRY_GAP = 16;

  function layoutMasonry() {
    var grid = root.querySelector(".ean-res-grid");
    if (!grid) return;

    var cards = grid.querySelectorAll(".ean-res-card");
    if (!cards.length) { grid.style.height = "0px"; return; }

    var containerWidth = grid.clientWidth;
    var columnCount = Math.max(1, Math.floor((containerWidth + MASONRY_GAP) / (MASONRY_COLUMN_WIDTH + MASONRY_GAP)));
    var columnWidth = (containerWidth - MASONRY_GAP * (columnCount - 1)) / columnCount;
    var columnHeights = new Array(columnCount).fill(0);

    cards.forEach(function (card) {
      card.style.width = columnWidth + "px";
      // Height depends on the width just set (text wrapping), so measure
      // after applying it and before positioning.
      var shortest = 0;
      for (var i = 1; i < columnCount; i++) {
        if (columnHeights[i] < columnHeights[shortest]) shortest = i;
      }
      card.style.left = shortest * (columnWidth + MASONRY_GAP) + "px";
      card.style.top = columnHeights[shortest] + "px";
      columnHeights[shortest] += card.offsetHeight + MASONRY_GAP;
    });

    grid.style.height = Math.max.apply(null, columnHeights) - MASONRY_GAP + "px";
  }

  var masonryResizeTimer = null;
  window.addEventListener("resize", function () {
    clearTimeout(masonryResizeTimer);
    masonryResizeTimer = setTimeout(layoutMasonry, 150);
  });

  function attachEvents() {
    var searchEl = root.querySelector(".ean-search");
    if (searchEl) {
      searchEl.addEventListener("input", function (e) {
        state.search = e.target.value;
        render();
        var el = root.querySelector(".ean-search");
        el.focus();
        el.selectionStart = el.selectionEnd = el.value.length;
      });
    }
    root.querySelectorAll(".ean-tag").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var tag = btn.getAttribute("data-tag");
        var idx = state.activeTags.indexOf(tag);
        if (idx === -1) state.activeTags.push(tag); else state.activeTags.splice(idx, 1);
        render();
      });
    });
    var clearBtn = root.querySelector("[data-clear-filters]");
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        state.search = "";
        state.activeTags = [];
        render();
      });
    }
    root.querySelectorAll("[data-cat]").forEach(function (card) {
      card.addEventListener("click", function () {
        state.view = "category";
        state.categoryId = card.getAttribute("data-cat");
        render();
      });
    });
    var more = root.querySelector("[data-show-more]");
    if (more) {
      more.addEventListener("click", function () {
        state.shown += PAGE_SIZE;
        render();
      });
    }
    root.querySelectorAll("[data-tagmode]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.tagMode = btn.getAttribute("data-tagmode");
        render();
      });
    });
    root.querySelectorAll("[data-layout]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.layout = btn.getAttribute("data-layout");
        saveLayout();
        render();
      });
    });
    var backSubstacks = root.querySelector("[data-back-substacks]");
    if (backSubstacks) {
      backSubstacks.addEventListener("click", function (e) {
        e.preventDefault();
        state.view = "category";
        state.categoryId = SUBSTACK_CATEGORY;
        state.substackId = null;
        render();
      });
    }
    var back = root.querySelector("[data-back]");
    if (back) {
      back.addEventListener("click", function (e) {
        e.preventDefault();
        state.view = "categories";
        state.categoryId = null;
        state.substackId = null;
        render();
      });
    }
    // A Substack card opens its curated articles, or the Substack itself when it has none
    root.querySelectorAll(".ean-res-card, .ean-res-row:not(.ean-cat-row)").forEach(function (card) {
      card.addEventListener("click", function () {
        var r = resourceById(card.getAttribute("data-res"));
        if (r.category === SUBSTACK_CATEGORY) {
          if (articlesFor(r).length) {
            state.view = "substack";
            state.substackId = r.id;
            render();
            root.scrollIntoView();
          } else if (r.url) {
            window.open(r.url, "_blank", "noopener");
          }
          return;
        }
        state.modalResourceId = r.id;
        render();
      });
    });
    var overlay = root.querySelector("[data-modal-overlay]");
    if (overlay) {
      overlay.addEventListener("click", function (e) {
        if (e.target === overlay) closeModal();
      });
      root.querySelector("[data-modal-close]").addEventListener("click", closeModal);
    }
  }

  function closeModal() {
    state.modalResourceId = null;
    render();
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && state.modalResourceId) closeModal();
  });

  root.innerHTML = '<div class="ean-empty">Loading resources&hellip;</div>';
  fetch(DATA_URL)
    .then(function (res) { return res.json(); })
    .then(function (data) {
      state.data = data;
      render();
    })
    .catch(function (err) {
      root.innerHTML = '<div class="ean-empty">Could not load resources. Check DATA_URL. (' + esc(err.message || String(err)) + ')</div>';
    });
})();