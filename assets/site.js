(function () {
  var catalog = [
    { title: "Mounting manuals", href: "mounting-manuals.html", group: "Section" },
    { title: "Engineering knowledge", href: "engineering-knowledge.html", group: "Section" },
    { title: "Stores & Logistics", href: "stores.html", group: "Section" },
    { title: "Warranty", href: "warranty.html", group: "Section" },
    { title: "Truck Mounting Instructions — Index (Revised October 2026)", href: "index-oct26.html", group: "Mounting manuals" },
    { title: "Unpacking", href: "unpacking.html", group: "Mounting manuals" },
    { title: "Mixer Mounting", href: "mixer-mount.html", group: "Mounting manuals" },
    { title: "Hydraulics", href: "hydraulics.html", group: "Mounting manuals" },
    { title: "Drive Line", href: "driveline.html", group: "Mounting manuals" },
    { title: "Water System", href: "water-system.html", group: "Mounting manuals" },
    { title: "Electrical & Remote Control", href: "electrical.html", group: "Mounting manuals" },
    { title: "Mudguards", href: "mudguards.html", group: "Mounting manuals" },
    { title: "Options", href: "options.html", group: "Mounting manuals" },
    { title: "Initial Start Up Procedure — 90 Series", href: "start-up.html", group: "Mounting manuals" },
    { title: "Decals", href: "decals.html", group: "Mounting manuals" },
    { title: "Drawings", href: "drawings.html", group: "Engineering knowledge" },
    { title: "Axle Capacity", href: "axle-capacity.html", group: "Engineering knowledge" },
    { title: "Mixer CG", href: "mixer-cg.html", group: "Engineering knowledge" },
    { title: "Stability", href: "engineering-knowledge.html#stability", group: "Engineering knowledge" },
    { title: "Frame Stress", href: "engineering-knowledge.html#frame-stress", group: "Engineering knowledge" },
    { title: "Hydraulic Schemes", href: "engineering-knowledge.html#hydraulic-schemes", group: "Engineering knowledge" },
    { title: "Mass Properties", href: "engineering-knowledge.html#mass-properties", group: "Engineering knowledge" },
    { title: "Standards", href: "engineering-knowledge.html#standards", group: "Engineering knowledge" },
    { title: "Clearances", href: "engineering-knowledge.html#clearances", group: "Engineering knowledge" },
  ];

  var header = document.getElementById("site-header");
  function onScroll() {
    if (!header) return;
    header.setAttribute("data-scrolled", window.scrollY > 8 ? "1" : "0");
  }
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  var kbd = document.querySelector("[data-kbd]");
  if (kbd) {
    var mac = /Mac|iPhone|iPad/.test(navigator.platform || "");
    kbd.textContent = mac ? "⌘K" : "Ctrl K";
  }

  var form = document.getElementById("site-search");
  var input = document.getElementById("site-search-input");
  var menu = document.getElementById("site-search-menu");
  var clearBtn = form && form.querySelector(".search-clear");
  var selected = -1;
  var hits = [];

  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function highlight(title, q) {
    var i = title.toLowerCase().indexOf(q.toLowerCase());
    if (i < 0 || !q) return esc(title);
    return esc(title.slice(0, i)) + "<strong>" + esc(title.slice(i, i + q.length)) + "</strong>" + esc(title.slice(i + q.length));
  }

  function closeSearch() {
    if (!menu || menu.hidden) return;
    menu.hidden = true;
    menu.innerHTML = "";
    selected = -1;
    hits = [];
    if (input) input.setAttribute("aria-expanded", "false");
  }

  function renderSearch(list, q, emptyNote) {
    if (!menu) return;
    if (!list.length) {
      menu.hidden = false;
      menu.innerHTML = '<p class="search-empty">' + esc(emptyNote || "No matching entries") + "</p>";
      input.setAttribute("aria-expanded", "true");
      selected = -1;
      hits = [];
      return;
    }
    var html = "";
    var last = "";
    list.forEach(function (item, i) {
      if (item.group !== last) {
        html += '<div class="search-label">' + esc(item.group) + "</div>";
        last = item.group;
      }
      html += '<a class="search-hit" role="option" id="hit-' + i + '" href="' + esc(item.href) + '" aria-selected="false"><strong>' + highlight(item.title, q) + "</strong><span>" + esc(item.group) + "</span></a>";
    });
    menu.innerHTML = html;
    menu.hidden = false;
    input.setAttribute("aria-expanded", "true");
    hits = Array.prototype.slice.call(menu.querySelectorAll(".search-hit"));
    selected = 0;
    paintSelection();
  }

  function paintSelection() {
    hits.forEach(function (el, i) {
      el.setAttribute("aria-selected", i === selected ? "true" : "false");
    });
    if (selected >= 0 && hits[selected]) {
      input.setAttribute("aria-activedescendant", hits[selected].id);
      hits[selected].scrollIntoView({ block: "nearest" });
    } else {
      input.removeAttribute("aria-activedescendant");
    }
  }

  function queryResults(q) {
    var needle = q.toLowerCase();
    return catalog
      .filter(function (item) {
        return (item.title + " " + item.group).toLowerCase().indexOf(needle) !== -1;
      })
      .sort(function (a, b) {
        var as = a.title.toLowerCase().indexOf(needle) === 0 ? 0 : 1;
        var bs = b.title.toLowerCase().indexOf(needle) === 0 ? 0 : 1;
        if (as !== bs) return as - bs;
        var ag = a.group === "Section" ? 0 : 1;
        var bg = b.group === "Section" ? 0 : 1;
        return ag - bg;
      })
      .slice(0, 8);
  }

  function syncFilled() {
    if (!form || !input) return;
    form.querySelector(".search").setAttribute("data-filled", input.value ? "1" : "0");
  }

  if (form && input && menu) {
    input.addEventListener("input", function () {
      syncFilled();
      var q = input.value.trim();
      if (!q) {
        closeSearch();
        return;
      }
      renderSearch(queryResults(q), q);
    });

    input.addEventListener("focus", function () {
      var q = input.value.trim();
      if (!q) return;
      renderSearch(queryResults(q), q);
    });

    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        if (menu.hidden) return;
        e.preventDefault();
        if (!hits.length) return;
        selected += e.key === "ArrowDown" ? 1 : -1;
        if (selected < 0) selected = hits.length - 1;
        if (selected >= hits.length) selected = 0;
        paintSelection();
      } else if (e.key === "Escape") {
        closeSearch();
      } else if (e.key === "Enter") {
        if (!menu.hidden && hits[selected]) {
          e.preventDefault();
          window.location.href = hits[selected].getAttribute("href");
        }
      }
    });

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!menu.hidden && hits[selected]) {
        window.location.href = hits[selected].getAttribute("href");
        return;
      }
      var q = input.value.trim();
      var found = q ? queryResults(q) : [];
      if (found[0]) window.location.href = found[0].href;
      else if (q) renderSearch([], q);
    });

    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        input.value = "";
        syncFilled();
        closeSearch();
        input.focus();
      });
    }
  }

  document.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
      if (!input) return;
      e.preventDefault();
      input.focus();
      input.select();
    }
  });

  var sectionsBtn = document.getElementById("sections-btn");
  var sectionsMenu = document.getElementById("sections-menu");

  function closeSections() {
    if (!sectionsMenu || sectionsMenu.hidden) return;
    sectionsMenu.hidden = true;
    if (sectionsBtn) sectionsBtn.setAttribute("aria-expanded", "false");
  }

  if (sectionsBtn && sectionsMenu) {
    sectionsBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = sectionsMenu.hidden;
      closeSearch();
      sectionsMenu.hidden = !open;
      sectionsBtn.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  document.addEventListener("click", function (e) {
    if (menu && !menu.hidden && form && !form.contains(e.target)) closeSearch();
    if (sectionsMenu && !sectionsMenu.hidden && sectionsBtn && !sectionsBtn.contains(e.target) && !sectionsMenu.contains(e.target)) {
      closeSections();
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeSections();
  });

  document.querySelectorAll("[data-shelf]").forEach(function (shelf) {
    var scroller = shelf.querySelector(".shelf-scroll");
    var prev = shelf.querySelector("[data-shelf-prev]");
    var next = shelf.querySelector("[data-shelf-next]");
    var navs = shelf.parentElement.querySelector(".shelf-navs");
    if (!scroller) return;

    function update() {
      var max = scroller.scrollWidth - scroller.clientWidth;
      var overflow = max > 4;
      shelf.setAttribute("data-left", scroller.scrollLeft > 2 ? "1" : "0");
      shelf.setAttribute("data-right", overflow && scroller.scrollLeft < max - 2 ? "1" : "0");
      if (prev) prev.disabled = scroller.scrollLeft <= 2;
      if (next) next.disabled = !overflow || scroller.scrollLeft >= max - 2;
      if (navs) navs.setAttribute("data-overflow", overflow ? "1" : "0");
    }

    if (prev) prev.addEventListener("click", function () {
      scroller.scrollBy({ left: -260, behavior: "smooth" });
    });
    if (next) next.addEventListener("click", function () {
      scroller.scrollBy({ left: 260, behavior: "smooth" });
    });
    scroller.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    update();
  });

  var toc = document.querySelector(".toc-nav");
  if (toc) {
    var links = Array.prototype.slice.call(toc.querySelectorAll(".toc-link"));
    var indicator = toc.querySelector(".toc-indicator");
    var headings = links.map(function (a) {
      return document.getElementById(a.getAttribute("href").slice(1));
    }).filter(Boolean);

    function setActive(id) {
      links.forEach(function (a) {
        var on = a.getAttribute("href") === "#" + id;
        a.classList.toggle("is-active", on);
        if (on && indicator) {
          var li = a.parentElement;
          indicator.style.top = li.offsetTop + "px";
          indicator.style.height = Math.max(li.offsetHeight - 2, 14) + "px";
          indicator.style.opacity = "1";
        }
      });
    }

    function currentHeading() {
      var line = (header ? header.offsetHeight : 56) + 28;
      var active = headings[0];
      headings.forEach(function (h) {
        if (h.getBoundingClientRect().top <= line) active = h;
      });
      return active && active.id;
    }

    function refresh() {
      var id = currentHeading();
      if (id) setActive(id);
    }

    document.addEventListener("scroll", refresh, { passive: true });
    window.addEventListener("resize", refresh);
    if (location.hash && document.getElementById(location.hash.slice(1))) {
      setActive(location.hash.slice(1));
    } else {
      refresh();
    }
  }
})();
