---
name: Lumina Precision
colors:
  surface: '#fcf8fb'
  surface-dim: '#dcd9dc'
  surface-bright: '#fcf8fb'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f6f2f5'
  surface-container: '#f0edf0'
  surface-container-high: '#eae7ea'
  surface-container-highest: '#e5e1e4'
  on-surface: '#1c1b1d'
  on-surface-variant: '#464554'
  inverse-surface: '#313032'
  inverse-on-surface: '#f3f0f2'
  outline: '#767586'
  outline-variant: '#c7c4d7'
  surface-tint: '#494bd6'
  primary: '#4648d4'
  on-primary: '#ffffff'
  primary-container: '#6063ee'
  on-primary-container: '#fffbff'
  inverse-primary: '#c0c1ff'
  secondary: '#006c49'
  on-secondary: '#ffffff'
  secondary-container: '#6cf8bb'
  on-secondary-container: '#00714d'
  tertiary: '#825100'
  on-tertiary: '#ffffff'
  tertiary-container: '#a36700'
  on-tertiary-container: '#fffbff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e1e0ff'
  primary-fixed-dim: '#c0c1ff'
  on-primary-fixed: '#07006c'
  on-primary-fixed-variant: '#2f2ebe'
  secondary-fixed: '#6ffbbe'
  secondary-fixed-dim: '#4edea3'
  on-secondary-fixed: '#002113'
  on-secondary-fixed-variant: '#005236'
  tertiary-fixed: '#ffddb8'
  tertiary-fixed-dim: '#ffb95f'
  on-tertiary-fixed: '#2a1700'
  on-tertiary-fixed-variant: '#653e00'
  background: '#fcf8fb'
  on-background: '#1c1b1d'
  surface-variant: '#e5e1e4'
typography:
  headline-xl:
    fontFamily: Geist
    fontSize: 36px
    fontWeight: '600'
    lineHeight: 44px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Geist
    fontSize: 30px
    fontWeight: '600'
    lineHeight: 38px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '500'
    lineHeight: 32px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Geist
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Geist
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
  label-sm:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
  headline-xl-mobile:
    fontFamily: Geist
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 34px
  headline-lg-mobile:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 30px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 40px
  gutter: 24px
  margin-mobile: 16px
  margin-desktop: 48px
  max-width: 1280px
---

## Brand & Style

The design system shifts from a dark, immersive simulation aesthetic to a high-clarity, professional environment. It targets power users, developers, and analysts who require a focused workspace that minimizes eye strain while maintaining a sense of cutting-edge sophistication.

The style is **Minimalist and Corporate/Modern**, heavily influenced by the high-density, utility-first aesthetics of industry leaders like Linear and Stripe. It prioritizes clarity through generous white space, subtle tonal shifts rather than heavy shadows, and precise typography. The emotional response is one of reliability, precision, and effortless organization.

## Colors

The palette is anchored by a pure `#FFFFFF` background to maximize perceived brightness and cleanliness. 

- **Primary (Indigo):** Used for primary actions, active states, and focus indicators. It provides a sophisticated pop of color against the neutral base.
- **Accents:** Emerald (Success), Amber (Warning), and Rose (Error) are used sparingly for semantic feedback, ensuring the UI remains informative but not overwhelming.
- **Neutrals:** A range of Zinc/Slate grays provides hierarchy. The darkest shade (`#09090B`) is reserved for primary headings to ensure maximum contrast and legibility.
- **Surfaces:** Subsurface elements like sidebars or secondary cards use `#F8F9FA` to create soft structural separation without the need for heavy borders.

## Typography

The design system utilizes **Geist** exclusively to leverage its technical, monospaced-influenced proportions while maintaining excellent legibility. 

- **Headlines:** Use tighter letter spacing and heavier weights to create a strong visual anchor.
- **Body:** Standardized at 16px for optimal reading, using a Zinc-800 color to reduce the "vibration" of pure black on pure white.
- **Labels:** Small labels use an uppercase transform with slight tracking to differentiate metadata from body content.
- **Scale:** The system transitions to smaller headline sizes on mobile to maintain information density without overwhelming the viewport.

## Layout & Spacing

The layout follows a **Fixed Grid** philosophy for desktop to maintain a structured, editorial feel, transitioning to a **Fluid Grid** for mobile devices.

- **Grid:** A 12-column system is used for desktop (1280px max-width). Components should align to these columns to maintain a "structured" look reminiscent of technical documentation.
- **Rhythm:** A 4px baseline grid ensures vertical consistency. All margins and paddings are multiples of 4 or 8.
- **Density:** The system favors a "compact-comfortable" density. Enough padding to breathe, but tight enough to support data-heavy applications.

## Elevation & Depth

This design system eschews traditional shadows in favor of **Tonal Layers** and **Low-Contrast Outlines**.

- **Surface Tiers:** Background is `#FFFFFF`. Cards and containers that need to stand out use a 1px border of `#E4E4E7` (Zinc-200). 
- **Active Elevation:** Only the most critical floating elements (Dropdowns, Modals) receive a shadow. These shadows are ultra-diffused: `0px 10px 15px -3px rgba(0, 0, 0, 0.05)`.
- **Interaction:** Hover states are indicated by shifting the background color to `#F4F4F5` rather than increasing shadow depth. This maintains the "flat" professional aesthetic.

## Shapes

The shape language is defined by a consistent 8px (`0.5rem`) radius for standard UI components.

- **Standard (8px):** Applied to buttons, input fields, and small cards.
- **Large (16px):** Applied to main content containers and modals.
- **Extra Large (24px):** Used for large feature cards or "hero" containers.

This "Rounded" approach balances the technical precision of the Geist typeface with a modern, approachable softness.

## Components

- **Buttons:** Primary buttons use a solid Indigo fill with white text. Secondary buttons use a white background with a Zinc-200 border and Zinc-900 text.
- **Input Fields:** Use a white background, Zinc-200 border, and a subtle inner shadow for a "inset" feel. On focus, the border transitions to Primary Indigo with a 2px outer glow.
- **Chips/Badges:** Use a "soft" color treatment—pale background with high-contrast text (e.g., Emerald-100 background with Emerald-800 text).
- **Cards:** Cards are defined by their 1px Zinc-200 border. No shadow is used for standard cards.
- **Lists:** Use subtle dividers (`1px solid #F1F1F4`) and generous horizontal padding to create a clean, row-based hierarchy.
- **Navigation:** Sidebars should use the `#F8F9FA` surface color to clearly demarcate the navigation zone from the primary workspace.