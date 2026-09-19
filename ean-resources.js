(function () {
  // ---- CONFIGURE THIS ----
  var DATA_URL = "https://cdn.jsdelivr.net/gh/exposeaz/website-resources@main/data.json";

  var root = document.getElementById("ean-resources-root");
  var state = { data: null, view: "categories", categoryId: null, search: "", activeTags: [], modalResourceId: null };

  // Categories whose single-category view sorts newest-year-first, in one
  // flat grid (no visual year sections/headers — same layout as every
  // other category). Substacks is deliberately excluded (see
  // renderCategoryResources) — it stays alphabetical instead.
  var YEAR_SORTED_CATEGORIES = ["books", "scholarly-articles", "essays", "legal-commentary", "data-research"];

  function esc(s) {
    return (s || "").replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function matchesFilters(r) {
    var q = state.search.trim().toLowerCase();
    if (q) {
      var hay = (r.title + " " + r.description + " " + r.reference).toLowerCase();
      if (hay.indexOf(q) === -1) return false;
    }
    if (state.activeTags.length) {
      var tags = r.tags || [];
      var ok = state.activeTags.every(function (t) { return tags.indexOf(t) !== -1; });
      if (!ok) return false;
    }
    return true;
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
    html += '</div>';
    html += '<div class="ean-tagbar">';
    state.data.tags.forEach(function (t) {
      var active = state.activeTags.indexOf(t.id) !== -1;
      html += '<button class="' + tagBtnClasses(active) + '" data-tag="' + t.id + '" data-active="' + active + '">' + esc(t.label) + '</button>';
    });
    html += '</div>';
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
    "legal-commentary": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v3M12 6 5 9M12 6l7 3M5 9l-2.5 5A3 3 0 0 0 5 18a3 3 0 0 0 2.5-4L5 9ZM19 9l-2.5 5a3 3 0 0 0 2.5 4 3 3 0 0 0 2.5-4L19 9ZM7 21h10"/></svg>',
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
    if (r.author) {
      html += '<div class="ean-res-author">' + esc(r.author) + '</div>';
    }
    if (r.tags && r.tags.length) {
      html += '<div class="ean-res-tags">' + r.tags.map(function (t) {
        var tagDef = state.data.tags.filter(function (x) { return x.id === t; })[0];
        return '<span data-tag="' + esc(t) + '">' + esc(tagDef ? tagDef.label : t) + '</span>';
      }).join('') + '</div>';
    }
    html += '</div>';
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
    if (r.author) {
      html += '<div class="ean-res-author">' + esc(r.author) + '</div>';
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

  // Renders the resources for a single category view: one flat grid,
  // always — just sorted differently depending on the category. No visual
  // year sections/headers anymore; year still shows on each card itself.
  function renderCategoryResources(categoryId, items) {
    var sorted = items;
    if (categoryId === "substacks") {
      sorted = items.slice().sort(function (a, b) {
        return a.title.localeCompare(b.title);
      });
    } else if (YEAR_SORTED_CATEGORIES.indexOf(categoryId) !== -1) {
      // Newest year first; undated resources sink to the end.
      sorted = items.slice().sort(function (a, b) {
        if (a.year == null && b.year == null) return 0;
        if (a.year == null) return 1;
        if (b.year == null) return -1;
        return b.year - a.year;
      });
    }
    return '<div class="ean-res-grid">' + sorted.map(renderResourceCard).join('') + '</div>';
  }

  function render() {
    var filtering = state.search.trim() !== "" || state.activeTags.length > 0;
    var html = renderToolbar();

    if (state.view === "category") {
      // A category is already selected, so search/tag filters narrow
      // *within* it instead of jumping out to a cross-category search —
      // only the top-level categories view searches everything at once.
      var items = state.data.resources.filter(function (r) { return r.category === state.categoryId; });
      if (filtering) items = items.filter(matchesFilters);
      html += '<div class="ean-crumb"><a href="#" class="ean-crumb-link" data-back="1">&larr; All categories</a> / ' + esc(categoryLabel(state.categoryId));
      if (filtering) html += ' — ' + items.length + ' result' + (items.length === 1 ? '' : 's');
      html += '</div>';
      html += items.length
        ? renderCategoryResources(state.categoryId, items)
        : '<div class="ean-empty">' + (filtering ? 'No resources match your filters in this category.' : 'No resources in this category yet.') + '</div>';
    } else if (filtering) {
      // Flat grid, not year-sectioned: this view spans multiple categories
      // and is ranked by search/filter relevance, not chronology.
      // NOTE: assumption made during planning, not a confirmed requirement —
      // revisit with the user if year-sectioning turns out to be wanted here too.
      var results = state.data.resources.filter(matchesFilters);
      html += '<div class="ean-crumb">' + results.length + ' result' + (results.length === 1 ? '' : 's') + '</div>';
      html += results.length
        ? '<div class="ean-res-grid">' + results.map(renderResourceCard).join('') + '</div>'
        : '<div class="ean-empty">No resources match your filters.</div>';
    } else {
      html += '<div class="ean-cat-grid">';
      state.data.categories.forEach(function (c) {
        var count = state.data.resources.filter(function (r) { return r.category === c.id; }).length;
        html += '<div class="ean-cat-card" data-cat="' + c.id + '">';
        html += '<h3>' + esc(c.label) + '</h3>';
        html += '<p>' + esc(c.blurb || '') + '</p>';
        html += '<div class="ean-cat-count">' + count + ' resource' + (count === 1 ? '' : 's') + '</div>';
        html += '</div>';
      });
      html += '</div>';
    }

    if (state.modalResourceId) {
      var modalRes = state.data.resources.filter(function (r) { return r.id === state.modalResourceId; })[0];
      if (modalRes) html += renderResourceModal(modalRes);
    }

    root.innerHTML = html;
    attachEvents();
  }

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
    root.querySelectorAll(".ean-cat-card").forEach(function (card) {
      card.addEventListener("click", function () {
        state.view = "category";
        state.categoryId = card.getAttribute("data-cat");
        render();
      });
    });
    var back = root.querySelector("[data-back]");
    if (back) {
      back.addEventListener("click", function (e) {
        e.preventDefault();
        state.view = "categories";
        state.categoryId = null;
        render();
      });
    }
    root.querySelectorAll(".ean-res-card").forEach(function (card) {
      card.addEventListener("click", function () {
        state.modalResourceId = card.getAttribute("data-res");
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