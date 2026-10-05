from __future__ import annotations
import asyncio
from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher
from .browser import get_current_page


LAST_RESULT_CACHE: Dict[str, List[Dict[str, Any]]] = {}
def visual_sort_items(items_with_boxes: List[Any]) -> List[Any]:
    """
    Sort items in visual reading order (top-to-bottom, left-to-right).
    Handles single-column lists, 2D grids, and horizontal rows.
    """
    valid = [item for item in items_with_boxes if item[1] and item[1].get('width', 0) > 20 and item[1].get('height', 0) > 20]
    if not valid:
        return [item[0] for item in items_with_boxes]

    # Sort primarily by y
    valid.sort(key=lambda it: it[1]['y'])

    # Group into rows based on vertical overlap
    rows: List[List[Any]] = []
    for it, box in valid:
        placed = False
        for row in rows:
            row_y_center = sum(b['y'] + b['height'] / 2 for _, b in row) / len(row)
            item_y_center = box['y'] + box['height'] / 2
            avg_height = sum(b['height'] for _, b in row) / len(row)

            # If vertical centers are within 40% of item height, they belong to the same visual row
            if abs(item_y_center - row_y_center) < max(avg_height * 0.4, 25):
                row.append((it, box))
                placed = True
                break
        if not placed:
            rows.append([(it, box)])

    # Sort rows top to bottom
    rows.sort(key=lambda r: sum(b['y'] for _, b in r) / len(r))

    # Sort items within each row left to right
    sorted_items = []
    for row in rows:
        row.sort(key=lambda it: it[1]['x'])
        for it, _ in row:
            sorted_items.append(it)

    return sorted_items


async def _find_candidate_list_containers(page: Any) -> List[Dict[str, Any]]:
    """
    Scan the page for parent elements whose direct children form a repeated,
    homogeneous cluster (matching tag/role) with consistent dimensions and content.
    Returns candidate dictionaries with 'root' ElementHandle and 'bestKey'.
    """
    try:
        handles = await page.evaluate_handle("""
        () => {
            const isNavOrSidebar = (el) => {
                if (el.closest('header, nav, footer, aside, [role="navigation"], [role="banner"], [role="contentinfo"]')) return true;
                const idCls = ((el.id || '') + ' ' + (typeof el.className === 'string' ? el.className : '')).toLowerCase();
                if (/guide|sidebar|nav-|masthead|menu-container/.test(idCls)) return true;
                return false;
            };

            const roots = Array.from(document.querySelectorAll(
                'div, section, article, table, tbody, ul, ol, main, [role="list"], [role="grid"], [role="feed"]'
            ));

            const candidates = [];

            roots.forEach(root => {
                const rect = root.getBoundingClientRect();
                if (rect.width < 100 || rect.height < 60) return;

                const style = window.getComputedStyle(root);
                if (style.display === 'none' || style.visibility === 'hidden') return;

                const children = Array.from(root.children).filter(child => {
                    const cRect = child.getBoundingClientRect();
                    if (cRect.width <= 0 || cRect.height <= 0) return false;
                    const cStyle = window.getComputedStyle(child);
                    return cStyle.display !== 'none' && cStyle.visibility !== 'hidden';
                });

                if (children.length < 2) return;

                // Group children by tag + role
                const groups = {};
                children.forEach(child => {
                    const role = child.getAttribute('role') || '';
                    const key = child.tagName.toLowerCase() + '|' + role;
                    if (!groups[key]) groups[key] = [];
                    groups[key].push(child);
                });

                let bestKey = null;
                let bestGroup = [];
                for (const [key, group] of Object.entries(groups)) {
                    if (group.length > bestGroup.length) {
                        bestGroup = group;
                        bestKey = key;
                    }
                }

                if (bestGroup.length < 2) return;

                let score = 0;
                // 1. Cluster size
                score += bestGroup.length * 2;
                // 2. Homogeneity ratio
                score += (bestGroup.length / children.length) * 15;

                // 3. Size consistency
                const widths = bestGroup.map(c => c.getBoundingClientRect().width);
                const heights = bestGroup.map(c => c.getBoundingClientRect().height);
                const avgW = widths.reduce((a, b) => a + b, 0) / widths.length;
                const avgH = heights.reduce((a, b) => a + b, 0) / heights.length;

                if (avgW >= 80 && avgH >= 30) {
                    score += 15;
                }

                const varianceW = widths.reduce((sum, w) => sum + Math.abs(w - avgW), 0) / widths.length;
                if (avgW > 0 && (varianceW / avgW) < 0.2) {
                    score += 15;
                }

                // 4. Content richness
                let withLinks = 0;
                let withContentLinks = 0;
                bestGroup.forEach(c => {
                    if (c.querySelector('a[href]')) withLinks++;
                    if (c.querySelector('a[href*="/watch"], a[href*="/shorts"], a[href*="/dp/"]')) withContentLinks++;
                });

                if (withLinks / bestGroup.length > 0.6) score += 20;
                if (withContentLinks > 0) score += 30;

                // 5. Main area vs sidebar/nav
                if (isNavOrSidebar(root)) {
                    score -= 60;
                }

                if (root.closest('main, [role="main"], #primary, #content, #contents')) {
                    score += 25;
                }

                candidates.push({
                    root,
                    bestKey,
                    count: bestGroup.length,
                    score
                });
            });

            candidates.sort((a, b) => b.score - a.score);
            return candidates.slice(0, 5).map(c => ({ root: c.root, bestKey: c.bestKey }));
        }
        """)
        props = await handles.get_properties()
        containers = []
        for p in props.values():
            root_handle = await p.get_property("root")
            key_handle = await p.get_property("bestKey")
            el = root_handle.as_element()
            key = await key_handle.json_value()
            if el:
                containers.append({"root": el, "bestKey": key})
        return containers
    except Exception as e:
        print("LIST CONTAINER ERROR:", e)
        return []


