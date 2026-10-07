/*
 * Overlapping 3D card deck for the accordion stacks.
 *
 * Cards of one stack overlap like a hand of cards: the last card sits in front
 * and every earlier card only shows a strip of its header. Depth is exposed as
 * CSS custom properties so the stylesheet owns the look:
 *   --stack-back   how many cards sit in front of this one (0 = front card)
 *   --stack-shift  scroll-linked parallax offset in px
 *   --stack-tilt   small rotateX from the card's distance to the viewport centre
 *   --stack-scale  scale from that same distance
 *   --stack-rise / --stack-fade  one-shot entrance motion
 * Everything is skipped for prefers-reduced-motion and offscreen cards.
 */
const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";
const READY_CLASS = "stack-motion-ready";
const ENTER_CLASS = "stack-entered";
const DECK_CLASS = "stack-deck";
const DEEP_DECK_CLASS = "stack-deck-deep";
const MAX_TILT_DEGREES = 1.6;
const MAX_SHRINK = 0.02;
const MAX_PARALLAX_PX = 2.4;
const DEEP_DECK_LIMIT = 6;
// Node.DOCUMENT_POSITION_FOLLOWING, inlined so the deck math stays testable without a DOM.
const DOCUMENT_POSITION_FOLLOWING = 4;

export function prefersReducedMotion() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return true;
  return window.matchMedia(REDUCED_MOTION_QUERY).matches === true;
}

export class StackMotion {
  constructor() {
    this.items = new Set();
    this.visible = new Set();
    this.decks = new Map();
    this.frame = 0;
    this.listening = false;
    this.observer = null;
    this.onScroll = this.onScroll.bind(this);
    this.onResize = this.onResize.bind(this);
    this.onMotionPreference = this.onMotionPreference.bind(this);
  }

  register(element) {
    if (!element || this.items.has(element)) return;
    this.items.add(element);
    element.classList.add(READY_CLASS);
    this.layoutDecks();
    if (prefersReducedMotion()) return;
    this.observe(element);
    this.listen();
    this.schedule();
  }

  unregister(element) {
    if (!element || !this.items.has(element)) return;
    this.items.delete(element);
    this.visible.delete(element);
    this.observer?.unobserve(element);
    this.releaseDeckClass(element);
    for (const property of ["--stack-tilt", "--stack-scale", "--stack-shift", "--stack-back",
      "--stack-rise", "--stack-fade"]) {
      element.style.removeProperty(property);
    }
    this.layoutDecks();
  }

  releaseDeckClass(element) {
    const parent = element.parentElement;
    if (!parent) return;
    const remaining = [...this.items].filter((item) => item.parentElement === parent);
    if (!remaining.length) {
      parent.classList.remove(DECK_CLASS, DEEP_DECK_CLASS);
      this.decks.delete(parent);
    }
  }

  /** Recompute the deck order so `--stack-back` matches the visual stacking. */
  layoutDecks() {
    const grouped = new Map();
    for (const element of this.items) {
      const parent = element.parentElement;
      if (!parent) continue;
      if (!grouped.has(parent)) grouped.set(parent, []);
      grouped.get(parent).push(element);
    }
    for (const [parent, children] of grouped) {
      children.sort((left, right) => (
        left.compareDocumentPosition(right) & DOCUMENT_POSITION_FOLLOWING ? -1 : 1
      ));
      const total = children.length;
      parent.classList.add(DECK_CLASS);
      parent.classList.toggle(DEEP_DECK_CLASS, total <= DEEP_DECK_LIMIT);
      children.forEach((element, index) => {
        // The last card is fully visible, so earlier cards carry the depth.
        element.style.setProperty("--stack-back", String(Math.min(total - 1 - index, 5)));
      });
      this.decks.set(parent, children);
    }
  }

  observe(element) {
    if (typeof IntersectionObserver !== "function") {
      this.visible.add(element);
      this.reveal(element);
      return;
    }
    if (!this.observer) {
      this.observer = new IntersectionObserver((entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            this.visible.add(entry.target);
            this.reveal(entry.target);
          } else {
            this.visible.delete(entry.target);
          }
        }
        this.schedule();
      }, { rootMargin: "120px 0px" });
    }
    this.observer.observe(element);
  }

  reveal(element) {
    if (element.classList.contains(ENTER_CLASS)) return;
    element.classList.add(ENTER_CLASS);
    element.style.setProperty("--stack-rise", "18px");
    element.style.setProperty("--stack-fade", "0");
    window.requestAnimationFrame(() => {
      element.style.setProperty("--stack-rise", "0px");
      element.style.setProperty("--stack-fade", "1");
    });
  }

  listen() {
    if (this.listening || typeof window === "undefined") return;
    this.listening = true;
    window.addEventListener("scroll", this.onScroll, { passive: true });
    window.addEventListener("resize", this.onResize);
    window.matchMedia?.(REDUCED_MOTION_QUERY).addEventListener?.("change", this.onMotionPreference);
  }

  teardown() {
    if (!this.listening || typeof window === "undefined") return;
    this.listening = false;
    window.removeEventListener("scroll", this.onScroll);
    window.removeEventListener("resize", this.onResize);
    window.matchMedia?.(REDUCED_MOTION_QUERY).removeEventListener?.("change", this.onMotionPreference);
  }

  onMotionPreference() {
    if (prefersReducedMotion()) {
      for (const element of this.items) {
        for (const property of ["--stack-tilt", "--stack-scale", "--stack-shift"]) {
          element.style.removeProperty(property);
        }
      }
      this.teardown();
      return;
    }
    this.listen();
    this.schedule();
  }

  onScroll() {
    this.schedule();
  }

  onResize() {
    this.layoutDecks();
    this.schedule();
  }

  schedule() {
    if (this.frame || typeof window === "undefined") return;
    this.frame = window.requestAnimationFrame(() => {
      this.frame = 0;
      this.measure();
    });
  }

  measure() {
    if (prefersReducedMotion()) return;
    const viewport = window.innerHeight || 0;
    if (!viewport) return;
    const center = viewport / 2;
    for (const element of this.visible) {
      const rect = element.getBoundingClientRect();
      if (!rect.height) continue;
      const offset = Math.max(-1, Math.min(1, (rect.top + rect.height / 2 - center) / center));
      const magnitude = Math.abs(offset);
      element.style.setProperty("--stack-tilt", `${(-offset * MAX_TILT_DEGREES).toFixed(3)}deg`);
      element.style.setProperty("--stack-scale", (1 - magnitude * MAX_SHRINK).toFixed(4));
      // Deeper cards drift a little more, which reads as the deck breathing while scrolling.
      element.style.setProperty("--stack-shift", `${(-offset * MAX_PARALLAX_PX).toFixed(2)}px`);
    }
  }
}

export const stackMotion = new StackMotion();

export const vStackMotion = {
  mounted(element) {
    stackMotion.register(element);
  },
  unmounted(element) {
    stackMotion.unregister(element);
  },
};
