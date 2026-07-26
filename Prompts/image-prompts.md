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

CodeIntel is personified as a towering Guardian whose entire body is
woven from living, luminous code — not a robot, not a cute character.
Its defining trait is a **duality**: immense, unmistakable power and
absolute certainty — nothing it seeks ever gets lost — held together
with total gentleness, innocence and tenderness. It never hunts or
seizes; it *gathers*, the way a shepherd gathers scattered lambs before
a storm, or a parent scoops up a frightened child — decisive and
sure-handed, but soft, protective, without a trace of menace or
aggression. The three banners are one continuous story, told across the
README:

1. **The Gathering** — small, scattered fragments of code (dim,
   rust-amber, drifting and lost like fireflies separated from their
   swarm through a vast dark digital void) are cupped and drawn in by
   the Guardian's open, gentle hands — none of them stay lost, but none
   are grabbed or crushed either. (This *is* hybrid search: certain, but
   careful.)
2. **The Nurturing Within** — inside the Guardian's own luminous
   chest-core, the gathered fragments are cradled, cross-referenced,
   compared, annotated — tended to, the way a mentor teaches, not the
   way a machine processes. (This *is* deep research, the comparison
   table, the symbol graph, the manual generator.)
3. **The Release** — the Guardian opens its hands with quiet pride and
   sends the same fragments back out, transformed: no longer small and
   lost, but large, solid, brilliant, complete — like a parent watching
   a grown child leave home, ready. (This *is* the enriched answer,
   explanation, or documentation coming back to the developer.)

- **World:** a vast, dark digital void (not a screen, not outer space —
  a bottomless dark expanse implying limitless codebase scale). The
  Guardian's body is built from flowing ribbons of glowing script-like
  circuitry, dense and warm at the core, softening into fine luminous
  threads at the extremities — powerful in scale, gentle in every
  gesture and posture; nothing about its stance ever reads as
  threatening.
