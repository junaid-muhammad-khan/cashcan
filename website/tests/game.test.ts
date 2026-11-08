import { describe, expect, it } from "vitest";
import {
  BINS, ITEMS, ITEMS_PER_LEVEL, LIVES, accuracyOf, levelOf, lessonFor, nextItem, scoreOf, timeForLevel, type ArtId,
} from "@/lib/game";

// A tiny seeded random generator so these tests never flake.
const seeded = (seed: number) => () => ((seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296);

describe("scoring matches the server (face_api/app/game.py)", () => {
  it("is 10 per item plus 5 per item in the best streak", () => {
    expect(scoreOf(20, 9)).toBe(245);
    expect(scoreOf(0, 0)).toBe(0);
    expect(scoreOf(40, 15)).toBe(475);
  });
  it("levels up every 8 correct items", () => {
    expect([0, 7, 8, 15, 16, 24].map(levelOf)).toEqual([1, 1, 2, 2, 3, 4]);
    expect(ITEMS_PER_LEVEL).toBe(8);
  });
  it("rounds accuracy and handles an empty game", () => {
    expect(accuracyOf(20, 2, 1)).toBe(87);
    expect(accuracyOf(0, 0, 0)).toBe(0);
    expect(accuracyOf(5, 0, 0)).toBe(100);
  });
  it("gives three lives", () => expect(LIVES).toBe(3));
});

describe("time per item", () => {
  it("starts at 7 seconds, gets shorter, and stops at 2.8 seconds", () => {
    expect(timeForLevel(1)).toBe(7000);
    expect(timeForLevel(2)).toBe(6500);
    const times = Array.from({ length: 20 }, (_, i) => timeForLevel(i + 1));
    expect(times.every((t, i) => i === 0 || t <= times[i - 1])).toBe(true);
    expect(timeForLevel(50)).toBe(2800);
  });
});

describe("the item set", () => {
  it("has unique ids and every bin has easy items", () => {
    expect(new Set(ITEMS.map((i) => i.id)).size).toBe(ITEMS.length);
    for (const b of BINS) expect(ITEMS.some((i) => i.bin === b.id && i.easy)).toBe(true);
  });
  it("includes the things from the whiteboard sketch in the right bins", () => {
    const bin = (name: string) => ITEMS.find((i) => i.name === name)?.bin;
    expect(bin("Water bottle")).toBe("cans");
    expect(bin("Soda can")).toBe("cans");
    expect(bin("Burger")).toBe("organics");
    expect(bin("Fries")).toBe("organics");
    expect(bin("Cup with straw")).toBe("waste");
    expect(bin("Candy wrapper")).toBe("waste");
  });
});

describe("nextItem", () => {
  it("only uses easy items on level 1 and everything from level 2", () => {
    const rng = seeded(1);
    const l1 = new Set(Array.from({ length: 300 }, () => nextItem(1, [], rng).id));
    expect([...l1].every((id) => ITEMS.find((i) => i.id === id)!.easy)).toBe(true);
    const l2 = new Set(Array.from({ length: 600 }, () => nextItem(2, [], rng).id));
    expect(l2.size).toBe(ITEMS.length);
  });
  it("never repeats an item from the last two turns", () => {
    const rng = seeded(7);
    const seen: ArtId[] = [];
    for (let i = 0; i < 500; i++) {
      const it = nextItem(2, seen, rng);
      expect(seen.slice(-2)).not.toContain(it.id);
      seen.push(it.id);
    }
  });
  it("shows the three bins about equally often", () => {
    const rng = seeded(3);
    const counts = { cans: 0, organics: 0, waste: 0 };
    for (let i = 0; i < 3000; i++) counts[nextItem(2, [], rng).bin]++;
    for (const n of Object.values(counts)) expect(n).toBeGreaterThan(850);
  });
});

describe("lessons", () => {
  it("say where the item really goes, kindly", () => {
    const peel = ITEMS.find((i) => i.id === "banana")!;
    expect(lessonFor(peel, "wrong")).toBe("Oops! Banana peel goes in Food scraps.");
    expect(lessonFor(peel, "spill")).toBe("Oh no, it spilled! Banana peel goes in Food scraps.");
  });
});