async def _extract_list_items(container: Any) -> List[Dict[str, Any]]:
    """
    Given a tight container element, return a list of visible descriptors
    for its children that look like 'items'.
    """
    child_sel = await container.query_selector_all(":scope > *")
    child_count = len(child_sel)
    items: List[Dict[str, Any]] = []

    for i in range(child_count):
        child = child_sel[i]
        try:
            if not await child.is_visible():
                continue
            # Skip UI helpers inside a header/footer/nav/aside
            if await child.evaluate("node => !!node.closest('header,nav,footer,aside')"):
                continue
            allowed_tags = {"a", "button", "tr", "li", "div", "p", "section"}
            tag = await child.evaluate("node => node.tagName.toLowerCase()")
            if tag not in allowed_tags and not tag.startswith("ytd-"):
                continue

            desc = await _format_element(child)
            if desc.get("href") is None and desc.get("type") == "link":
                href = await child.get_attribute("href")
                if href:
                    desc["href"] = href
            items.append(desc)
        except Exception:
            continue
    return items


async def inspect_list_item(position: str):
    """
    Resolve a numeric list_item target (e.g., "1", "2") to an actual
    Playwright ElementHandle that represents the nth visible item
    inside the best candidate list container, sorted in visual reading order.
    """
    if not position.isdigit():
        return None
    idx = int(position) - 1
    if idx < 0:
        return None

    page = await get_current_page()
    if not page:
        return None

    # Wait for page to finish any in-progress navigation (e.g. after pressing Enter on search)
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=8000)
    except Exception:
        pass  # Page might already be loaded or timeout — continue with polling

    # Poll briefly for list containers to handle pages in transition or loading search results
    containers = []
    for _ in range(8):
        containers = await _find_candidate_list_containers(page)
        if containers:
            break
        await asyncio.sleep(0.5)

    if not containers:
        return None

    # Use the highest-scoring container
    best_candidate = containers[0]
    container = best_candidate["root"]
    best_key = best_candidate.get("bestKey", "")
    expected_tag, expected_role = best_key.split("|") if "|" in best_key else ("", "")

    # Get direct child elements
    children = await container.query_selector_all(":scope > *")
    items_with_boxes: List[Any] = []

    for child in children:
        try:
            if not await child.is_visible():
                continue

            tag = await child.evaluate("node => node.tagName.toLowerCase()")
            role = await child.get_attribute("role") or ""

            # Sibling group match check
            if expected_tag and tag != expected_tag:
                continue
            if expected_role and role != expected_role:
                continue

            box = await child.bounding_box()
            if box and box["width"] > 20 and box["height"] > 20:
                # Find primary clickable link/title within the card
                primary_link = await child.query_selector(
                    "a#video-title, a#video-title-link, h2 a, h3 a, a[href*='/watch'], a#thumbnail, a[href]"
                )
                click_target = primary_link if primary_link else child
                items_with_boxes.append((click_target, box))
        except Exception:
            continue

    if not items_with_boxes:
        return None

    sorted_items = visual_sort_items(items_with_boxes)
    if idx >= len(sorted_items):
        return None

    return sorted_items[idx]

