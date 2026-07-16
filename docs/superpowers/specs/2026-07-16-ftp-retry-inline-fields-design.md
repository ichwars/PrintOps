# FTP Retry Inline Fields Design

## Goal

Place the three FTP retry selection fields in one visually balanced row without changing their behavior or making the card feel crowded.

## Layout

- Replace the vertical settings stack with a responsive grid.
- Use three equal-width columns from the medium breakpoint upward.
- Keep the fields stacked in one column on narrow mobile viewports.
- Each label, select, and chevron stays inside its own grid cell.
- Select controls fill the available cell width instead of using the current fixed width.
- Preserve the existing spacing, dark surfaces, borders, radii, typography, focus color, and control height.
- Keep the weak-WLAN helper text directly below the connection-timeout select inside the third grid cell.

## Behavior

- No setting keys, values, options, update handlers, translations, or persistence behavior change.
- The retry-enabled switch continues to show and hide the complete field grid.
- Keyboard, focus, and native select behavior remain unchanged.

## Responsive Acceptance Criteria

- At desktop and tablet widths, retry attempts, retry delay, and connection timeout appear side by side with equal widths and aligned tops.
- At narrow mobile widths, the fields stack without horizontal overflow or clipped labels.
- The helper text does not affect alignment of the select controls above it.

## Verification

- Add a focused SettingsPage assertion for the responsive three-column grid and full-width select wrappers.
- Run the focused SettingsPage tests, ESLint, and the production build.
- Verify the live desktop and mobile layouts in a real browser.
