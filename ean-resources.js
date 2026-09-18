(function () {
  // ---- CONFIGURE THIS ----
  var DATA_URL = "https://cdn.jsdelivr.net/gh/exposeaz/website-resources@main/data.json";

  var root = document.getElementById("ean-resources-root");
  var state = { data: null, view: "categories", categoryId: null, search: "", activeTags: [] };

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
    "books": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 5c2-1 5-1 7 0v14c-2-1-5-1-7 0V5Z"/><path d="M20 5c-2-1-5-1-7 0v14c2-1 5-1 7 0V5Z"/></svg>',
    "scholarly-articles": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M6 3h9l4 4v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z"/><path d="M9 12h6M9 16h6M9 8h3"/></svg>',
    "essays": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 20l4.5-1.2L19 8.3a1.8 1.8 0 0 0 0-2.6l-.7-.7a1.8 1.8 0 0 0-2.6 0L5.2 15.5 4 20Z"/></svg>',
    "legal-commentary": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 3v3M12 6 5 9M12 6l7 3M5 9l-2.5 5A3 3 0 0 0 5 18a3 3 0 0 0 2.5-4L5 9ZM19 9l-2.5 5a3 3 0 0 0 2.5 4 3 3 0 0 0 2.5-4L19 9ZM7 21h10"/></svg>',
    "organizations": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 21V8l8-5 8 5v13"/><path d="M9 21v-6h6v6M4 21h16"/></svg>',
    "letters": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="5" width="18" height="14" rx="1.5"/><path d="m3 6 9 7 9-7"/></svg>',
    "declarations": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 4v16M4 5h13l-2 3 2 3H4"/></svg>'
  };

  function renderResourceCard(r) {
    var html = '<div class="ean-res-card">';
    if (r.image) {
      html += '<div class="ean-res-image"><img src="' + esc(r.image) + '" alt="" loading="lazy"></div>';
    } else {
      var icon = CATEGORY_ICONS[r.category] || CATEGORY_ICONS["essays"];
      html += '<div class="ean-res-image ean-res-image--fallback">' + icon + '</div>';
    }
    html += '<div class="ean-res-header">';
    html += '<span class="ean-res-badge">' + esc(categoryLabel(r.category)) + '</span>';
    if (r.year) {
      html += '<span class="ean-res-year">' + esc(String(r.year)) + '</span>';
    }
    html += '</div>';
    html += '<h4>' + esc(r.title) + '</h4>';
    if (r.description) {
      html += '<p class="ean-res-desc">' + esc(r.description) + '</p>';
    } else {
      html += '<p class="ean-res-desc empty">No description yet.</p>';
    }
    if (r.tags && r.tags.length) {
      html += '<div class="ean-res-tags">' + r.tags.map(function (t) {
        var tagDef = state.data.tags.filter(function (x) { return x.id === t; })[0];
        return '<span>' + esc(tagDef ? tagDef.label : t) + '</span>';
      }).join('') + '</div>';
    }
    html += '<div class="ean-res-ref">' + esc(r.reference) + '</div>';
    if (r.url) {
      html += '<a class="ean-res-link" href="' + esc(r.url) + '" target="_blank" rel="noopener">Visit source &rarr;</a>';
    }
    html += '</div>';
    return html;
  }

  function render() {
    var filtering = state.search.trim() !== "" || state.activeTags.length > 0;
    var html = renderToolbar();

    if (filtering) {
      var results = state.data.resources.filter(matchesFilters);
      html += '<div class="ean-crumb">' + results.length + ' result' + (results.length === 1 ? '' : 's') + '</div>';
      html += results.length
        ? '<div class="ean-res-grid">' + results.map(renderResourceCard).join('') + '</div>'
        : '<div class="ean-empty">No resources match your filters.</div>';
    } else if (state.view === "categories") {
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
    } else if (state.view === "category") {
      var items = state.data.resources.filter(function (r) { return r.category === state.categoryId; });
      html += '<div class="ean-crumb"><a href="#" class="ean-crumb-link" data-back="1">&larr; All categories</a> / ' + esc(categoryLabel(state.categoryId)) + '</div>';
      html += items.length
        ? '<div class="ean-res-grid">' + items.map(renderResourceCard).join('') + '</div>'
        : '<div class="ean-empty">No resources in this category yet.</div>';
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
  }

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