async def _format_element(el: Any) -> Dict[str, Any]:
    """Return a minimal, JSON-serialisable description of *el*.

    Only the fields that are useful for further browser actions are
    included; missing values are ``None`` to keep the structure
    consistent.  All operations are wrapped in try/except blocks – the
    reader is tolerant of unexpected DOM shapes.
    """
    try:
        tag = await el.evaluate("node => node.tagName.toLowerCase()")
    except Exception:
        tag = None

    try:
        role = await el.evaluate("node => node.getAttribute('role') || node.getAttribute('aria-role')")
    except Exception:
        role = None

    # Accessible name: aria‑label/aria‑labelledby, or visible text
    try:
        label = await el.evaluate("node => node.getAttribute('aria-label') || node.getAttribute('aria-labelledby')")
    except Exception:
        label = None
    if not label:
        try:
            label = await el.inner_text()
        except Exception:
            label = None

    try:
        placeholder = await el.get_attribute('placeholder')
    except Exception:
        placeholder = None

    try:
        bounding = await el.bounding_box()
        x = int(bounding['x']) if bounding else None
        y = int(bounding['y']) if bounding else None
        width = int(bounding['width']) if bounding else None
        height = int(bounding['height']) if bounding else None
    except Exception:
        x = y = width = height = None

    try:
        selector_id = await el.evaluate('node => node.getAttribute("id")')
        if selector_id:
            selector = f'#{selector_id}'
        else:
            tag_part = tag if tag else '*'
            cls = await el.get_attribute('class')
            if cls:
                selector = f'{tag_part}.' + '.'.join(c for c in cls.split() if c)
            else:
                selector = tag_part
    except Exception:
        selector = None

    return {
        'type': role or tag or 'unknown',
        'label': label,
        'placeholder': placeholder,
        'selector': selector,
        'x': x,
        'y': y,
        'width': width,
        'height': height,
    }

# ------------------------------------------------------------------
# Utility scoring – how well an element matches a semantic target.
# ------------------------------------------------------------------
from difflib import SequenceMatcher


def _similar(a: Optional[str], b: Optional[str]) -> float:
    """Return a similarity ratio between 0 and 1 for two strings.
    Handles ``None`` gracefully.
    """
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _element_score(desc: Dict[str, Any], target: str) -> float:
    """Return a score of how well *desc* matches *target*.

    Higher is better; a score > 0 is considered a match.
    """
    score = 0.0
    target_l = target.strip().lower()

    weights = {
        'placeholder': 5.0,
        'label': 5.0,
        'selector': 4.0,
        'type': 3.0,
        'role': 3.0,
    }

    # 1. Placeholder
    if desc.get('placeholder'):
        score += weights['placeholder'] * _similar(desc['placeholder'], target_l)

    # 2. Label / visible text
    if desc.get('label'):
        score += weights['label'] * _similar(desc['label'], target_l)

    # 3. Selector
    if desc.get('selector'):
        score += weights['selector'] * _similar(desc['selector'], target_l)

    # 4. Type
    if desc.get('type'):
        score += weights['type'] * _similar(desc['type'], target_l)

    # 5. Searchbar should prefer actual text-entry elements
    if target_l == 'searchbar':
        element_type = str(desc.get('type', '')).lower()
        placeholder = str(desc.get('placeholder', '')).lower()
        if element_type in ('textbox', 'combobox', 'input', 'textarea'):
            score += 20.0
        if 'search' in placeholder:
            score += 20.0
        if element_type == 'button':
            score -= 20.0

    return score

# ------------------------------------------------------------------
# Generic search‑result collector
# ------------------------------------------------------------------
async def collect_search_results(page: Any, limit: int = 10) -> List[Dict[str, Any]]:
    """Collect up to *limit* search-result-like candidates from the current page.

    The collector uses generic heuristics to pick elements that look like
    result items (anchors with href and meaningful text, or
a containers
    that expose a clickable area).  It preserves the DOM/visual
    order and returns a list of element descriptors.
    """
    loc = page.locator("a[href], button,div[role='listitem'] div[role='link'], div[role='button'], ""div[role='row'], tr,div[role='list-item']")
    try:
        await loc.wait_for(state="visible", timeout=4000)
    except Exception:
        return []
    total = await loc.count()
    candidates: List[Dict[str, Any]] = []
    for i in range(total):
        el = loc.nth(i)
        try:
            if not await el.is_visible():
                continue
            cls = await el.get_attribute('class')
            text = await el.inner_text()
            if cls and any(tag in cls.lower() for tag in ("header", "nav", "footer", "sidebar")):
                continue
            if not text or len(text.strip()) < 3:
                continue
            href = await el.get_attribute('href')

            desc = await _format_element(el)
            if href:
                desc['href'] = href

            candidates.append(desc)

            if len(candidates) >= limit:
                break
            
        except Exception:
            continue
    # Deduplicate by selector
    seen = set()
    uniq: List[Dict[str, Any]] = []
    for d in candidates:
        sel = d.get('selector')
        if sel and sel not in seen:
            seen.add(sel)
            uniq.append(d)
    return uniq

