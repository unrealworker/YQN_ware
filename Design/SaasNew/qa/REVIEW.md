# SaasNew migration QA

Checked on 2026-10-27. This review covers the DOM-to-editable-node converter and a read-only check of the generated migration. It does not certify the final Figma document.

## Converter validation

Run:

```powershell
node Design/SaasNew/dom-to-pen.cjs
node Design/SaasNew/qa/check-text-geometry.cjs
```

Latest snapshot set: 38 files, 8,021 editable nodes, 2,036 text nodes. No missing/duplicated DOM text, duplicate IDs, invalid geometry, unsupported importer properties, missing image files, lost SVGs, or missing action targets. The 26 warnings are empty auxiliary DOM boxes with no content.

Single-line text fix is included in `dom-to-pen.cjs`: 1,970 single-line DOM runs and 13 input values use Figma automatic width, preventing an unwanted extra line caused by font metric differences. The 12 actual multi-line runs retain their original fixed geometry. Numeric original glyph bounds have at least four pixels of right-side clearance from clipping ancestors. Final Figma font metrics should still be inspected. Fonts are Microsoft YaHei for text containing non-ASCII characters and Arial for ASCII text.

Example:

```js
const { convert } = require('./dom-to-pen.cjs');
const { root, actions, warnings } = convert(snapshot, 'b31-actual', {
  x: 1440, y: 64, width: 480, height: 1016
});
```

## Migration findings sent to parent

- At the initial 23-board migration audit, each updated board had one current navigation strip and one current sidebar. Effective reference geometry removal worked; no duplicate legacy sidebar remained.
- Scene image replacement retained legacy children named `replay_poi_overlay` on boards 5, 47, 48, 49, 50, 51, and 53. Board 47 showed forklift 03 returning while the new sidebar and clean scene image represented loaded forklift 02. This is an old overlay, not text burned into the scene bitmap. Parent owns this correction.
- Board 47 originally paired the 640-second loaded scene with a 230-second timeline. Matching replay transport snapshots are now available for parent to integrate.
- Main POI on board 31 and legacy inventory POIs on board 11 used old camera anchor coordinates. Their tips pointed outside their intended objects after replacing the scene image. Parent owns camera/anchor synchronization.
- Board 50's new exit dialog correctly follows the production CEF geometry: a 480-by-1016 sidebar iframe at x=1440, y=64, containing a 390-by-243 card at local x=45, y=386.5. The previous full-page centered modal was stale.

## Preview evidence and limits

`board-31.png`, `board-11.png`, `board-47.png`, and `board-50.png` were captured with the temporary renderer before the single-line fix. They identify the original wrap issue and scene-overlay mismatches; they are not final acceptance images. The renderer only approximates the old auto-layout and icon nodes, so its old-icon squares are not evidence of a Figma import defect. Browser QA task space 12 has been finished and closed.

Main migration scripts, migration JSON, importer, and production UI were not modified by this QA pass. Parent handles final rebuild, Figma visual acceptance, and Git commit.
