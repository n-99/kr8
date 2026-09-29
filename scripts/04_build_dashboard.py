# -*- coding: utf-8 -*-
"""KR8 step 4: filter -> CSV + dashboard, in one go (replaces the old steps 3-5).

The rows written to the dashboard are exactly the rows selected here, so the
dashboard can no longer drift away from the CSV. Year range, max versions,
buckets, compilations, breakbeat hardcore, reissues, white label and YouTube
filters are live in the page; everything else comes from config.py.
"""
import csv
import html
import sqlite3
import sys
import textwrap

import config
from common import (Params, Stats, check_schema, in_default_view, load_data, pause,
                    select_rows, setup_console)

setup_console()

GENRE_LABEL = {"J": "J", "D": "DnB", "B": "BH"}
WHY_LABEL = {"remix": "remix", "nj_artist": "non-jungle artist", "nj_label": "non-jungle label",
             "small": "small act"}

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jungle Hidden Gems</title>
<style>
    body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #121212; color: #e0e0e0; margin: 0; padding: 20px; }
    h1 { color: #00e676; text-align: center; margin: 0 0 18px; }
    .controls { display: flex; gap: 10px; justify-content: center; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
    .controls label { font-size: 14px; color: #bdbdbd; display: flex; align-items: center; gap: 6px; }
    input[type=text], input[type=number], select { padding: 9px 10px; border-radius: 5px; border: 1px solid #333; background: #1e1e1e; color: #fff; font-size: 14px; }
    input[type=text] { width: 300px; max-width: 100%; }
    input[type=number] { width: 72px; }
    .chips { display: flex; gap: 8px; justify-content: center; align-items: center; margin-bottom: 14px; flex-wrap: wrap; }
    .chip-group { display: flex; gap: 6px; align-items: center; padding: 4px 10px; border: 1px solid #2c2c2c; border-radius: 6px; }
    .chip-group > span { color: #808080; font-size: 13px; margin-right: 2px; }
    .chip { display: inline-flex; align-items: center; gap: 5px; padding: 4px 10px; border: 1px solid #333; border-radius: 14px; background: #1e1e1e; font-size: 13px; cursor: pointer; user-select: none; }
    .chip:hover { border-color: #555; }
    .chip:has(input:checked) { border-color: #00e676; color: #00e676; }
    .chip input { accent-color: #00e676; margin: 0; }
    :focus-visible { outline: 2px solid #64b5f6; outline-offset: 2px; }
    #count { text-align: center; color: #9e9e9e; font-size: 14px; margin-bottom: 10px; }
    .table-wrap { overflow-x: auto; border-radius: 8px; }
    table { width: 100%; border-collapse: collapse; background: #1e1e1e; }
    th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #333; vertical-align: top; }
    th { background-color: #2c2c2c; color: #00e676; cursor: pointer; user-select: none; white-space: nowrap; }
    th:hover { background-color: #383838; }
    th.nosort { cursor: default; }
    th.nosort:hover { background-color: #2c2c2c; }
    tr.master-row:hover { background-color: #252525; }
    tr.details-row { display: none; background-color: #181818; }
    tr.details-row.show { display: table-row; }
    .expand-btn { cursor: pointer; font-weight: bold; color: #00e676; width: 20px; display: inline-block; text-align: center; }
    .mark-btn { background: none; border: 0; color: #616161; font-size: 17px; cursor: pointer; padding: 0 4px; line-height: 1; }
    .mark-btn:hover { color: #bdbdbd; }
    .mark-want { color: #ffd54f; }
    .mark-seen { color: #00e676; }
    a { color: #64b5f6; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .yt-link { display: inline-block; margin-right: 15px; margin-bottom: 5px; font-size: 13px; color: #ff5252; }
    .yt-link:hover { color: #ff8a80; }
    .release-list { list-style-type: none; padding: 0; margin: 0; }
    .release-list li { margin-bottom: 5px; }
    .remix-text { color: #ffb74d; font-style: italic; }
    .tag { display: inline-block; padding: 1px 7px; border-radius: 4px; font-size: 12px; font-weight: 600; background: #2c2c2c; color: #e0e0e0; }
    .t-J { color: #00e676; }
    .t-D { color: #64b5f6; }
    .t-B { color: #ce93d8; }
    .badge { display: inline-block; margin-left: 4px; padding: 1px 6px; border: 1px solid #444; border-radius: 4px; font-size: 11px; color: #bdbdbd; }
    .why { display: block; margin-top: 3px; font-size: 12px; color: #757575; }
    .num { text-align: right; }
    @media (max-width: 700px) { body { padding: 10px; } th, td { padding: 8px; } }
</style>
</head>
<body>

<h1>🌴 Jungle Hidden Gems 🌴</h1>

<div class="controls">
    <input type="text" id="searchInput" placeholder="Search artist, title, label, cat#, remixer...">
    <label title="Compilations and jungle remixes always ignore this range">Year <input type="number" id="yMin" value="__YMIN__" min="1980" max="2030"> to <input type="number" id="yMax" value="__YMAX__" min="1980" max="2030"></label>
    <label>Max versions <select id="maxV">__MAXV_OPTIONS__</select></label>
    <select id="markFilter">
        <option value="all">All records</option>
        <option value="hideseen">Hide seen</option>
        <option value="want">Only wanted</option>
    </select>
</div>
<div class="chips">
    <div class="chip-group"><span>Show</span>
        <label class="chip"><input type="checkbox" data-bucket="remix" checked> Jungle remixes</label>
        <label class="chip"><input type="checkbox" data-bucket="nj_artist" checked> Non-jungle artist</label>
        <label class="chip"><input type="checkbox" data-bucket="nj_label" checked> Non-jungle label</label>
        <label class="chip"><input type="checkbox" data-bucket="small" checked> Small acts</label>
    </div>
    <div class="chip-group"><span>Include</span>
        <label class="chip"><input type="checkbox" id="incComp"> Compilations</label>
        <label class="chip"><input type="checkbox" id="incBH"> Breakbeat hardcore</label>
        <label class="chip"><input type="checkbox" id="incReiss"> Reissued</label>
    </div>
    <div class="chip-group"><span>Only</span>
        <label class="chip"><input type="checkbox" id="onlyWL"> White label</label>
        <label class="chip"><input type="checkbox" id="onlyYT"> With YouTube</label>
    </div>
</div>
<div id="count"></div>

<div class="table-wrap">
<table id="gemsTable">
    <thead>
        <tr>
            <th class="nosort" style="width: 30px;"></th>
            <th class="nosort" style="width: 34px;" title="Click a star to mark: wanted, seen, none"></th>
            <th data-col="2" data-type="num">Year</th>
            <th data-col="3">Tag</th>
            <th data-col="4">Title</th>
            <th data-col="5">Artist</th>
            <th data-col="6">Label</th>
            <th data-col="7">Cat#</th>
            <th data-col="8" data-type="num" title="Versions of this master on Discogs (all formats)">Ver.</th>
            <th data-col="9">Jungle remix highlight</th>
            <th data-col="10">YouTube</th>
        </tr>
    </thead>
    <tbody id="tableBody">
__ROWS__
    </tbody>
</table>
</div>

<script>
(function () {
    'use strict';
    var tbody = document.getElementById('tableBody');
    var rowEls = Array.prototype.slice.call(tbody.querySelectorAll('tr.master-row'));

    // Everything the filters need is computed once, so filtering never touches the DOM tree.
    var items = rowEls.map(function (row) {
        var next = row.nextElementSibling;
        var detail = (next && next.classList.contains('details-row')) ? next : null;
        var d = row.dataset;
        return {
            row: row, detail: detail, key: d.key,
            y: parseInt(d.y, 10) || 0, v: parseInt(d.v, 10) || 1,
            tags: d.tags ? d.tags.split(' ') : [],
            g: d.g, comp: d.comp === '1', wl: d.wl === '1', reiss: d.reiss === '1', yt: d.yt === '1',
            cells: Array.prototype.slice.call(row.cells).map(function (c) { return c.textContent.trim().toLowerCase(); }),
            text: (row.textContent + ' ' + (detail ? detail.textContent : '')).toLowerCase()
        };
    });

    // ---- seen / wanted marks (kept in this browser's localStorage)
    var STORE_KEY = 'kr8v3:marks';
    var marks = {};
    try { marks = JSON.parse(window.localStorage.getItem(STORE_KEY) || '{}') || {}; } catch (e) { marks = {}; }
    function saveMarks() { try { window.localStorage.setItem(STORE_KEY, JSON.stringify(marks)); } catch (e) { /* private mode */ } }
    var MARK_TEXT = { '': '\\u2606', want: '\\u2605', seen: '\\u2713' };
    var NEXT_MARK = { '': 'want', want: 'seen', seen: '' };
    function paintMark(it) {
        var btn = it.row.querySelector('.mark-btn');
        var m = marks[it.key] || '';
        btn.textContent = MARK_TEXT[m];
        btn.className = 'mark-btn' + (m ? ' mark-' + m : '');
    }

    // ---- filters
    function el(id) { return document.getElementById(id); }
    var search = el('searchInput'), yMinEl = el('yMin'), yMaxEl = el('yMax'), maxVEl = el('maxV');
    var markSel = el('markFilter'), incComp = el('incComp'), incBH = el('incBH'), incReiss = el('incReiss');
    var onlyWL = el('onlyWL'), onlyYT = el('onlyYT'), countEl = el('count');
    var bucketEls = Array.prototype.slice.call(document.querySelectorAll('input[data-bucket]'));

    function applyFilters() {
        var yMin = parseInt(yMinEl.value, 10) || 0;
        var yMax = parseInt(yMaxEl.value, 10) || 9999;
        var maxV = parseInt(maxVEl.value, 10) || 99;
        var term = search.value.trim().toLowerCase();
        var mode = markSel.value;
        var on = {};
        bucketEls.forEach(function (b) { on[b.getAttribute('data-bucket')] = b.checked; });
        var shown = 0;
        items.forEach(function (it) {
            var ok = true;
            if (it.comp) { if (!incComp.checked) ok = false; }            // compilations ignore the year range
            else if (it.tags.indexOf('remix') === -1 && (it.y < yMin || it.y > yMax)) ok = false;   // remixes too
            if (ok && it.g === 'B' && !incBH.checked) ok = false;
            if (ok && it.reiss && !incReiss.checked) ok = false;
            if (ok && it.v > maxV) ok = false;
            if (ok) {
                var any = false;
                for (var i = 0; i < it.tags.length; i++) { if (on[it.tags[i]]) { any = true; break; } }
                ok = any;
            }
            if (ok && onlyWL.checked && !it.wl) ok = false;
            if (ok && onlyYT.checked && !it.yt) ok = false;
            if (ok) {
                var m = marks[it.key] || '';
                if (mode === 'hideseen' && m === 'seen') ok = false;
                else if (mode === 'want' && m !== 'want') ok = false;
            }
            if (ok && term && it.text.indexOf(term) === -1) ok = false;
            it.row.style.display = ok ? '' : 'none';
            if (ok) { shown++; }
            else if (it.detail) {
                it.detail.classList.remove('show');
                var btn = it.row.querySelector('.expand-btn');
                if (btn) btn.textContent = '+';
            }
        });
        countEl.textContent = 'Showing ' + shown + ' of ' + items.length + ' records';
    }

    var timer;
    search.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(applyFilters, 150); });
    [yMinEl, yMaxEl, maxVEl, markSel, incComp, incBH, incReiss, onlyWL, onlyYT].concat(bucketEls).forEach(function (c) {
        c.addEventListener('change', applyFilters);
    });

    // ---- row buttons (delegated)
    var byRow = {};
    items.forEach(function (it) { byRow[it.row.id] = it; });
    tbody.addEventListener('click', function (e) {
        var t = e.target;
        var tr = t.closest ? t.closest('tr.master-row') : null;
        if (!tr) return;
        var it = byRow[tr.id];
        if (t.classList.contains('expand-btn') && it.detail) {
            it.detail.classList.toggle('show');
            t.textContent = it.detail.classList.contains('show') ? '\\u2212' : '+';
        } else if (t.classList.contains('mark-btn')) {
            var nxt = NEXT_MARK[marks[it.key] || ''];
            if (nxt) marks[it.key] = nxt; else delete marks[it.key];
            saveMarks();
            paintMark(it);
            if (markSel.value !== 'all') applyFilters();
        }
    });

    // ---- sorting: per-column direction, cell text pre-computed, detail rows travel with their record
    var sortState = { col: -1, dir: 'asc' };
    function sortKey(it, col, type) {
        if (type === 'num') return col === 2 ? it.y : it.v;
        return it.cells[col];
    }
    Array.prototype.slice.call(document.querySelectorAll('th[data-col]')).forEach(function (th) {
        th.addEventListener('click', function () {
            var col = parseInt(th.getAttribute('data-col'), 10);
            var type = th.getAttribute('data-type') || 'text';
            sortState.dir = (sortState.col === col && sortState.dir === 'asc') ? 'desc' : 'asc';
            sortState.col = col;
            var mult = sortState.dir === 'asc' ? 1 : -1;
            items.sort(function (a, b) {
                var ka = sortKey(a, col, type), kb = sortKey(b, col, type);
                return ka < kb ? -mult : ka > kb ? mult : 0;
            });
            var frag = document.createDocumentFragment();
            items.forEach(function (it) {
                frag.appendChild(it.row);
                if (it.detail) frag.appendChild(it.detail);
            });
            tbody.appendChild(frag);
        });
    });

    items.forEach(paintMark);
    applyFilters();
})();
</script>
</body>
</html>
"""


def esc(s):
    return html.escape(str(s), quote=True)


def render_row(idx, r):
    rid = "row-%d" % idx
    attrs = ('id="%s" data-key="%s" data-y="%d" data-v="%d" data-tags="%s" data-g="%s" '
             'data-comp="%d" data-wl="%d" data-reiss="%d" data-yt="%d"') % (
        rid, esc(r["key"]), r["year"], r["versions"], " ".join(r["tags"]), r["gtag"],
        r["comp"], r["wl"], r["reiss"], r["yt"])

    expand = '<td><span class="expand-btn" title="Show releases">+</span></td>' if r["n"] > 1 else "<td></td>"
    mark = '<td><button type="button" class="mark-btn" title="Cycle: wanted, seen, none">\u2606</button></td>'

    badges = '<span class="tag t-%s">%s</span>' % (r["gtag"], GENRE_LABEL[r["gtag"]])
    if r["comp"]:
        badges += '<span class="badge">comp</span>'
    if r["wl"]:
        badges += '<span class="badge">white label</span>'
    if r["reiss"]:
        badges += '<span class="badge">reissue</span>'
    why = ", ".join(WHY_LABEL[t] for t in r["tags"])
    tag_cell = '<td>%s<span class="why">%s</span></td>' % (badges, esc(why))

    yt = "".join('<a href="%s" target="_blank" rel="noopener" class="yt-link">\u25b6 %s</a>' % (
        esc(v["url"]), esc(v["title"].split(" - ", 1)[-1])) for v in r["videos"])
    remixes = "; ".join(r["remixes"])
    remix_cls = ' class="remix-text"' if remixes else ""

    out = ['<tr class="master-row" %s>' % attrs, expand, mark,
           "<td>%s</td>" % esc(r["year_text"]), tag_cell,
           '<td><a href="%s" target="_blank" rel="noopener">%s</a></td>' % (esc(r["url"]), esc(r["title"])),
           "<td>%s</td>" % esc(r["artist"]), "<td>%s</td>" % esc(r["label"]),
           "<td>%s</td>" % esc(r["catno"]),
           '<td class="num">%d</td>' % r["versions"],
           "<td%s>%s</td>" % (remix_cls, esc(remixes)), "<td>%s</td>" % yt, "</tr>"]

    if r["n"] > 1:
        lis = []
        for x in r["releases"]:
            extra = ", ".join(p for p in (x["label"], x["year"], "white label" if x["wl"] else "") if p)
            lis.append('<li><a href="%s" target="_blank" rel="noopener">Release #%d</a> %s%s</li>' % (
                esc(x["url"]), x["id"], esc(x["catno"]), (" (%s)" % esc(extra)) if extra else ""))
        out.append('<tr class="details-row"><td colspan="11"><strong>%d matching releases:</strong>'
                   '<ul class="release-list">%s</ul></td></tr>' % (r["n"], "".join(lis)))
    return "\n".join(out)


def write_html(rows, P):
    body = "\n".join(render_row(i, r) for i, r in enumerate(rows))
    opts = "".join('<option value="%d"%s>%d</option>' % (
        v, " selected" if v == P.UI_MAX_VERSIONS else "", v) for v in range(1, P.EXPORT_MAX_VERSIONS + 1))
    page = (PAGE.replace("__YMIN__", str(P.UI_YEAR_MIN)).replace("__YMAX__", str(P.UI_YEAR_MAX))
            .replace("__MAXV_OPTIONS__", opts).replace("__ROWS__", body))
    with open(config.HTML_FILE, "w", encoding="utf-8") as f:
        f.write(page)


def write_csv(rows):
    with open(config.CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:   # BOM: Excel reads it right
        w = csv.writer(f)
        w.writerow(["Discogs URL", "Title", "Main Artist", "Label", "Cat#", "Year", "Genre tag",
                    "Versions on Discogs", "Releases kept", "Why", "Flags", "Jungle Remix Highlight"])
        for r in rows:
            flags = ", ".join(n for n, on in (("comp", r["comp"]), ("white label", r["wl"]),
                                              ("reissue", r["reiss"]), ("youtube", r["yt"])) if on)
            w.writerow([r["url"], r["title"], r["artist"], r["label"], r["catno"], r["year_text"],
                        GENRE_LABEL[r["gtag"]], r["versions"], r["n"], ", ".join(r["tags"]), flags,
                        "; ".join(r["remixes"])])


def main():
    conn = sqlite3.connect(config.DB_FILE)
    check_schema(conn)
    P = Params()
    print("Loading database ...")
    stats = Stats(conn, P.USE_GROUPS)
    data = load_data(conn)
    conn.close()
    if P.USE_GROUPS and not stats.has_groups:
        print("Note: no alias / sublabel groups loaded (run 02_build_groups.py to merge them).")

    print("Selecting ...")
    rows = select_rows(data, stats, P)
    write_csv(rows)
    write_html(rows, P)

    view = [r for r in rows if in_default_view(r, P)]

    def split(rs):
        g, t = {}, {}
        for r in rs:
            g[r["gtag"]] = g.get(r["gtag"], 0) + 1
            for k in r["tags"]:
                t[k] = t.get(k, 0) + 1
        return (", ".join("%s %d" % (GENRE_LABEL[k], g[k]) for k in ("J", "D", "B") if k in g),
                ", ".join("%s %d" % (WHY_LABEL[k], t[k]) for k in ("remix", "nj_artist", "nj_label", "small")
                          if k in t))

    def out(text):
        print(textwrap.fill(text, 78, subsequent_indent="      "))

    print("\n" + "=" * 60)
    out("Records in the dashboard: %s" % format(len(rows), ","))
    out("  by genre tag: %s" % split(rows)[0])
    out("  by bucket (overlapping): %s" % split(rows)[1])
    out("Visible on first load: %s (years %d-%d, versions <= %d, no comps / BH / reissues)" % (
        format(len(view), ","), P.UI_YEAR_MIN, P.UI_YEAR_MAX, P.UI_MAX_VERSIONS))
    out("  by genre tag: %s" % split(view)[0])
    out("  by bucket (overlapping): %s" % split(view)[1])
    print("CSV:  %s" % config.CSV_FILE)
    print("HTML: %s" % config.HTML_FILE)
    print("=" * 60)
    pause()


if __name__ == "__main__":
    main()
