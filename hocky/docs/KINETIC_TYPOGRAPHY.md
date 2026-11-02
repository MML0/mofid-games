# Kinetic type backdrop

The faint wave of letters behind the splash, countdown, goals and results. It is a port of the Brik sketch
[circle wave kinetic typography](https://brik.space/tools/remix-of-circle-wave-kinetic-typography-movrkwb1), in
`market_hockey/render/kinetic.py`. Preview and tune it with:

```bash
.venv/bin/python tools/kinetic_lab.py
```

In the game, the same sliders are in the control panel under **Kinetic Type**.

## What each slider does

For every grid cell, `d` is the distance from the cell to the wave center.

| Slider | Formula | What you see |
|---|---|---|
| Grid Density | `spacing = canvas / (density + 1)` | Cells per side. Also sets the letter size, because `textSize = spacingY * 0.9`. |
| Character Set | `chars[floor(d / (ringWidth / 2)) % length]` | The text spelled outward from the center, one letter per half ring. A space leaves an empty ring. |
| Animation Speed | `sin(frame * speed + ...)` | How fast the waves travel outward, in radians per frame. |
| Wave Frequency | `sin(... + d * frequency)` | How many waves fit on screen. The wavelength is `2π / frequency`. |
| Min Stretch | `map(wave, -1, 1, min, max)` | Letter width in the wave's trough. Low values make thin slivers. |
| Max Stretch | same | Letter width on the crest, where neighbors merge into solid bars. |
| Ring Width | `floor(d / ringWidth)` | Width of each color band. It also sets the letter rings, at half this width. |
| Colors 1, 2, 3 | `palette[(ring + shift) % 3]` | The band colors, repeating outward. |
| Color Swap | `shift = floor(frame / interval)` | Moves every band to the next color each interval, in a hard step. |
| Background | | Fill behind the letters. The game omits it and adds the letters over the arena. |

Only the width stretches (`scale(stretch, 1)`). The height stays fixed.

The reference page's values are density 28, speed 0.06, frequency 0.03, stretch 0.25 to 2.6, ring width 75, on a
1080 × 1350 canvas. Slider values mean the same on any canvas, because distances are scaled to that canvas's size.

## What differs from the sketch

- **Phase accumulates.** The sketch's `frameCount * speed` jumps whenever speed changes, so animating speed needs
  `phase += speed * dt`.
- **New controls for the moments:** font scale, opacity, a movable wave center, a reveal annulus, a text wipe, a
  letter-width limit, and a split that gives the two halves of the arena different looks.
- **Centering in the game.** Each letter's visible shape is centered on its cell, and one cell always sits on the exact
  middle (the density rounds up to an odd number). The sketch aligns on the font's line box instead, which sits a little
  off center. The lab's Site mode keeps the sketch's alignment.
- **Faster, slightly coarser widths in the game.** Widths snap to steps of about 3% above 32 px, and at most 110 new
  sprites are built per frame. The lab's Site mode has neither limit.

## Moments

Each moment in `MOMENTS` is a set of keyframe tracks over the sliders, so the lab's handles move as it plays. All
effect text is English, and every effect is centered on the arena.

| Moment | Text | What the sliders do |
|---|---|---|
| Splash, on launch | Brand texts | Density falls from 45 while the rings reveal from the center. |
| Waiting | Brand texts, in turn | Stretch, frequency and ring width drift on slow sines, and each new text spreads out from the center. |
| Match start | `MARKET HOCKEY` | The grid folds from fine to large type. |
| Ready | `READY` | Steady letters around a clear center. |
| 3, 2, 1 | The digit | The grid stays fixed at 13 and the digit stays whole. Each beat is a gentle swell around a clear center. |
| Go | `GO` | The widest stretch of the countdown, then a hole opens from the middle to clear the arena for play. |
| Goal | `GOAL` in the scorer's color | A wave spreading from the center. **Start goal wave at the impact point** moves it to where the ball crossed the line. |
| Final | `MARKET CLOSED` | Every slider winds down until the letters nearly stop. |
| Result | `WINNER` | The winner's half is lit. The other half is calm brand red with `STEADY PROGRESS`. The seam is cut on the exact center line. |

During play the backdrop is off, so the ball stays easy to read (`kinetic.opacity_play`, default 0).

**Max Letter Width** caps how far one letter can spread over its neighbors (1.5 cells by default). Lower it for more
readable type, or raise it to 8 for the fully merged bars the sketch can make. **Moment Pace** slows or speeds up the
splash, go, goal and result.

Moments only animate sliders that glide smoothly. Changing density or ring width moves or recolors every cell at once,
which looks like a jump, so a moment leaves them alone or holds them constant for its whole length.

## Additions for the game

Neither Brik tool has these controls; they are in the **Kinetic Type** tab and in the lab.

- **Opacity wave (waiting screen).** A second sine that only changes opacity:
  `opacity = map(sin(opacityPhase + d * frequency) ^ sharpness, min, max)`. At frequency 0 the whole visual fades out and
  returns together. Higher frequencies make rings of light and dark. Sharpness above 1 gives shorter peaks, like a pulse.
- **Rim fade.** Letters fade from **Fade starts** to nothing at **Fade ends**, so they stay inside the paddles, walls and
  goal lines.
- **Letter ring width.** In the sketch, letters change every half color ring, so tight color rings would scramble the
  words. Here the two are separate.

## How it follows the brand book

| Rule (Brand Book V04) | Applied here |
|---|---|
| Turquoise `#00A796` is the primary color and means profit and growth | Color 1. Colors 2 and 3 (`#53D5FD`, `#94E3FE`) come from the reference settings and aren't in the brand book |
| Red `#F3716D` means loss or a falling market, under 50% of an illustration, never a background | Only on the losing half of the result, at low opacity |
| Purple `#832C73` is limited to under 30% of a background | Only as Player 2's team color |
| No sad, discouraging, harsh or cluttered imagery | The other side shows the slogan `STEADY PROGRESS`, never a loss message |
| Identity graphics are the five marks (dot, plus, minus, times, slash) and a dot grid | Spaces become dots, and the marks ride the front of a text wipe, drawn as vectors with the book's proportions |
| Brand phrases: Mofid Securities, Steady Progress | The default waiting-screen texts |
| Persian titles use a strong display face, and body text a calmer one (Dana and IRANSans in the book) | Pinar Black for titles, Pinar Bold for messages, and Pinar on the supervisor page |
| English type is Helvetica or Myriad | SF Compact Display Bold for English text. Heavy for the digits and the effect's letters |

The fonts come from `Fonts/`, with Pinar's weights baked into `assets/fonts` by `tools/make_brand_fonts.py`. The lab's
Site mode keeps pygame's FreeSansBold, the closest match to the sketch's Helvetica.

## Moving brand objects

`market_hockey/render/brand_motion.py` adds moving objects between the letters and the game. Reference: the Meta "Chat Circle" floor projection, especially seconds 28 to 32. Settings are in the **Brand Motion** tab. Try each object with the buttons at the bottom of `tools/kinetic_lab.py`.

| Object | From the reference | From the brand book |
|---|---|---|
| Flood | The disc floods, grooved with pulsing rings, and an iris opens | Brand tint, turquoise and the team colors |
| Center coin | A disc turning over from picture to picture | The book's icons and the bull |
| Paper plane | A folded plane banking across the board | The Telegram icon's plane, folded in 3D, with a trail of brand dots |
| Flying coins | Emoji arriving and leaving | The book's icons on brand-colored coins |
| Coin wall | The wall of flipping emoji | The same coins. On the result it fills the winner's half and keeps clear of the text |
| Dot grid | The bloom from the center | The identity page's dot grid: dots swell and open into the five marks, on a heartbeat |
| Fine rings | The pulsing concentric rings | Turquoise and tint, lit by two sines beating against each other |
| Market chart | (added for this client) | The shapes of the book's chart icons, with red for falling candles |
| Marks burst | The confetti | The five identity marks |

**When they run.** The waiting screen plays a 46 second loop. The match start floods, the countdown (5 to 1, `countdown.start`) runs a ring with one dot going round it, GO floods again, and each goal floods and throws marks in the scorer's color. A plane crosses during play every 14 seconds at 45% strength.

**Staying in the background.** Objects are drawn together on one layer at 60% (`motion.object_opacity`), floods at 60% (`motion.flood_strength`) and the chart a little lower still (`motion.chart_strength`). All of them fade between 0.72 and 0.92 of the radius (`motion.edge_fade_start`, `motion.edge_fade_end`), a shorter fade than the letters' 0.5 to 0.82, so objects keep their size. On the waiting screen a soft dark backing (`match.title_backing`) sits behind the title and the prompt, so the visuals pass behind the text.

**The Mofid logo.** The book's stacked logo, the bull above کارگزاری مفید and پیشرفت مداوم, in white on transparent, baked from the book's vectors. It stays in the background of the waiting screen at 55% (`motion.logo_rest`). After Start the same logo brightens, a damped spring carries it to the center with one soft overshoot and a little growth, its growth then builds, and it fades to zero while still growing, over `match.intro_s`. All of it follows smooth curves with no phases to switch between. The waiting text fades out over it. The result screen has a small logo at its head.

**Brand rules kept.** A goal in any team color but turquoise floods in fine bands, because the book limits purple and red as backgrounds. Red is only used for falling candles and the other side on the result. The bull only appears in white, on turquoise or dark blue.

**Sharpness on a 4 m floor.** A 1080 px canvas gives 3.7 mm per pixel, so a projector with more pixels (and a larger `display.canvas_width` and `canvas_height`) is the one thing that can make it sharper still. Within that: rings are computed per radius, polygons are antialiased each frame instead of rotating a bitmap, coins are built large and reduced, and letters are built at 4x with tightened edges.

To rebuild the icons from the PDF: `python3 tools/make_brand_icons.py /path/to/Brnadbook-V04.pdf` (needs PyMuPDF).
