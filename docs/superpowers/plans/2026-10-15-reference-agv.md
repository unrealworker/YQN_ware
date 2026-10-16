# Reference AGV Modeling and UE Import

**Goal:** Recreate the supplied warehouse robot in Blender and import a reusable Actor into the existing UE logistics scene.
**Authorization:** User approved direct modeling from photograph proportions with nominal 1.6 m chassis length; no surveyed dimensions available.
**Method:** Editable hard-surface Blender geometry, separate component collections, FBX export, UE material reconstruction and Blueprint Actor.
**Constraints:** Front is Blender -X, Z is up. Approximate body width .9 m and overall height 1.11 m. Hidden faces are inferred; small unreadable labels are not claimed as exact. Preserve existing warehouse objects.

- [x] Model rounded dark chassis, wheel cutouts, yellow perimeter bumper, floating deck and control cabinet.
- [x] Model detailed rubber tires, metal rims, camera/IR sensor and red beacon in parallel modules.
- [x] Assemble editable .blend and compare a rendered three-quarter view against the reference; refine silhouette and detail.
- [x] Export FBX with material manifest, import /Game/AGV_Reference, compile BP_AGV_Reference and place AGV_01_Reference in LogisticsWarehouse.
- [x] Verify saved assets in a fresh UE process, capture a UE close-up and document dimensions and scope.

Verification checks real artifacts: rendered silhouette and materials, meter-to-centimeter scale, ground contact, saved material slots, Blueprint default mesh, one placed Actor, and successful Blueprint compilation. Visual source construction does not need implementation-mirroring unit tests.

Completed: 566 editable source parts, 181517 exported triangles, 20 material slots. Fresh-process verification passed; project Blueprint compilation completed with 0 errors, 0 warnings and 0 load failures. The two UE screenshots in Saved/AGV_UE_Closeup.png and Saved/AGV_UE_Context.png were inspected. Capture report confirms removal of the temporary camera and successful map save. Overall bounds are 1.640 x 0.956 x 1.101 m at scale 1.
