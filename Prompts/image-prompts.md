# AI Image Prompts — README Banners

Three banner images for this kit's `README.md` / `README.tr-TR.md`.
Generate with any capable image model (Nano Banana Pro, Midjourney v7,
Flux, GPT-Image, etc.) at a **wide 16:9 banner aspect ratio**, save as
PNG under `docs/images/` (`overview.png`, `core-features.png`,
`design-philosophy.png` — shrink oversized model output first with
`tools/resize-images.bat`). The `README.md`/`README.tr-TR.md` image tags
ship **uncommented** — the pictures appear as soon as the files land.

This file is **self-contained** — there is no shared base prompt to
inherit from. This kit owns a completely distinct visual world.

## Art direction — "The Guardian of Code" (a 3-act story, not a static mascot)

CodeIntel is personified as a towering guardian whose entire body is
woven from living, luminous code — not a robot, not a cute character,
a powerful elemental force made of light and syntax. The three banners
are one continuous story, told across the README:

1. **The Chase** — scattered, fleeing fragments of code (dim, rust-amber,
   scrambling like startled sparks through a vast dark digital void)
   are run down and seized by the Guardian's outstretched hand — nothing
   escapes it. (This *is* hybrid search: nothing hides from it.)
2. **The Forge Within** — inside the Guardian's own luminous chest-core,
   the captured fragments are held, cross-referenced, compared,
   annotated — worked on, not just stored. (This *is* deep research,
   the comparison table, the symbol graph, the manual generator.)
3. **The Release** — the Guardian opens its hand and sends the same
   fragments back out, transformed: no longer small and scattered, but
   large, solid, brilliant, complete. (This *is* the enriched answer,
   explanation, or documentation coming back to the developer.)

- **World:** a vast, dark digital void (not a screen, not outer space —
  a bottomless dark expanse implying limitless codebase scale). The
  Guardian's body is built from flowing ribbons of glowing script-like
  circuitry, dense at the core and trailing into fine luminous threads
  at the extremities — powerful and elemental, not humanoid-mascot cute.
- **Palette:** near-black void (base), brilliant electric cyan-white
  (the Guardian, and anything it has already touched/transformed),
  dim rust-amber (fleeing/uncaught, unprocessed code, before capture) —
  the cyan-vs-amber contrast *is* the before/after of the whole story.
- **Style:** epic cinematic digital-painting, dramatic rim lighting,
  strong sense of scale and motion, particle/light-trail detail.
- **Consistency:** all three images share this exact Guardian, world,
  and palette; each is a different beat of the same story, a different
  shot type and camera angle.

## Negative Prompt (paste into every generation)

```
text, letters, readable words, logos, watermark, low quality, blurry,
cute, chibi, cartoon mascot, toy-like, humans, real robots, screens,
monitors, keyboards, office setting, different art style between images
```

## Image 1 — Overview / The Chase (`docs/images/overview.png`)

**Slot:** top of the README, under the title/badges.
**Shot:** wide dynamic action shot, diagonal composition, strong motion
blur on the fleeing fragments — establishes the whole world and story.

**Prompt:**
```
Epic cinematic digital painting. In a vast, bottomless dark digital
void, a swarm of small, dim, rust-amber code-fragments — jagged
splinters of glowing syntax, like startled sparks — are scrambling and
scattering in every direction as if trying to flee. From the edge of
frame, an enormous, powerful Guardian made entirely of flowing,
brilliant electric cyan-white circuitry and living code-ribbons reaches
in with one massive glowing hand, closing its grip around a cluster of
the fleeing fragments mid-flight. The fragments already caught in its
hand are transforming, glowing brighter, shifting from dim rust-amber to
brilliant cyan. Many more fragments still scatter and flee in the
distance, but none of them will get away. Strong diagonal composition,
dramatic motion blur on the fleeing fragments, powerful rim lighting on
the Guardian's hand and arm, near-black void background, particle and
light-trail detail. No text, no readable words, not cute or cartoonish —
epic and powerful. Wide 16:9 banner composition, highly detailed.
```

## Image 2 — Core Features / The Forge Within (`docs/images/core-features.png`)

**Slot:** top of the "Core Capabilities" section.
**Shot:** medium shot, camera pushed inside the Guardian's translucent
chest-core, looking at the captured fragments being worked on — closer
and more intimate than Image 1, a different angle entirely.

**Prompt:**
```
Epic cinematic digital painting. Inside the luminous, translucent
chest-core of a towering Guardian made of brilliant electric cyan-white
circuitry, four captured code-fragments — now glowing solid cyan, no
longer dim amber — are suspended and actively being worked on, each in a
clearly distinct way so they read as four separate ideas: (1) one
fragment with fine threads of light branching outward from it to three
smaller sibling fragments, like a nervous system — cross-referencing
relationships; (2) two nearly-identical fragments held side by side,
one glowing subtly brighter than the other as if being judged and
scored — comparison and evaluation; (3) one fragment wrapped in a second,
outer layer of finer annotation-light, like a manuscript gaining
margin notes — documentation being generated around it; (4) one
fragment held against a faint mirror-echo of itself, with only the
genuinely matching parts lighting up — verification, not assumption.
All of this suspended inside a vast glowing chamber of circuitry, near-
black void just visible beyond the translucent chest wall, powerful rim
lighting, particle and light-trail detail. No text, no readable words,
not cute or cartoonish — epic and powerful. Wide 16:9 banner
composition, highly detailed.
```

## Image 3 — Design & Philosophy / The Release (`docs/images/design-philosophy.png`)

**Slot:** top of the "Design & Philosophy" section.
**Shot:** dramatic low-angle close-up, the most unusual framing of the
three — looking up at the Guardian's opening hand from below as it
releases its work back into the world.

**Prompt:**
```
Epic cinematic digital painting, dramatic low-angle shot looking up
from below. A towering Guardian made of brilliant electric cyan-white
circuitry opens its massive glowing hand, releasing several
code-fragments back out into the vast dark void — but these fragments
are no longer the small, dim, scattered sparks they were before capture;
they are now large, solid, brilliant crystalline constructs of pure
cyan light, complex and complete, flying outward powerfully with bright
trailing light-streaks, dwarfing what they used to be. The Guardian's
open hand and forearm fill the lower foreground in dramatic
silhouette-lit close-up, the released constructs soaring up and away
into the dark distance above. Near-black void, powerful rim lighting,
strong sense of scale and motion, particle and light-trail detail. No
text, no readable words, not cute or cartoonish — epic and powerful.
Wide 16:9 banner composition, highly detailed.
```