# ------------------------------------------------------------------
# Positional target handler
# ------------------------------------------------------------------
async def inspect_positional_target(target: str) -> List[Dict[str, Any]]:
    """Turn positional targets (first_ … tenth_) into an index and return
the descriptor for the nth candidate from the generic collector.
    """
    target_l = target.lower()
    # Map prefixes to zero\-based index
    prefix_map = {
        "first": 0,
        "second": 1,
        "third": 2,
        "fourth": 3,
        "fifth": 4,
        "sixth": 5,
        "seventh": 6,
        "eighth": 7,
        "ninth": 8,
        "tenth": 9,
    }
    idx = None
    for p, i in prefix_map.items():
        if target_l.startswith(p + "_"):
            idx = i
            break
    if idx is None:
        return []
    page = await get_current_page()
    if not page:
        return []
    candidates = await collect_search_results(page)
    if len(candidates) <= idx:
        return []
    LAST_RESULT_CACHE[target] = candidates
    return [candidates[idx]]

async def _get_gmail_compose_region(page: Any) -> Any:
    """Return Gmail's active Compose window if one is open."""
    try:
        region = page.locator('[role="region"][aria-label="New Message"]').last
        if await region.count() > 0 and await region.is_visible():
            return region
    except Exception:
        pass
    return None

async def inspect(filters: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Return element descriptors that match *filters*.

    Parameters
    ----------
    filters
        A list of semantic target strings (e.g. ``"searchbar"`` or
        ``"Compose"``).  If omitted, all common interactive elements
        are returned.
    """
    page = await get_current_page()
    if not page:
        raise RuntimeError("No current page found — ensure browser is ready and opened")

    # Handle positional targets before generic scoring
    if filters:
        for target in filters:
            if target.isdigit():
                list_match = await inspect_list_item(target)
                if list_match:
                    return list_match

            positional_match = await inspect_positional_target(target)
            if positional_match:
                return positional_match

    compose_region = None
    if (
        "mail.google.com" in page.url
        and filters
        and any(f.strip().lower() in {"to", "subject", "message"} for f in filters)
        and compose_region is None
    ):
        return []

    if "mail.google.com" in page.url and filters:
        target_names = {f.strip().lower() for f in filters}
        if target_names & {"to", "subject", "message"}:
            try:
                region = page.locator('[role="region"][aria-label="New Message"]').last
                await region.wait_for(state="visible", timeout=5000)
                compose_region = region
            except Exception:
                compose_region = None

    if compose_region is None:
        compose_region = await _get_gmail_compose_region(page)

    # Common interactive selectors – broad enough for generic sites.
    common_selectors = [
        'button',
        'a[href]',
        'input:not([type=hidden])',
        'select',
        'textarea',
        '[role=button]',
        '[role=link]',
        '[role=textbox]',
        '[role=slider]',
        '[role=menuitem]',
        '[role=option]',
        '[role=combobox]',
    ]

    candidates: List[Dict[str, Any]] = []
    for sel in common_selectors:
        loc = compose_region.locator(sel) if compose_region else page.locator(sel)
        try:
            count = await loc.count()
        except Exception:
            continue
        for i in range(count):
            el = loc.nth(i)
            try:
                if not await el.is_visible():
                    continue
                desc = await _format_element(el)
                candidates.append(desc)
            except Exception:
                continue

    if not filters:
        return candidates

    matched: List[Dict[str, Any]] = []
    for target in filters:
        best_score = 0.0
        best_elements: List[Dict[str, Any]] = []
        for desc in candidates:
            score = _element_score(desc, target)
            if score > best_score:
                best_score = score
                best_elements = [desc]
            elif score > 0.0 and abs(score - best_score) < 1e-6:
                best_elements.append(desc)
        matched.extend(best_elements)
    unique: List[Dict[str, Any]] = []
    seen: set = set()
    for d in matched:
        sel = d.get('selector')
        if sel and sel not in seen:
            seen.add(sel)
            unique.append(d)
    return unique

