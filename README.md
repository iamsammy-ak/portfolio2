# Abhishek Kumar — portfolio

One page, one continuous cut: a studio portrait in 3D that a cursor (or a finger) scans into a machine,
a scroll-driven journey reel, the projects, and how to work together. Built after the structure and
motion of benkaluza.com, rebuilt for an engineer.

Live at **https://iamsammy-ak.github.io/portfolio2/** (GitHub Pages, from the `main` branch).
No build step: push to `main` and the site updates within a minute or two.

## What's in here

| Path | What it is |
| --- | --- |
| `index.html` | The whole site: markup, CSS, the WebGL hero (three.js shaders, a small fluid sim), the journey reel, arrivals. |
| `assets/hero/` | `face.webp` (the cut-out portrait), `depth.webp` (relief for the 3D), `machine.webp` (the machine view), `hero-data.js` (478 face-mesh points). All generated, see below. |
| `assets/story/` | The eight journey cards as images, rendered from `tools/story-cards.html`. |
| `assets/fonts/` | Archivo (variable: weight and width), Geist, Geist Mono. Latin subsets. |
| `assets/cv/` | The CV the Download button serves. |
| `vendor/` | three.js r128 and Lenis 1.1.13, served locally. |
| `tools/` | The generators below plus `shoot.mjs`, a DevTools-protocol screenshotter used while building. |

## Change the content

Everything personal is near the top of the script in `index.html` or in the markup:

- **Name and headline:** the `.wordmark` spans, and `HEAD_L…HEAD_R2` (`PART ENGINEER.` / `PART MACHINE.`).
- **Journey:** the `CHAPTERS` array (year, place, title, picture, one line) and `STAGGER` (how far each card sits above or below the timeline). `FT_AT` is the chapter where the timeline turns from dashed (bachelor's) to solid (master's).
- **Projects, offers, organisations, contact, footer:** plain HTML in the `today`, `work` and `footer` sections.
- **Email:** the `mailto:` link and the string in the Copy button handler.

## Regenerate the hero from a new photo

The hero wants a front-on portrait with even light. The sharper the photo, the sharper the 3D head
(the current source is 960 px wide, so the head is a little soft at full size).

```
python -m pip install pillow numpy scipy mediapipe rembg onnxruntime opencv-python-headless
python tools/prepare_hero.py path/to/photo.jpg
```

This frames the crop like the reference (face about 36% of the width, eyes 41% down, shirt running off
the bottom), cuts the background, runs MediaPipe's face mesh, builds the depth relief from the silhouette
plus the mesh, and draws the machine view (brushed metal from the depth lighting, the mesh as etched seams,
lens eyes, a grille for the mouth). The live site instead uses the rendered robot head in
`tools/machine-source.webp`, fitted to the mesh by a second step:

```
python tools/fit_machine.py
```

It maps the render's eyes and chin onto yours (scale, rotation, shift) and writes `machine.webp`, so a new
photo only needs the two commands in order. Skip it to keep the wireframe version.

## Regenerate the journey cards

Edit `tools/story-cards.html` (one `<section class="card">` per chapter), then:

```
bash tools/render_story.sh
```

## Check it

```
node tools/shoot.mjs out.png --at=0.5 --mouse=600,400;800,420 --wait=1500
node tools/shoot.mjs phone.png --w=390 --h=844 --dpr=2 --touch --at=0.4
```

`?at=0.5` on the URL jumps the page to that fraction with smooth scrolling off.
