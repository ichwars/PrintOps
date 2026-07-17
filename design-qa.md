# NumberField Size Adjustment — Design QA

- Source visual truth: `C:\Users\droth\AppData\Local\Temp\codex-clipboard-4ac8226b-e846-45ae-9ad0-6ae94da6ac04.png`
- Implementation screenshot: `C:\Users\droth\Documents\GitHub\PrintOps\docs\design-qa-number-field-after-800.png`
- Viewport: 800 × 600 responsive browser capture; geometry was also measured in the desktop layout.
- State: dark theme, Settings → Orders & Calculation → Calculation, default drying time set to `0`.

## Full-view comparison evidence

The responsive implementation preserves the existing PrintOps card hierarchy, typography,
colors, labels, and two-column field rhythm. The NumberField steppers now have a consistent
40 px logical width throughout the page without changing the shared 38 px desktop control
height. No horizontal overflow was detected.

## Focused region comparison evidence

The reference highlighted an oversized and vertically displaced stepper beside
`Standard-Trocknungszeit h`. Before the fix, browser geometry measured the input at
37.99 px high and the stepper at 39.60 px high, with the stepper starting 2.60 px above
the input. After the fix, the input and parent both measure 37.99 px high. The stepper is
inset by 1 px on both edges and measures 36.01 px high, so it follows the input border
exactly. Its logical width is 40 px and both icons are 14 px.

## Required fidelity surfaces

- Fonts and typography: unchanged; the existing PrintOps font sizes, weights, and label hierarchy match the surrounding controls.
- Spacing and layout rhythm: passed; the input-only top margin and conflicting 40 px height were removed, eliminating the offset.
- Colors and visual tokens: unchanged; borders, backgrounds, hover colors, and disabled opacity continue to use the shared tokens.
- Image quality and asset fidelity: not applicable; the control contains only Lucide interface icons and no raster or brand imagery.
- Copy and content: unchanged; labels and values remain identical to the reference state.

## Findings

No actionable P0, P1, or P2 differences remain for the requested NumberField sizing.

## Comparison history

1. P2 — Stepper exceeded and vertically drifted from the input due to the legacy `mt-1 h-10` consumer classes. Fixed by using the shared control height without an input-only offset.
2. P2 — Stepper affordance was too narrow and its arrows were difficult to read. Fixed by standardizing the width at 40 px and increasing the icons from 12 px to 14 px.
3. Post-fix evidence — automated component tests pass, measured geometry follows the input border, and the responsive capture shows consistent controls without overflow.

## Implementation checklist

- [x] Remove conflicting calculation-only height and top margin.
- [x] Standardize the shared stepper width.
- [x] Increase arrow readability.
- [x] Verify interaction tests, lint, build, geometry, and responsive overflow.

## Follow-up polish

None required for this focused adjustment.

final result: passed
