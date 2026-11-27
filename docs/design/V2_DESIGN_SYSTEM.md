# Find-IT v2.0.0 — Design system guide (for the 3 front-end developers)

Everything is in `static/css/v2.css` (loaded after `app.css` and `campus-bg.css` in `base.html`).
You get the sidebar, top bar, footer and monument background automatically by extending
`core/base.html`. Do **not** change form field names, `id`s, `data-…` attributes, `{% csrf_token %}`
or `method="post"` (v2 doc rule).

## Page skeleton
```django
{% extends "core/base.html" %}
{% block title %}My page · Find-IT{% endblock %}
{% block content %}
<section class="page-wrap">
  <a class="back-link" href="…">{% include "core/includes/icon.html" with name="arrow-left" %}Back</a>
  <div class="page-heading"><div><span class="eyebrow">Small label</span><h1>Title</h1><p class="muted">One line.</p></div>
    <div class="button-row"><a class="button button-primary" href="…">Main action</a></div></div>
  <section class="panel">…</section>
</section>
{% endblock %}
```
Narrow forms: `narrow-page` instead of `page-wrap`. Public sign-in style pages: `auth-shell` (see `login.html`).
Optional blocks: `bg_variant` (`campus-bg--app` light / `campus-bg--hero` dark), `body_class`.

## Parts
| Need | Class / include |
| --- | --- |
| Icon | `{% include "core/includes/icon.html" with name="search" %}` — names listed at the top of the file |
| Buttons | `button` + `button-primary` / `button-soft` / `button-outline` / `button-danger` / `button-light` (on dark) / `button-ghost-light` (on dark); `button-small`, `button-full` |
| Card | `panel` |
| Small label | `eyebrow` (mono, uppercase) |
| Accent words | `<span class="accent">reconnect.</span>` (serif italic) |
| Post type | `type-pill type-lost` / `type-found` |
| Item status | `status-pill status-{{ post.status|lower }}` (open, claim_in_progress, turned_over, returned, claimed, closed) |
| Claim status | `status-pill status-{{ claim.status|lower }}` (submitted, approved, declined, completed…) |
| Report status | `{% include "core/includes/report_status.html" %}` |
| Category / plain chip | `subtle-chip` |
| Number tiles | `staff-stats stat-grid-4/5/6` + `stat-card` (+ `is-hero`, `stat-amber`, `stat-green`, `stat-review`, `stat-danger`, `stat-neutral`, `accent-bar`) |
| Icon tiles | `metric-grid` + `metric` + `metric-icon` (dashboard) |
| Shortcut cards | `quick-links` + `quick-link` |
| Two cards side by side | `split-panels` |
| List rows | `queue-row`, `staff-row`, `audit-row` |
| Info box | `form-callout`, `warning-callout`, `guardhouse-callout`, `notice-banner` |
| Empty state | `empty-state` + `empty-icon` |
| Tabs | `segmented` with `is-active` link |
| Post card | `{% include "core/includes/post_card.html" %}` |
| "Are you sure?" | add `data-confirm="Title?" data-confirm-text="Explain" data-confirm-ok="Button text"` to a submit button |

## Colours (CSS variables)
`--forest` #0b2a23 (sidebar), `--emerald` #24574a (main buttons), `--sage` #9fc2b0, `--sage-pale`,
`--canvas-2` (page), `--paper-2` (cards), `--ink-2` (text), `--muted-2`, `--danger`, `--amber`,
`--lavender` (guard house), `--slate`, `--sky`. Old v1 names (`--navy`, `--teal`…) now point to these.

## Sizes
Use rem, %, clamp() and vw — no fixed px except 1px lines (owner's rule). Breakpoints: 64em (sidebar
becomes a slide-in menu), 48em (phone), 30em (small phone).
