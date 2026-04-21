# Lightcore Prism Design Notes

Reference image:

- `lightcore-prism-ui-reference.jpg`

## Visual Direction

- Overall tone: bright, white-first interface with subtle prism gradients.
- Mood: clean, premium, airy, and product-system oriented.
- Contrast: soft surfaces with restrained black text and selective iridescent accents.

## Layout Principles

- Use a design-system board layout with clear horizontal sections.
- Group tokens, controls, navigation, components, web page, and mobile app examples as separate zones.
- Keep the interface sparse and precise, with strong alignment and minimal decoration.
- Favor generous whitespace and compact component examples over dense dashboard composition.

## Color Language

- Base background: white and near-white.
- Surface layers: soft gray panels and low-contrast borders.
- Accent colors: prism gradients moving through warm yellow, cyan, blue, violet, and pink.
- Primary text: near-black.
- Secondary text: cool gray.

## Component Language

- Buttons: low-height pills with subtle borders and faint prism glow on primary actions.
- Navigation: thin desktop bar and compact mobile header examples.
- Icons: light outline icons with generous spacing.
- Controls: clean search fields, toggles, progress bars, tabs, and small status labels.
- Data displays: donut chart, light line chart, and compact mobile finance card.

## Possible Use In This Project

- Use as a future light-mode reference if the dashboard needs daytime monitoring.
- Borrow the tight component spacing for controls, filters, tabs, and input states.
- Reuse the prism accent sparingly for secondary highlights, not as the main dashboard palette.
- Keep the current production dashboard dark-first unless a separate light theme is explicitly introduced.

## What To Avoid

- Mixing this bright prism language directly into the current Cosmic Gravity dark theme.
- Using the full rainbow gradient as a dominant dashboard background.
- Reducing data density too much for the trading monitor workflow.
- Turning operational status cards into marketing-style product cards.
