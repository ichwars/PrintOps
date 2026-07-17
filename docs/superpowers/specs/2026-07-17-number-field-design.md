# Unified NumberField Design

**Date:** 2026-07-17  
**Status:** Approved design  
**Selected visual:** Variant A — integrated vertical steppers

## Context

PrintOps currently uses native `input[type="number"]` controls. Their spinner buttons are rendered by the browser and therefore differ from the shared PrintOps controls in color, size, hover behavior, and platform appearance. The application already owns shared primitives for text, selection, date, checkbox, switch, modal, tabs, buttons, and scroll areas. Numeric entry is the remaining common form primitive without a dedicated component.

## Goals

- Add one reusable `NumberField` primitive with PrintOps styling.
- Replace native number spinners with integrated vertical increment and decrement buttons.
- Preserve existing values, callbacks, validation constraints, payloads, and form behavior.
- Migrate every real numeric input in the frontend to the shared component.
- Provide consistent mouse, touch, keyboard, disabled, read-only, light, and dark behavior.
- Keep the component compatible with compact settings grids and mobile layouts.

## Non-Goals

- Do not replace range sliders, color fields, file fields, chart configuration such as Recharts `XAxis type="number"`, or non-input domain controls.
- Do not introduce locale-aware thousands separators or formatted currency display inside the editable field.
- Do not change numeric storage types, API payloads, validation rules, defaults, or save timing.
- Do not add press-and-hold acceleration in this phase.

## Approaches Considered

### A. Integrated vertical steppers — selected

Place two compact arrow buttons inside a right-hand segment of the field. This preserves current field width and density while replacing platform-specific browser chrome with the PrintOps visual language.

### B. External minus and plus buttons

This offers larger touch targets and very explicit behavior, but materially increases width and would disrupt existing multi-column forms.

### C. Integrated horizontal minus and plus segment

This is more touch-friendly than vertical steppers but consumes more horizontal space inside the value area. It is less suitable for the dense settings layouts selected for PrintOps.

## Component Boundary

Create `frontend/src/components/ui/NumberField.tsx` and export it from `frontend/src/components/ui/index.ts`.

The component owns:

- the native numeric input and removal of browser spinner chrome;
- the integrated increment and decrement buttons;
- numeric stepping, clamping, and floating-point normalization;
- shared field label, helper text, error text, and accessibility wiring;
- visual states for focus, hover, disabled, read-only, invalid, light, and dark themes.

Consumers continue to own:

- conversion to domain-specific numbers where required;
- application validation beyond `min`, `max`, and `step`;
- persistence, mutation calls, toasts, and save timing;
- units and domain-specific labels.

## Public Interface

`NumberField` follows the existing `TextField` conventions:

```ts
export type NumberFieldProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'type' | 'value' | 'onChange' | 'size'
> & {
  value?: string | number;
  onValueChange?: (value: string) => void;
  onChange?: ChangeEventHandler<HTMLInputElement>;
  label?: ReactNode;
  helperText?: ReactNode;
  error?: ReactNode;
  incrementLabel?: string;
  decrementLabel?: string;
};
```

At least one change callback is expected for editable fields. Read-only display remains valid without a callback. Both callback styles are supported so existing migrations do not need to change payload construction.

## Value and Step Behavior

- The editable input remains `type="number"`; browser spinner pseudo-elements are hidden with component-owned CSS.
- Direct typing emits the raw input string without early domain conversion.
- The step buttons use the platform's numeric step semantics as the behavioral baseline, including `step="any"` handling.
- `step` defaults to `1` when omitted.
- Increment and decrement clamp to `min` and `max` when supplied.
- An empty value starts from `min` when incrementing if a minimum exists; otherwise it starts from `0`. Decrementing an empty value starts from `max` when a maximum exists; otherwise it starts from `0` and then applies the decrement step.
- Decimal results are normalized to the precision implied by `step`, avoiding visible floating-point artifacts such as `0.30000000000000004`.
- Invalid free-form text is still governed by the native number input; the component does not silently coerce it on render.
- The step controls never emit a value on mount.

## Interaction and Accessibility

- Arrow Up and Arrow Down retain native numeric input behavior.
- Each stepper is a `button type="button"` and therefore never submits the surrounding form.
- Buttons receive accessible labels derived from `incrementLabel` and `decrementLabel`, with shared translated defaults.
- The buttons are disabled when the field is disabled or read-only, and at their respective numeric boundary.
- Focus remains on the input after pointer activation so repeated keyboard editing remains possible.
- The input is connected to `FormField` labels, helper text, required state, and errors exactly like `TextField`.
- Focus-visible treatment uses the active PrintOps accent color.
- The combined field reaches the existing mobile minimum height; the right segment widens slightly on touch layouts without changing desktop density.

## Visual Design

- Field height and border radius match the shared `TextField`.
- A 34-pixel desktop segment sits on the right and is divided into equal upper and lower buttons.
- A subtle left divider separates value entry from the step controls; a second divider separates the two arrows.
- Chevrons use the existing icon set and inherit neutral foreground colors.
- Hover and active states use restrained accent-color backgrounds; disabled and read-only states use the existing shared opacity treatment.
- The native WebKit and Firefox spinner controls are hidden only inside `NumberField`, not globally.

## Migration Scope

Migration proceeds in two source-auditable groups:

1. Replace every `TextField type="number"` with `NumberField`, preserving all props and callback behavior.
2. Replace remaining native JSX `input type="number"` elements across pages, dialogs, printer workflows, inventory, settings, and order calculation surfaces.

Explicit exclusions are chart-library props, range sliders, and source text that is not a rendered input. Completion requires a scoped source audit showing no remaining rendered `input[type="number"]` outside `NumberField`.

## Testing Strategy

Add focused component tests before implementation for:

- increment and decrement with the default step;
- decimal steps without floating-point artifacts;
- minimum and maximum clamping and boundary-disabled buttons;
- empty-value stepping rules;
- direct input callback compatibility;
- Arrow Up and Arrow Down behavior;
- disabled and read-only states;
- accessible labels and non-submitting step buttons;
- focus retention after clicking a stepper;
- no callback on mount.

Update affected integration tests only where they currently depend on native number-spinner implementation details. Preserve all existing payload assertions. Run the full frontend test suite, i18n parity check, lint, production build, source audit, and browser QA at desktop and mobile widths.

## Browser QA Flow

The primary rendered flow is:

`Settings → Device Management → printer cost field → increment/decrement and direct typing → unchanged saved value payload`.

Also sample numeric fields from inventory, printer workflows, and order calculation. Validate light and dark themes, keyboard stepping, pointer stepping, mobile layout, no clipping, no framework overlay, and no relevant console errors.

## Risks and Mitigations

- **Floating-point drift:** normalize results to step precision and test decimal sequences.
- **Payload regressions:** keep string callbacks at the primitive boundary and retain existing integration payload assertions.
- **Form submission from steppers:** enforce `type="button"` and test inside a form.
- **Broad migration risk:** migrate in bounded groups with focused tests and a final source audit.
- **Inconsistent accessible naming:** provide translated defaults and allow explicit labels for domain-specific wording.
