const ZIREN_MAX_ELEMENTS = 520;
const ZIREN_SNAPSHOT_INTERVAL_MS = 650;
const ZIREN_GROUP_MAX_INTERACTIVE = 14;
const ZIREN_HIGHLIGHT_Z_INDEX = 2147483647;

const zirenIds = new WeakMap();
const zirenElements = new Map();
let zirenNextId = 1;
let zirenSnapshotBusy = false;
let zirenHighlightState = null;

function zirenIdFor(element) {
  let id = zirenIds.get(element);
  if (!id) {
    id = `z-${zirenNextId++}`;
    zirenIds.set(element, id);
  }
  zirenElements.set(id, element);
  return id;
}

function zirenRect(element) {
  const rect = element.getBoundingClientRect();
  return {
    x: rect.left,
    y: rect.top,
    width: rect.width,
    height: rect.height,
  };
}

function zirenRectVisible(rect) {
  return Boolean(
    rect.width >= 2
    && rect.height >= 2
    && rect.right > 0
    && rect.bottom > 0
    && rect.left < window.innerWidth
    && rect.top < window.innerHeight
  );
}

function zirenVisible(element) {
  if (!(element instanceof Element)) return false;
  const style = window.getComputedStyle(element);
  if (
    style.display === "none"
    || style.visibility === "hidden"
    || Number(style.opacity || "1") <= 0.02
  ) {
    return false;
  }
  return zirenRectVisible(element.getBoundingClientRect());
}

function zirenCleanText(value, limit = 220) {
  return String(value || "")
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, limit);
}

function zirenDirectText(element) {
  const parts = [];
  for (const node of element.childNodes) {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = zirenCleanText(node.textContent, 140);
      if (text) parts.push(text);
    }
  }
  return zirenCleanText(parts.join(" "), 180);
}

function zirenAssociatedLabel(element) {
  if (!(element instanceof HTMLInputElement)) return "";
  if (element.labels?.length) {
    return zirenCleanText(
      Array.from(element.labels)
        .map((label) => label.innerText || label.textContent || "")
        .join(" "),
      180,
    );
  }
  return "";
}

function zirenTextFor(element, fallback = "") {
  return zirenCleanText(
    element.getAttribute("aria-label")
    || element.getAttribute("title")
    || zirenAssociatedLabel(element)
    || zirenDirectText(element)
    || fallback
    || element.innerText
    || element.textContent,
    220,
  );
}

function zirenRoleFor(element) {
  const explicit = zirenCleanText(element.getAttribute("role"), 60).toLowerCase();
  if (explicit) return explicit;
  const tag = element.tagName.toLowerCase();
  if (tag === "a") return "link";
  if (tag === "button") return "button";
  if (tag === "select") return "combobox";
  if (tag === "textarea") return "textbox";
  if (tag === "input") {
    const type = (element.getAttribute("type") || "text").toLowerCase();
    if (type === "checkbox") return "checkbox";
    if (type === "radio") return "radio";
    if (["button", "submit", "reset"].includes(type)) return "button";
    return "textbox";
  }
  if (/^h[1-6]$/.test(tag)) return "heading";
  if (tag === "label") return "label";
  return "text";
}

function zirenInteractive(element) {
  const tag = element.tagName.toLowerCase();
  const role = zirenRoleFor(element);
  return Boolean(
    ["a", "button", "input", "select", "textarea"].includes(tag)
    || [
      "button",
      "checkbox",
      "combobox",
      "link",
      "menuitem",
      "option",
      "radio",
      "switch",
      "tab",
      "textbox",
    ].includes(role)
    || element.hasAttribute("onclick")
    || element.tabIndex >= 0
  );
}

function zirenCandidate(element, fallbackText = "") {
  if (!zirenVisible(element)) return null;
  const text = zirenTextFor(element, fallbackText);
  if (!text || text.length > 220) return null;
  const rect = element.getBoundingClientRect();
  if (!zirenRectVisible(rect)) return null;
  const viewportArea = Math.max(1, window.innerWidth * window.innerHeight);
  const area = rect.width * rect.height;
  if (area / viewportArea > 0.72) return null;
  return {
    id: zirenIdFor(element),
    text,
    role: zirenRoleFor(element),
    interactive: zirenInteractive(element),
    rect: zirenRect(element),
    member_ids: [],
  };
}