- **The four fragment archetypes:** the drifting/gathered code-fragments
  are never generic blobs — they read as four distinct silhouette
  families, each evoking a different language *by shape and texture
  alone*, never by literal text: a **Delphi** fragment is a rectangular,
  tablet-like shard with a formal double-line border and a small
  bracket-notch at each end, like a sealed scroll (this is the
  Guardian's own native shape — it appears most often and largest,
  since Delphi is CodeIntel's deepest home); a **C++** fragment is an
  angular, faceted shard with sharp pointer-like spikes jutting from its
  edges and layered chevron facets, metallic and systems-cold at the
  glint but still warmed by the Guardian's glow; a **Python** fragment
  is a smooth, serpentine ribbon that curves in soft descending steps,
  rounded and flowing, no hard edges at all; a **C#** fragment is a
  rounded-square shard with a faint dotted lattice texture and two or
  three tiny orbiting pennant-flecks drifting just above its surface
  like small attached tags. All four families share the same size range
  and the same rust-amber-to-cyan transformation arc — they are
  siblings, not a hierarchy.
- **Palette:** near-black void (base), brilliant electric cyan-white
  with a warm, soft inner glow — never harsh or cold — (the Guardian,
  and anything it has already touched/transformed), dim rust-amber
  (lost/unprocessed code, before gathering) — the cyan-vs-amber contrast
  *is* the before/after of the whole story, and the Guardian's light
  should always feel nurturing rather than blinding.
- **Style:** cinematic digital-painting, soft volumetric glow rather than
  harsh rim lighting, tender and reverent mood even at epic scale,
  particle/light-trail detail.
- **Consistency:** all three images share this exact Guardian, world,
  and palette; each is a different beat of the same story, a different
  shot type and camera angle.

## Negative Prompt (paste into every generation)

```
text, letters, readable words, logos, watermark, low quality, blurry,
menacing, aggressive, predatory, monstrous, cute, chibi, cartoon mascot,
toy-like, humans, real robots, screens, monitors, keyboards, office
setting, different art style between images
```

## Image 1 — Overview / The Gathering (`docs/images/overview.png`)

**Slot:** top of the README, under the title/badges.
**Shot:** wide dynamic shot, diagonal composition, gentle motion on the
drifting fragments — establishes the whole world and story.

**Prompt:**
```
Cinematic digital painting. In a vast, bottomless dark digital void, a
scatter of small, dim, rust-amber code-fragments drifts and wanders in
every direction, disoriented rather than fleeing in fear. The
fragments are clearly four distinct silhouette families, no literal
text on any of them: rectangular tablet-like shards with a formal
double-line border and a small bracket-notch at each end (most numerous
and largest of the four); angular faceted shards with sharp pointer-like
spikes and metallic chevron facets; smooth serpentine ribbons that curve
in soft descending steps; rounded-square shards with a faint dotted
lattice texture and two or three tiny orbiting pennant-flecks. From the
edge of frame, an enormous Guardian made entirely of flowing, brilliant
electric cyan-white circuitry and living code-ribbons reaches in with
both open hands, cupped gently rather than grasping, drawing a cluster
of the lost fragments — one of each silhouette family visible together —
toward its palms with unmistakable certainty but total tenderness. The
fragments already gathered are softening into a warmer glow, shifting
from dim rust-amber toward brilliant cyan as they near the Guardian's
hands, their distinct shapes still readable even as they brighten. Many
more fragments of all four families still drift in the distance, but
not one of them will be left behind. Strong diagonal composition, gentle
motion blur on the drifting fragments, soft warm volumetric glow around
the Guardian's hands and arms — powerful in scale, protective and
unthreatening in posture — near-black void background, particle and
light-trail detail. No text, no readable words, not menacing, not cute
or cartoonish — immense yet tender. Wide 16:9 banner composition,
highly detailed.
```

## Image 2 — Core Features / The Nurturing Within (`docs/images/core-features.png`)

**Slot:** top of the "Core Capabilities" section.
**Shot:** medium shot, camera pushed inside the Guardian's translucent
chest-core, looking at the gathered fragments being tended to — closer
and more intimate than Image 1, a different angle entirely.

**Prompt:**
```
Cinematic digital painting. Inside the luminous, translucent chest-core
of a towering Guardian made of brilliant electric cyan-white circuitry,
four gathered code-fragments — now glowing a warm solid cyan, no longer
dim amber, and clearly the four silhouette families from the gathering:
a rectangular double-bordered tablet shard, an angular chevron-faceted
shard, a smooth descending-step ribbon, and a rounded-square
dotted-lattice shard with its small pennant-flecks — rest cradled in
soft light, each being tended to in a clearly distinct way so they read
as four separate ideas, all rendered gently rather than clinically: (1)
the tablet shard has fine threads of light branching outward from it to
three smaller sibling fragments, like a hand resting on each in turn —
cross-referencing relationships; (2) the chevron shard sits held close
beside a second, nearly-identical chevron shard, one glowing subtly
brighter as if being lovingly, carefully compared, not judged; (3) the
ribbon shard is wrapped in a second, soft outer layer of finer
annotation-light, like a blanket of margin notes — documentation being
generated around it; (4) the pennant shard is held gently against a
faint mirror-echo of itself, only the genuinely matching parts warming
into light — patient verification, not assumption. All of this cradled inside
a vast, warmly glowing chamber of circuitry, near-black void just
visible beyond the translucent chest wall, soft volumetric glow rather
than harsh light, particle and light-trail detail. No text, no readable
words, not menacing, not cute or cartoonish — immense yet tender. Wide
16:9 banner composition, highly detailed.
```

## Image 3 — Design & Philosophy / The Release (`docs/images/design-philosophy.png`)

**Slot:** top of the "Design & Philosophy" section.
**Shot:** dramatic low-angle close-up, the most unusual framing of the
three — looking up at the Guardian's opening hands from below as it
releases its work back into the world.

**Prompt:**
```
Cinematic digital painting, low-angle shot looking up from below. A
towering Guardian made of brilliant electric cyan-white circuitry opens
its hands slowly and with quiet pride, releasing several code-fragments
back out into the vast dark void — not thrown or launched, but let go
gently, the way a parent lets a grown child step forward on their own.
These fragments are no longer the small, dim, lost sparks they were
before gathering; they are now large, solid, brilliant crystalline
constructs of warm cyan light, complex and complete, drifting outward
steadily and confidently with soft trailing light-streaks, dwarfing what
they used to be — yet each still clearly reads as one of the four
silhouette families (tablet, chevron, ribbon, pennant-lattice), now
rendered as fully-formed crystalline sculptures instead of small drifting
shards. The Guardian's open hands and forearms fill the lower
foreground in a tender, reverent close-up, softly rim-lit rather than
harshly silhouetted, the released constructs rising up and away into the
dark distance above like something being sent off with love. Near-black
void, soft warm volumetric glow, strong sense of scale without menace,
particle and light-trail detail. No text, no readable words, not
menacing, not cute or cartoonish — immense yet tender. Wide 16:9 banner
composition, highly detailed.
```
