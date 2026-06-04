"""
Market Data Engine — Launcher Visual Engine
Renders animated dark gradient background with floating particles,
glowing logo, and plasma separator. Fully self-contained.
"""

import math
import random
from tkinter import Canvas
from PIL import Image, ImageTk, ImageDraw, ImageFilter


# Neon palette
NEON_CYAN = "#00E8D4"
NEON_VIOLET = "#A855F7"
NEON_TEAL = "#14B8A6"
BG_DARK = "#020208"


class FloatingParticle:
    """Single ambient floating particle with drift + pulse."""
    def __init__(self, width, height):
        self.x = random.uniform(0, width)
        self.y = random.uniform(0, height)
        self.vx = random.uniform(-0.15, 0.15)
        self.vy = random.uniform(-0.12, 0.12)
        self.max_size = random.choice([0.6, 0.9, 1.2, 1.5, 1.8])
        self.color = random.choice(["#00E8D4", "#A855F7", "#14B8A6", "#d4e0f7", "#ffffff"])
        self.pulse_speed = random.uniform(0.02, 0.06)
        self.pulse_phase = random.uniform(0, math.pi * 2)
        self.width = width
        self.height = height

    def update(self):
        self.x += self.vx
        self.y += self.vy
        if self.x < 0:
            self.x = self.width
        elif self.x > self.width:
            self.x = 0
        if self.y < 0:
            self.y = self.height
        elif self.y > self.height:
            self.y = 0


class ParticleField:
    """Ambient floating particles across the canvas."""
    def __init__(self, width, height, count=40):
        self.particles = [FloatingParticle(width, height) for _ in range(count)]

    def draw(self, canvas, frame_idx):
        for p in self.particles:
            p.update()
            pulse = 0.3 + 0.7 * abs(math.sin(frame_idx * p.pulse_speed + p.pulse_phase))
            size = p.max_size * pulse
            if size < 0.3:
                continue
            canvas.create_oval(
                p.x - size, p.y - size, p.x + size, p.y + size,
                fill=p.color, outline="", tags="particles"
            )


class LauncherVisualEngine:
    """Renders the cinematic gradient background and particle field."""
    def __init__(self, width, height, scaling=1.0):
        self.width = int(width * scaling)
        self.height = int(height * scaling)
        self.bg_image = self._render_gradient()
        self.bg_photo = ImageTk.PhotoImage(self.bg_image)
        self.particles = ParticleField(self.width, self.height, count=35)

    def _render_gradient(self):
        w, h = self.width, self.height
        img = Image.new("RGBA", (w, h))
        draw = ImageDraw.Draw(img)
        for y in range(h):
            ratio = y / h
            r = int(2 + 8 * ratio)
            g = int(2 + 6 * ratio)
            b = int(10 + 20 * ratio)
            draw.line([(0, y), (w, y)], fill=(r, g, b, 255))

        # Subtle radial glow top-left (cyan) and bottom-right (violet)
        glow_cyan = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gc_draw = ImageDraw.Draw(glow_cyan)
        gc_draw.ellipse([-w // 3, -h // 3, w // 2, h // 2], fill=(0, 232, 212, 18))
        glow_cyan = glow_cyan.filter(ImageFilter.GaussianBlur(radius=60))
        img = Image.alpha_composite(img, glow_cyan)

        glow_violet = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gv_draw = ImageDraw.Draw(glow_violet)
        gv_draw.ellipse([w // 2, h // 3, int(w * 1.3), int(h * 1.3)], fill=(168, 85, 247, 14))
        glow_violet = glow_violet.filter(ImageFilter.GaussianBlur(radius=50))
        img = Image.alpha_composite(img, glow_violet)

        return img

    def draw_frame(self, canvas, frame_idx):
        canvas.delete("all")
        canvas.create_image(0, 0, image=self.bg_photo, anchor="nw", tags="bg")
        self.particles.draw(canvas, frame_idx)


class PlasmaSeparator:
    """Animated gradient separator line that cycles through neon colors."""
    def __init__(self, parent, width=500, height=3, scaling=1.0):
        self.width = int(width * scaling)
        self.height = int(max(3, height * scaling))
        self.canvas = Canvas(parent, highlightthickness=0, bg=BG_DARK,
                             width=self.width, height=self.height)
        self._frame_idx = 0
        self._total_frames = 120
        self._photo_cache = []
        self._build_cache()

    def _build_cache(self):
        import colorsys
        for f_idx in range(self._total_frames):
            img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            phase = f_idx / self._total_frames
            for x in range(self.width):
                t = x / self.width
                hue = (0.48 + 0.15 * math.sin(t * math.pi * 3 + phase * math.pi * 2)
                       + 0.06 * math.sin(phase * math.pi * 4))
                shimmer_peak = (phase * 2.0) % 2.0 - 0.5
                dist = abs(t - shimmer_peak)
                brightness = 0.55 + 0.45 * max(0, 1 - dist * 3.5)
                sat = 0.75 + 0.25 * math.sin(t * math.pi * 2 + phase * math.pi * 6)
                r, g, b = colorsys.hsv_to_rgb(hue % 1.0, sat, brightness)
                ri, gi, bi = int(r * 255), int(g * 255), int(b * 255)
                alpha = int(180 + 75 * brightness)
                for y in range(self.height):
                    edge = 1.0 - abs(y - self.height / 2) / (self.height / 2)
                    a = int(alpha * edge * edge)
                    draw.point((x, y), fill=(ri, gi, bi, max(0, min(255, a))))
            glow = img.filter(ImageFilter.GaussianBlur(radius=1))
            merged = Image.alpha_composite(glow, img)
            self._photo_cache.append(ImageTk.PhotoImage(merged))

    def place(self, **kwargs):
        self.canvas.place(**kwargs)

    def animate(self):
        self._frame_idx = (self._frame_idx + 1) % self._total_frames
        frame = self._photo_cache[self._frame_idx]
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=frame, anchor="nw", tags="plasma")
