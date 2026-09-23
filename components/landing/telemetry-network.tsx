"use client";

import { useEffect, useRef } from "react";
import { pointerX, pointerY, subscribePointer } from "@/lib/pointer";
import { useReducedMotionSafe } from "@/lib/use-reduced-motion";

type Point = { x: number; y: number; vx: number; vy: number; r: number };

const LINK_DIST = 150;
const POINTER_RADIUS = 240;

/**
 * A barely-visible constellation / flight-path network behind the hero.
 * Points drift slowly; links and nodes brighten near the pointer.
 * Runs only while visible, only on desktop, never under reduced motion.
 */
export function TelemetryNetwork({ className }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const reduce = useReducedMotionSafe();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    if (window.matchMedia("(max-width: 767px)").matches) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const unsubscribe = subscribePointer();
    let points: Point[] = [];
    let width = 0;
    let height = 0;
    let dpr = 1;
    let raf = 0;
    let running = false;
    let last = 0;

    const seed = () => {
      const count = Math.round(Math.min(72, Math.max(28, (width * height) / 20000)));
      points = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 6,
        vy: (Math.random() - 0.5) * 6,
        r: 0.8 + Math.random() * 1.1,
      }));
    };

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      width = rect.width;
      height = rect.height;
      dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      seed();
      if (reduce) draw(0);
    };

    const draw = (dt: number) => {
      ctx.clearRect(0, 0, width, height);
      const rect = canvas.getBoundingClientRect();
      const mx = pointerX.get() - rect.left;
      const my = pointerY.get() - rect.top;

      // move
      if (dt > 0) {
        for (const p of points) {
          p.x += p.vx * dt;
          p.y += p.vy * dt;
          if (p.x < -20) p.x = width + 20;
          if (p.x > width + 20) p.x = -20;
          if (p.y < -20) p.y = height + 20;
          if (p.y > height + 20) p.y = -20;
        }
      }

      // links
      ctx.lineWidth = 1;
      for (let i = 0; i < points.length; i++) {
        const a = points[i];
        for (let j = i + 1; j < points.length; j++) {
          const b = points[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const d2 = dx * dx + dy * dy;
          if (d2 > LINK_DIST * LINK_DIST) continue;
          const d = Math.sqrt(d2);
          const base = (1 - d / LINK_DIST) * 0.11;
          const cx = (a.x + b.x) / 2;
          const cy = (a.y + b.y) / 2;
          const pd = Math.hypot(cx - mx, cy - my);
          const boost = pd < POINTER_RADIUS ? (1 - pd / POINTER_RADIUS) * 0.42 : 0;
          const alpha = base + boost;
          ctx.strokeStyle = boost > 0.02 ? `rgba(89,217,255,${alpha})` : `rgba(221,248,255,${alpha})`;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }

      // nodes
      for (const p of points) {
        const pd = Math.hypot(p.x - mx, p.y - my);
        const boost = pd < POINTER_RADIUS ? (1 - pd / POINTER_RADIUS) : 0;
        const alpha = 0.28 + boost * 0.6;
        ctx.fillStyle = boost > 0.05 ? `rgba(89,217,255,${alpha})` : `rgba(221,248,255,${alpha})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r + boost * 1.2, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    const frame = (ts: number) => {
      const dt = last ? Math.min(0.05, (ts - last) / 1000) : 0;
      last = ts;
      draw(dt);
      raf = requestAnimationFrame(frame);
    };

    const start = () => {
      if (running || reduce) return;
      running = true;
      last = 0;
      raf = requestAnimationFrame(frame);
    };
    const stop = () => {
      running = false;
      cancelAnimationFrame(raf);
    };

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    const io = new IntersectionObserver(
      ([entry]) => (entry.isIntersecting && !document.hidden ? start() : stop()),
      { threshold: 0 },
    );
    io.observe(canvas);
    const onVis = () => (document.hidden ? stop() : start());
    document.addEventListener("visibilitychange", onVis);

    return () => {
      stop();
      ro.disconnect();
      io.disconnect();
      document.removeEventListener("visibilitychange", onVis);
      unsubscribe();
    };
  }, [reduce]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={className}
      style={{ width: "100%", height: "100%", display: "block" }}
    />
  );
}
