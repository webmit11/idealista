# Yendari — Design Brief: International Web Storefront

> Self-contained brief. This Claude Code session starts cold — everything needed is here.
> Use the `ui-ux-pro-max` skill. UI copy and deliverables in **English**.

## 1. Product
Yendari (yendari.com) is a curated real-estate finder for **investment + living** across **Southern Europe** — starting with Portugal (**Porto, Lisbon**) and expanding to **Spain, Italy** and more — aimed at **international buyers**. It already has a Telegram Mini App (Russian audience) and an owner web dashboard, built on FastAPI + SQLModel + PostgreSQL + Jinja2 templates. This brief is for a **NEW public, English-first web storefront** — the international acquisition surface — reusing the existing data engine.

## 2. Goal
A premium, trustworthy, **data-forward** public website that converts international investors and relocators (UK, Israel, Gulf, expats) into **leads**. It must feel like a real, professional site worthy of a €200k–500k decision: discoverable (SEO), no install, instant trust. Distinct from the Telegram app.

## 3. Audience
- **Investors** — yield/ROI focused.
- **Relocators** — living/lifestyle focused.
English is the lingua franca. Buyers are cautious and high-value; clarity and credibility beat flashiness.

## 4. Markets & i18n
**Multi-country from the start — the design MUST scale across countries.** Portugal (Porto, Lisbon) now; Spain, Italy and more next. Needs a **country → city selector**. Currency **EUR** (PT/ES/IT all use it). Languages: **EN (primary), PT, ES, IT, RU** → language switcher. (Idealista covers PT/ES/IT, so the same data pipeline extends across markets.)

## 5. Brand & visual direction — SLEEK MODERN + trustworthy (KEY REQUIREMENT)
- Name: **Yendari** (yendari.com). **No logo yet — design a wordmark + mark** as part of this work: modern, country-agnostic, a European property-intelligence brand. (The old dark "Domus" mark belongs to the Telegram product and is NOT the storefront brand.)
- Required feel: **sleek, modern, high-polish** — the craft level of **Linear / Stripe / Vercel / Arc**, but **image-forward** for real estate. NOT editorial/serif/"traditional" — an earlier serif+paper direction read as old; drop it. Trust comes from **polish + real data + real photos**, not from looking classic. A refined **dark** theme is welcome (reads very modern); also offer a clean light variant.

**Modern touches to USE (they build trust):**
- Generous negative space, tight precise grid, strong hierarchy — crisp and confident (not editorial/literary).
- Real, high-quality photography — a Porto/Lisbon hero image + real cached listing photos.
- Purposeful micro-interactions: smooth card hovers, gentle on-scroll reveals, animated stat counters — all subtle, and respect `prefers-reduced-motion`.
- Subtle depth/layering (soft shadows), restrained rounded corners, consistent spacing tokens.
- Sticky nav that condenses on scroll; light/airy default with one confident accent; optional dark-mode toggle.
- Data shown as the hero: score badges, yield, "below market" chips, small charts — the data IS the trust signal.
- **Type**: a distinctive modern grotesk (e.g. Geist, General Sans, Satoshi — NOT default Inter, NOT a serif display) + **monospace for numbers/data** (price, yield, score) for a fintech/trading-desk feel.
- Tasteful **bento-grid** for the "Why Yendari" section.

**Trust signals to include:**
- Real numbers up front (listings count, avg yield, refresh cadence).
- Social proof: testimonials, "licensed local agents", partner/agency logos, "AI-analysed".
- Transparency: a short "how we score" methodology, real photos, "updated every X days".
- Legitimacy cues: privacy note on forms (GDPR-friendly), company/contact in footer, HTTPS. No fake urgency, no dark patterns.

**Avoid (modern but trust-killing):** all-over glassmorphism, neon gradients, heavy parallax, autoplay video with sound, gimmicky cursors, intrusive popups.

