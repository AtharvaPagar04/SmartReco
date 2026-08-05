/**
 * Minimal Live Background — Floating Glowing Particles & Ambient Orbs
 * Creates a subtle, high-performance ambient glow background matching
 * modern dark-mode aesthetic standards.
 */
(function () {
  'use strict';

  function initAmbientBackground() {
    const canvas = document.getElementById('ambient-bg');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    window.addEventListener('resize', function () {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
      createParticles();
    });

    const particles = [];
    const particleCount = Math.min(Math.floor((width * height) / 22000), 45);

    // Light glowing orbs
    const orbs = [
      { x: width * 0.2, y: height * 0.15, r: 280, vx: 0.15, vy: 0.1, color: 'rgba(99, 102, 241, 0.07)' },
      { x: width * 0.8, y: height * 0.35, r: 340, vx: -0.12, vy: 0.12, color: 'rgba(168, 85, 247, 0.05)' },
      { x: width * 0.5, y: height * 0.85, r: 300, vx: 0.08, vy: -0.15, color: 'rgba(59, 130, 246, 0.06)' },
    ];

    function Particle() {
      this.x = Math.random() * width;
      this.y = Math.random() * height;
      this.radius = Math.random() * 1.5 + 0.5;
      this.alpha = Math.random() * 0.4 + 0.1;
      this.vx = (Math.random() - 0.5) * 0.25;
      this.vy = (Math.random() - 0.5) * 0.25;
      this.pulseSpeed = Math.random() * 0.015 + 0.005;
      this.pulse = Math.random() * Math.PI;
    }

    function createParticles() {
      particles.length = 0;
      for (let i = 0; i < particleCount; i++) {
        particles.push(new Particle());
      }
    }

    createParticles();

    function render() {
      ctx.clearRect(0, 0, width, height);

      // Render ambient soft light orbs
      orbs.forEach(function (orb) {
        orb.x += orb.vx;
        orb.y += orb.vy;

        if (orb.x < -100 || orb.x > width + 100) orb.vx *= -1;
        if (orb.y < -100 || orb.y > height + 100) orb.vy *= -1;

        const grad = ctx.createRadialGradient(orb.x, orb.y, 0, orb.x, orb.y, orb.r);
        grad.addColorStop(0, orb.color);
        grad.addColorStop(1, 'rgba(5, 5, 8, 0)');

        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(orb.x, orb.y, orb.r, 0, Math.PI * 2);
        ctx.fill();
      });

      // Render floating subtle particles
      particles.forEach(function (p) {
        p.x += p.vx;
        p.y += p.vy;
        p.pulse += p.pulseSpeed;

        if (p.x < 0) p.x = width;
        if (p.x > width) p.x = 0;
        if (p.y < 0) p.y = height;
        if (p.y > height) p.y = 0;

        const currentAlpha = p.alpha + Math.sin(p.pulse) * 0.15;

        ctx.fillStyle = 'rgba(255, 255, 255, ' + Math.max(0.02, Math.min(0.65, currentAlpha)) + ')';
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fill();
      });

      requestAnimationFrame(render);
    }

    render();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAmbientBackground);
  } else {
    initAmbientBackground();
  }
})();
