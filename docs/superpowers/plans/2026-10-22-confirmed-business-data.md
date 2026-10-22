# GHS confirmed inventory and equipment implementation plan

> **For agentic workers:** Use subagent-driven-development for independent UI/design work and verification-before-completion before committing.

**Goal:** Apply confirmed facts in the answered 库存与设备数据对接问题表.xlsx to the current design and UE embedded business pages; retain original unverified design/data with explicit 数据未核验 labels per the user's follow-up.

**Architecture:** A versioned, immutable browser/Node module owns the verified extract. Scene equipment remains a separate dataset with its existing IDs and interactions. The web panel consumes the extract without network access or invented model bindings.

**Tech Stack:** UE 5.4, embedded Chromium, plain JavaScript/CSS, Node test runner, Pencil.

**Spec:** The workbook answers at 库存对接!E7:F17, 设备对接!E7:F17 and 接口与更新!E7:F15.

## Constraints and review focus

- GHS system warehouse 108 / GHS_CA_US only; BCF/BCT physical scope remains unconfirmed.
- This is a dated verified extract, not a production feed or a single business snapshot. Preserve distinct query/source/ETL timestamps with explicit UTC+08:00.
- Inventory quantity unit, capacity, real empty/locked slots and mappings remain unknown. The original capacity pie/chart/matrix remains a separately labeled unverified example; never use it or scene pallets as verified business evidence.
- Ledger normal/repair/disabled are management states; unknown telemetry stays null, never online, normal or zero by default.
- Five provided samples are not complete inventories; search/filter counts must not impersonate full warehouse counts. Scene IDs and registry IDs cannot cross-bind.

## Tasks

- [x] Add `Content/GHSTwinUI/web/business-data.js` as the single source for confirmed facts, source-cell provenance, nulls and enums. Test reconciliation, negative quantities, unknown statuses and sample completeness in `tests/business-data.test.js`.
- [x] Update `app.js`, `style.css`, `index.html` and relevant tests: inventory/current aggregate, partial samples and independently labeled original unverified capacity charts/matrix; registry default plus separate scene browsing; consistent overview; no fake registry focus calls or cross-source sample search.
- [x] Update existing Pencil components/artboards and overwrite current exports/manifest, retaining address/clock/POI styling. Record confirmed vs pending decisions in the current design brief.
- [x] Run all Node tests, actual UE embedded browser page/interaction checks and visual screenshots. Verify staging includes the new web module. Run fresh independent review and resolve findings.
- [x] Update implementation documentation and commit only task-owned files to master with a Chinese message. Preserve pre-existing user changes and scene assets.

Verification on 2026-10-23: 79 Node tests and 9 real UE checks passed; 6 captures cover 2560×1600 and 390×844. Scene assets were not saved and the warehouse map hash stayed unchanged. No C++ changes or packaging were required for the embedded web source update.