- Deliver a **real rendered page**, not swatches (you can't judge "sleek" from a palette): build the actual hero + top-deals + lead form in HTML/CSS, using **real listing photos from `https://aicraftpin.com/img/{id}`** and a real Porto/Lisbon hero image. Propose a **dark** and a **light** variant of one sleek-modern direction. Tasteful modern effects only (subtle gradient/glow on CTAs, hairline borders, soft grain, glassy condensed nav, spring micro-interactions, sparkline charts) — restrained, `prefers-reduced-motion` aware.

## 5b. Anti-generic — must NOT look like an AI-templated site (KEY)
A generic "AI website" look actively *hurts* trust (reads as low-effort / fly-by-night). Deliberately avoid the tells and build a crafted, ownable identity.

**Tells to AVOID (the "AI slop" look):**
- Default Inter/generic sans everywhere; centered headline + subtitle + two buttons (primary + ghost) hero; aurora / gradient-blob backgrounds; purple-blue startup gradient palette.
- Untouched shadcn/ui defaults; a uniform three-column feature grid with generic line icons; symmetric, everything-centered layout; stock photos or no photos; vague copy ("Empower / Seamless / The future of…").

**How to look crafted & real instead:**
- **Distinctive typography** — a characterful modern grotesk (+ mono for data), not default Inter and not a serif display. Type carries the brand.
- **Editorial, slightly asymmetric layout** — a strong grid with intentional off-center compositions and deliberate overlaps; break the centered-everything pattern.
- **An ownable palette** — not purple/blue startup gradients. Pick a confident, **country-agnostic** premium palette (the brand must work across Portugal, Spain, Italy — no single-country folk colors as the core).
- **Real photography** — actual Porto/Lisbon scenes (hero) + real cached listing photos. Real imagery instantly de-genericizes.
- **Concrete, specific copy** — real numbers and real local area names per market (e.g. Bonfim · Porto, Chiado · Lisbon, Malasaña · Madrid); specificity reads as credible and non-templated.
- **A signature element** — make the deal-score badge / "below market" chip a recognizable visual motif; custom data viz; a real map.
- **Sense of place (optional, per market)** — a light, swappable local cue (a city skyline/landmark photo per market) rather than one fixed folk motif; the core brand stays country-agnostic and scalable.
- Restraint over trends: craft, real content, and tuned details beat effects.

## 6. Structure (v1 = landing page)
1. **Hero** — value prop + search (location / budget / typology) + trust stats.
2. **Top deals** — grid of scored listing cards.
3. **Why Yendari** — AI deal score, ROI simulator, short-let (AL) income, neighbourhood scoring.
4. **Lead capture** — email + WhatsApp, low friction.
5. **Footer** — brand, languages, legal links.

Later pages (design system should anticipate): listings list, listing detail, areas/neighbourhoods, how-it-works, SEO insight articles.

## 7. Data the engine provides (design around this — it's the differentiator)
Per listing: price (EUR), typology (T0–T4), area m², parish + municipality, nearest metro + distance & walk-minutes, **deal score 0–100** (badge), **gross yield %**, **price-per-m² vs local median** (e.g. "24% below market"), price-drop / price-up markers, **AL short-let licence** flag + short-let income, ROI inputs, and **cached non-expiring photos** (served at `/img/{id}` and `/img/{id}/{n}`). Site meta: 1,000+ curated listings, average yield, refresh cadence.

## 8. Components to design (consistent visual language)
- **Listing card**: photo, score badge, price, yield %, facts (typology · m² · area), metro line, market-delta chip, AL badge.
- Hero search controls (Country → City → Budget). **No invest/live toggle in the hero** — every listing is scored as both an investment and a place to live, so the search must not split the two.
- Trust stat strip (metric tiles).
- **Lead form**: email + WhatsApp (phone dial-code is pre-filled from the visitor's IP) + **purchase intent (Invest · Live in · Both)** — captured here for agent qualification, not as a search filter.
- Value-prop blocks (icon + title + line).
- City selector, language switcher.
- A reusable way to express **score / yield / market-delta / AL**.

## 9. Monetization context (drives the CTAs)
- **Primary**: lead-gen → referral to local licensed agents. CTAs: "Get your free shortlist", "Talk to an advisor", "Book a viewing".
- **Secondary (later, Stripe)**: paid investment report (€79–149) and paid analysis of other regions.
- Lead form captures **budget, timeline, and purchase intent (Invest · Live in · Both)**. Intent is collected in the lead form for **agent qualification**, NOT as a hero search filter.
- **Brand message — "both":** every Yendari listing is scored *simultaneously* as an investment (yield, market-delta, AL income) and as a place to live (metro, condition, neighbourhood). Pure-invest services ignore livability; portals ignore yield — Yendari does both, and the UI must never force buyers to choose invest-or-live.

## 10. Tech / implementation constraints
- Built in this repo (branch `feature/international-web`), served by **FastAPI + Jinja2 + static CSS**. No heavy SPA needed — semantic server-rendered HTML + light vanilla JS is preferred (SEO + speed).
- The public surface must **NOT** require Telegram auth (the Mini App uses Telegram initData; this storefront is open browsing + a lead form). Assume a new public data path mirroring the existing API.
- Use **CSS variables** for theming (supports the light/dark direction + future PT/RU).
- **Mobile-first & responsive** (many buyers on phones). **Accessibility WCAG AA**: contrast ≥ 4.5:1, visible focus states, touch targets ≥ 44×44px.
- Real listing images load from `/img/{id}`; design a tasteful placeholder for the few without photos.

## 11. Deliverables
1. **Design system** (via `--design-system`): style, color palette, typography, spacing/tokens, component specs — as CSS variables.
2. **High-fidelity, responsive HTML/CSS** for the landing (hero → deals → why → lead capture → footer).
3. **Listing card** component (the reusable hero of the site).
4. Pass a **UI audit** (accessibility, contrast, spacing, touch targets, no emoji as structural icons).

## 12. Out of scope for design
Backend, scraping, payments wiring, and the data-source legal question are operational — not part of this design task.

## 13. First task
Run `ui-ux-pro-max --design-system` for this brief, then **build a real rendered landing page** (hero + top-deals + lead form + footer) plus the reusable **listing card** and a **Yendari wordmark/logo**, in the **sleek-modern** direction — **dark as primary, plus a light variant** — using **real photos from `https://aicraftpin.com/img/{id}`** (e.g. `/img/3578`, gallery `/img/3578/1`). Deliver an actual page, not color swatches. Commit on `feature/international-web`. Start by showing the hero + 3 listing cards as one rendered page, then iterate.