function zirenCollectBaseElements() {
  const result = [];
  const seen = new Set();
  const structuralSelector = [
    "a",
    "button",
    "input",
    "select",
    "textarea",
    "label",
    "[role]",
    "[aria-label]",
    "[title]",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "legend",
  ].join(",");

  for (const element of document.querySelectorAll(structuralSelector)) {
    if (result.length >= 320) break;
    const candidate = zirenCandidate(element);
    if (!candidate || seen.has(candidate.id)) continue;
    seen.add(candidate.id);
    result.push(candidate);
  }

  const walker = document.createTreeWalker(
    document.body,
    NodeFilter.SHOW_TEXT,
    {
      acceptNode(node) {
        const text = zirenCleanText(node.textContent, 160);
        const parent = node.parentElement;
        if (!text || text.length < 2 || !parent || !zirenVisible(parent)) {
          return NodeFilter.FILTER_REJECT;
        }
        if (["SCRIPT", "STYLE", "NOSCRIPT", "SVG"].includes(parent.tagName)) {
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      },
    },
  );

  let node = walker.nextNode();
  while (node && result.length < 430) {
    const parent = node.parentElement;
    if (parent) {
      const candidate = zirenCandidate(parent, node.textContent || "");
      if (candidate && !seen.has(candidate.id)) {
        seen.add(candidate.id);
        result.push(candidate);
      }
    }
    node = walker.nextNode();
  }

  return result;
}

function zirenUnionRects(rects, padding = 8) {
  if (!rects.length) return null;
  let left = Infinity;
  let top = Infinity;
  let right = -Infinity;
  let bottom = -Infinity;
  for (const rect of rects) {
    left = Math.min(left, rect.left ?? rect.x);
    top = Math.min(top, rect.top ?? rect.y);
    right = Math.max(right, (rect.right ?? ((rect.x || 0) + rect.width)));
    bottom = Math.max(bottom, (rect.bottom ?? ((rect.y || 0) + rect.height)));
  }
  left = Math.max(0, left - padding);
  top = Math.max(0, top - padding);
  right = Math.min(window.innerWidth, right + padding);
  bottom = Math.min(window.innerHeight, bottom + padding);
  return {
    x: left,
    y: top,
    width: Math.max(2, right - left),
    height: Math.max(2, bottom - top),
  };
}

function zirenBuildGroups(baseElements) {
  const groups = [];
  const interactiveById = new Map(
    baseElements.filter((item) => item.interactive).map((item) => [item.id, item]),
  );
  const viewportArea = Math.max(1, window.innerWidth * window.innerHeight);

  for (const heading of baseElements) {
    if (groups.length >= 90) break;
    if (heading.interactive || heading.text.length > 64) continue;
    const headingElement = zirenElements.get(heading.id);
    if (!headingElement) continue;

    let ancestor = headingElement.parentElement;
    let depth = 0;
    while (ancestor && depth < 5) {
      depth += 1;
      const memberCandidates = [];
      for (const element of ancestor.querySelectorAll(
        "a,button,input,select,textarea,[role='button'],[role='checkbox'],[role='radio'],[role='switch'],[role='combobox']",
      )) {
        if (!zirenVisible(element)) continue;
        const id = zirenIdFor(element);
        const known = interactiveById.get(id) || zirenCandidate(element);
        if (!known || !known.interactive) continue;
        const rect = element.getBoundingClientRect();
        const headingRect = headingElement.getBoundingClientRect();
        if (rect.top < headingRect.top - 18) continue;
        if (rect.top > headingRect.bottom + Math.min(420, window.innerHeight * 0.48)) {
          continue;
        }
        memberCandidates.push({ id, element, rect, known });
        if (memberCandidates.length > ZIREN_GROUP_MAX_INTERACTIVE) break;
      }

      if (
        memberCandidates.length >= 2
        && memberCandidates.length <= ZIREN_GROUP_MAX_INTERACTIVE
      ) {
        const rects = [headingElement.getBoundingClientRect()]
          .concat(memberCandidates.map((item) => item.rect));
        const union = zirenUnionRects(rects, 10);
        if (!union) break;
        const areaRatio = (union.width * union.height) / viewportArea;
        if (
          areaRatio <= 0.35
          && union.width <= window.innerWidth * 0.62
          && union.height <= window.innerHeight * 0.62
        ) {
          groups.push({
            id: `group:${heading.id}`,
            text: heading.text,
            role: "group",
            interactive: false,
            rect: union,
            member_ids: [heading.id]
              .concat(memberCandidates.map((item) => item.id))
              .slice(0, 24),
          });
          break;
        }
      }
      ancestor = ancestor.parentElement;
    }
  }
  return groups;
}

function zirenCollectSnapshot() {
  zirenElements.clear();
  const base = zirenCollectBaseElements();
  const groups = zirenBuildGroups(base);
  const elements = groups.concat(base).slice(0, ZIREN_MAX_ELEMENTS);
  return {
    url: location.href,
    title: document.title,
    viewport_width: window.innerWidth,
    viewport_height: window.innerHeight,
    device_pixel_ratio: window.devicePixelRatio || 1,
    elements,
  };
}

async function zirenPublishSnapshot() {
  if (zirenSnapshotBusy || document.visibilityState !== "visible" || !document.body) {
    return;
  }
  zirenSnapshotBusy = true;
  try {
    const snapshot = zirenCollectSnapshot();
    await chrome.runtime.sendMessage({
      type: "ziren-snapshot",
      snapshot,
    });
  } catch (_error) {
    // Browser Bridge may not be installed correctly yet; keep the page untouched.
  } finally {
    zirenSnapshotBusy = false;
  }
}

function zirenCurrentRect(command) {
  const ids = Array.isArray(command.member_ids) && command.member_ids.length
    ? command.member_ids
    : [command.element_id];
  const rects = [];
  for (const id of ids) {
    const element = zirenElements.get(id);
    if (element && zirenVisible(element)) {
      rects.push(element.getBoundingClientRect());
    }
  }
  if (!rects.length) return null;
  return zirenUnionRects(rects, 10);
}

function zirenRemoveHighlight() {
  if (!zirenHighlightState) return;
  cancelAnimationFrame(zirenHighlightState.frameId);
  zirenHighlightState.container.remove();
  zirenHighlightState = null;
}

function zirenHighlight(command) {
  zirenRemoveHighlight();
  const container = document.createElement("div");
  const label = document.createElement("div");
  const badge = document.createElement("span");

  container.setAttribute("data-ziren-browser-highlight", "true");
  Object.assign(container.style, {
    position: "fixed",
    pointerEvents: "none",
    zIndex: String(ZIREN_HIGHLIGHT_Z_INDEX),
    border: "3px solid #00e5ff",
    borderRadius: "10px",
    boxSizing: "border-box",
    boxShadow: "0 0 0 1px rgba(0,229,255,.35), 0 0 24px rgba(0,229,255,.85)",
    background: "rgba(0,229,255,.045)",
    transition: "left 80ms linear, top 80ms linear, width 80ms linear, height 80ms linear",
  });

  Object.assign(label.style, {
    position: "absolute",
    left: "0",
    top: "-31px",
    minHeight: "26px",
    maxWidth: "360px",
    display: "flex",
    alignItems: "center",
    gap: "7px",
    padding: "4px 9px",
    color: "#dfffff",
    background: "rgba(1,12,18,.96)",
    border: "1px solid rgba(0,229,255,.75)",
    borderRadius: "8px",
    font: "600 12px/1.2 system-ui, -apple-system, Segoe UI, sans-serif",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
    boxShadow: "0 0 14px rgba(0,229,255,.35)",
  });

  Object.assign(badge.style, {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    width: "18px",
    height: "18px",
    borderRadius: "999px",
    color: "#001015",
    background: "#00e5ff",
    fontWeight: "800",
    flex: "0 0 auto",
  });
  badge.textContent = "Z";
  label.appendChild(badge);
  label.appendChild(document.createTextNode(zirenCleanText(command.label, 120) || "Ziren"));
  container.appendChild(label);
  document.documentElement.appendChild(container);

  const startedAt = performance.now();
  const duration = Math.max(1200, Number(command.duration_ms) || 6500);
  const state = { container, frameId: 0 };
  zirenHighlightState = state;

  function update(now) {
    if (zirenHighlightState !== state) return;
    const rect = zirenCurrentRect(command);
    if (!rect || now - startedAt >= duration) {
      zirenRemoveHighlight();
      return;
    }
    Object.assign(container.style, {
      left: `${Math.round(rect.x)}px`,
      top: `${Math.round(rect.y)}px`,
      width: `${Math.round(rect.width)}px`,
      height: `${Math.round(rect.height)}px`,
    });
    state.frameId = requestAnimationFrame(update);
  }
  state.frameId = requestAnimationFrame(update);
}

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === "ziren-command" && message.command?.type === "highlight") {
    zirenHighlight(message.command);
  }
});

setInterval(zirenPublishSnapshot, ZIREN_SNAPSHOT_INTERVAL_MS);
window.addEventListener("focus", zirenPublishSnapshot, { passive: true });
window.addEventListener("scroll", () => {
  if (!zirenHighlightState) zirenPublishSnapshot();
}, { passive: true });
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") zirenPublishSnapshot();
});
setTimeout(zirenPublishSnapshot, 150);
