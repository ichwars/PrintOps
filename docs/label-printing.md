# Printing labels on a partially used sheet

Open **Print labels** from the filament inventory or material inventory and
select the items to print. Each Avery format has its own **Start position**:

- Avery L7160: positions 1–21 on A4, three columns and seven rows.
- Avery 5160: positions 1–30 on US Letter, three columns and ten rows.

Positions run left to right, then continue on the next row. For example,
position 4 is the left label in the second row. Positions before the chosen
start remain blank. The offset applies only to the first sheet; every later
sheet starts at position 1. The order of selected items and the colour-sort
option determine the order in the PDF.

Choose the matching Avery button to open the generated PDF. Print at actual
size (100%) on the matching paper format. Single-label AMS-holder and box
formats continue to start at position 1. A blank, fractional or out-of-range
sheet position disables its print button and displays a correction hint.
Opening the dialog again resets both sheet positions to 1.

Large selections scroll independently; the remaining options can also scroll
on short screens, while Close and Cancel remain available. A failed generation
retains the selection and start position for retry.

The local spool, Spoolman and material-label endpoints accept the optional
integer `start_position`, defaulting to 1. The maximum depends on `template`;
single-label formats reject values other than 1. Invalid positions return HTTP
422 before inventory data is loaded. Existing permissions still apply.

Transparent and multicolour swatches affect only the swatch itself. QR codes
retain opaque black modules and a white background on every label format.
